"""All YouTube Data API v3 calls: list, update, batch, upload."""

import time
from typing import Any, Callable

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

UPLOAD_CHUNK = 4 * 1024 * 1024  # 4 MB resumable chunks


def build_service(creds: Credentials):
    return build("youtube", "v3", credentials=creds)


def fetch_my_videos(service, limit: int = 25) -> list[dict]:
    """
    Fetch the most recent `limit` videos from the channel's uploads playlist,
    then return only the private/scheduled ones.
    Pass limit=0 to fetch all.
    """
    # Step 1: get the uploads playlist ID.
    # Try personal channel first, then brand/managed channels as fallback.
    try:
        ch_resp = service.channels().list(
            part="contentDetails", mine=True
        ).execute()
    except HttpError as e:
        raise RuntimeError(f"Failed to fetch channel info: {e}") from e

    items = ch_resp.get("items", [])

    if not items:
        # Brand Account channels don't appear under mine=True
        try:
            ch_resp = service.channels().list(
                part="contentDetails", managedByMe=True, maxResults=50
            ).execute()
            items = ch_resp.get("items", [])
        except HttpError:
            items = []

    if not items:
        raise RuntimeError(
            "No YouTube channel found for this account.\n\n"
            "If BibleKhaos is a Brand Account, you need to sign in as that brand "
            "account directly during the OAuth flow — not as your personal Google "
            "account. Try removing this account and re-adding it, then click "
            "'Switch Account' on the Google sign-in page to select the correct channel."
        )

    uploads_playlist_id = (
        items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    )

    # Step 2: collect video IDs up to limit (playlist is newest-first)
    video_ids = []
    page_token = None
    while True:
        remaining = (limit - len(video_ids)) if limit else 50
        batch_size = min(remaining, 50) if limit else 50
        kwargs = dict(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=batch_size,
        )
        if page_token:
            kwargs["pageToken"] = page_token
        try:
            pl_resp = service.playlistItems().list(**kwargs).execute()
        except HttpError as e:
            raise RuntimeError(f"Failed to list playlist items: {e}") from e

        for item in pl_resp.get("items", []):
            vid_id = item["contentDetails"].get("videoId")
            if vid_id:
                video_ids.append(vid_id)

        page_token = pl_resp.get("nextPageToken")
        if not page_token or (limit and len(video_ids) >= limit):
            break

    if not video_ids:
        return []

    # Step 3: fetch snippet+status in batches of 50
    videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        videos.extend(_get_video_details(service, batch))

    # Filter to private + scheduled only
    return [
        v for v in videos
        if v.get("status", {}).get("privacyStatus") in ("private", "unlisted")
        or v.get("status", {}).get("publishAt")
    ]


def _get_video_details(service, video_ids: list[str]) -> list[dict]:
    resp = service.videos().list(
        part="snippet,status",
        id=",".join(video_ids),
        maxResults=50,
    ).execute()
    return resp.get("items", [])


def update_video(
    service,
    video_id: str,
    existing_video: dict,
    title: str,
    description: str,
    tags: list[str],
    publish_at: str | None,
    privacy_status: str = "private",
    category_id: str = "20",
    default_language: str | None = None,
    default_audio_language: str | None = None,
    license: str = "youtube",
    embeddable: bool = True,
    made_for_kids: bool = False,
    contains_synthetic_media: bool = False,
    public_stats_viewable: bool = False,
    dry_run: bool = False,
) -> dict:
    """Update a single video's snippet + status with all writable fields."""
    existing_snippet = existing_video.get("snippet", {})

    snippet = {
        "title": title,
        "description": description,
        "tags": tags,
        "categoryId": category_id,
    }
    if default_language:
        snippet["defaultLanguage"] = default_language
    if default_audio_language:
        snippet["defaultAudioLanguage"] = default_audio_language

    status = {
        "privacyStatus": privacy_status,
        "embeddable": embeddable,
        "license": license,
        "publicStatsViewable": public_stats_viewable,
        "selfDeclaredMadeForKids": made_for_kids,
        "containsSyntheticMedia": contains_synthetic_media,
    }
    if publish_at:
        status["publishAt"] = publish_at
        status["privacyStatus"] = "private"

    body = {"id": video_id, "snippet": snippet, "status": status}

    if dry_run:
        return {"id": video_id, "dryRun": True, "wouldSend": body}

    return _call_with_retry(
        lambda: service.videos().update(
            part="snippet,status",
            body=body,
        ).execute()
    )


def upload_video(
    service,
    file_path: str,
    title: str,
    description: str,
    tags: list[str],
    category_id: str = "20",
    privacy_status: str = "private",
    publish_at: str | None = None,
    default_language: str | None = None,
    default_audio_language: str | None = None,
    license: str = "youtube",
    embeddable: bool = True,
    made_for_kids: bool = False,
    contains_synthetic_media: bool = False,
    public_stats_viewable: bool = False,
    notify_subscribers: bool = False,
    progress_callback: Callable[[float], None] | None = None,
) -> dict:
    """
    Upload a video file using a resumable upload.
    progress_callback(pct) is called with 0-100 as chunks complete.
    Returns the inserted video resource dict.
    """
    snippet = {
        "title": title,
        "description": description,
        "tags": tags,
        "categoryId": category_id,
    }
    if default_language:
        snippet["defaultLanguage"] = default_language
    if default_audio_language:
        snippet["defaultAudioLanguage"] = default_audio_language

    status = {
        "privacyStatus": "private" if publish_at else privacy_status,
        "embeddable": embeddable,
        "license": license,
        "publicStatsViewable": public_stats_viewable,
        "selfDeclaredMadeForKids": made_for_kids,
        "containsSyntheticMedia": contains_synthetic_media,
    }
    if publish_at:
        status["publishAt"] = publish_at

    body = {"snippet": snippet, "status": status}
    media = MediaFileUpload(file_path, mimetype="video/*", resumable=True, chunksize=UPLOAD_CHUNK)

    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
        notifySubscribers=notify_subscribers,
    )

    response = None
    while response is None:
        try:
            http_status, response = request.next_chunk()
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504):
                time.sleep(2)
                continue
            raise
        if http_status and progress_callback:
            progress_callback(http_status.progress() * 100)

    if progress_callback:
        progress_callback(100.0)
    return response


def set_thumbnail(service, video_id: str, image_path: str) -> dict:
    """Upload a custom thumbnail for the given video."""
    import mimetypes
    mime, _ = mimetypes.guess_type(image_path)
    mime = mime or "image/jpeg"
    media = MediaFileUpload(image_path, mimetype=mime, resumable=False)
    return _call_with_retry(
        lambda: service.thumbnails().set(
            videoId=video_id, media_body=media
        ).execute()
    )


def _call_with_retry(fn, retries: int = 1, delay: float = 2.0) -> Any:
    """Call fn(); on 5xx error retry once after delay seconds."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except HttpError as e:
            if e.resp.status >= 500 and attempt < retries:
                time.sleep(delay)
                continue
            raise


def batch_update_videos(
    service,
    updates: list[dict],
    dry_run: bool = False,
    progress_callback=None,
) -> list[dict]:
    """
    Process a list of update dicts. Each dict must include 'existing_video'
    (the full API item) so update_video can preserve untouched fields.
    Calls progress_callback(index, total, video_id, success, error) after each video.
    """
    results = []
    total = len(updates)

    for i, upd in enumerate(updates):
        vid_id = upd["video_id"]
        try:
            ex_snippet = upd["existing_video"].get("snippet", {})
            ex_status = upd["existing_video"].get("status", {})
            result = update_video(
                service=service,
                video_id=vid_id,
                existing_video=upd["existing_video"],
                title=upd["title"],
                description=upd.get("description", ex_snippet.get("description", "")),
                tags=upd["tags"],
                publish_at=upd.get("publish_at"),
                privacy_status=upd.get("privacy_status", ex_status.get("privacyStatus", "private")),
                category_id=upd.get("category_id", str(ex_snippet.get("categoryId", "20"))),
                default_language=upd.get("default_language", ex_snippet.get("defaultLanguage")),
                default_audio_language=upd.get("default_audio_language", ex_snippet.get("defaultAudioLanguage")),
                license=upd.get("license", ex_status.get("license", "youtube")),
                embeddable=upd.get("embeddable", ex_status.get("embeddable", True)),
                made_for_kids=upd.get("made_for_kids", False),
                contains_synthetic_media=upd.get("contains_synthetic_media", False),
                public_stats_viewable=upd.get("public_stats_viewable", False),
                dry_run=dry_run,
            )
            results.append({"video_id": vid_id, "success": True, "data": result})
            if progress_callback:
                progress_callback(i + 1, total, vid_id, True, None)
        except Exception as exc:
            results.append({"video_id": vid_id, "success": False, "error": str(exc)})
            if progress_callback:
                progress_callback(i + 1, total, vid_id, False, str(exc))

    return results
