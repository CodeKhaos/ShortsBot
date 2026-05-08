"""TikTok Content Posting API v2 — list, upload, delete."""

import math
import time
from pathlib import Path
from typing import Callable

import requests

BASE = "https://open.tiktokapis.com"
CHUNK_SIZE = 10 * 1024 * 1024   # 10 MB per chunk (TikTok min non-last = 5 MB)
MAX_POLL = 60                    # max status-poll attempts
POLL_INTERVAL = 3                # seconds between polls

VIDEO_FIELDS = (
    "id,title,video_description,create_time,cover_image_url,"
    "share_url,duration,height,width,embed_link,"
    "view_count,like_count,comment_count,share_count,privacy_level"
)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _headers(token: dict) -> dict:
    return {"Authorization": f"Bearer {token['access_token']}"}


def _post(endpoint: str, token: dict, **kwargs) -> dict:
    resp = requests.post(
        BASE + endpoint, headers=_headers(token), timeout=30, **kwargs
    )
    resp.raise_for_status()
    data = resp.json()
    err = data.get("error", {})
    if err.get("code", "ok") not in ("ok", ""):
        raise RuntimeError(f"TikTok API error [{err.get('code')}]: {err.get('message')}")
    return data


def _get(endpoint: str, token: dict, **kwargs) -> dict:
    resp = requests.get(
        BASE + endpoint, headers=_headers(token), timeout=30, **kwargs
    )
    resp.raise_for_status()
    data = resp.json()
    err = data.get("error", {})
    if err.get("code", "ok") not in ("ok", ""):
        raise RuntimeError(f"TikTok API error [{err.get('code')}]: {err.get('message')}")
    return data


# ---------------------------------------------------------------------------
# Creator info — tells us what settings this account allows
# ---------------------------------------------------------------------------

def query_creator_info(token: dict) -> dict:
    """
    Returns a dict with keys like:
      creator_avatar_url, creator_username, creator_nickname,
      privacy_level_options, comment_disabled, duet_disabled,
      stitch_disabled, max_video_post_duration_sec
    """
    data = _post("/v2/post/publish/creator_info/query/", token)
    return data.get("data", {})


# ---------------------------------------------------------------------------
# Video list
# ---------------------------------------------------------------------------

def fetch_my_videos(token: dict, limit: int = 25) -> list[dict]:
    """Return up to `limit` of the user's TikTok videos, newest first."""
    videos = []
    cursor = 0
    page = min(limit, 20) if limit else 20  # TikTok max page size = 20

    while True:
        body = {
            "max_count": page,
            "fields": VIDEO_FIELDS,
        }
        if cursor:
            body["cursor"] = cursor

        data = _post("/v2/video/list/", token, json=body)
        items = data.get("data", {}).get("videos", [])
        videos.extend(items)

        if limit and len(videos) >= limit:
            break
        if not data.get("data", {}).get("has_more"):
            break
        cursor = data["data"].get("cursor", 0)

    return videos[:limit] if limit else videos


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_video(token: dict, video_id: str) -> None:
    _post("/v2/video/delete/", token, json={"video_id": video_id})


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def upload_video(
    token: dict,
    file_path: str,
    title: str,
    privacy_level: str = "SELF_ONLY",
    disable_duet: bool = False,
    disable_comment: bool = False,
    disable_stitch: bool = False,
    video_cover_timestamp_ms: int = 0,
    brand_content_toggle: bool = False,
    brand_organic_toggle: bool = False,
    is_aigc: bool = False,
    progress_callback: Callable[[float], None] | None = None,
) -> str:
    """
    Upload a video via TikTok's resumable chunked upload.
    Returns the publish_id; poll get_publish_status() for the final video_id.
    """
    path = Path(file_path)
    file_size = path.stat().st_size

    # Determine chunk layout
    if file_size <= CHUNK_SIZE:
        chunk_size = file_size
        total_chunks = 1
    else:
        chunk_size = CHUNK_SIZE
        total_chunks = math.ceil(file_size / chunk_size)

    # 1. Initialize upload
    init_body = {
        "post_info": {
            "title": title,
            "privacy_level": privacy_level,
            "disable_duet": disable_duet,
            "disable_comment": disable_comment,
            "disable_stitch": disable_stitch,
            "video_cover_timestamp_ms": video_cover_timestamp_ms,
            "brand_content_toggle": brand_content_toggle,
            "brand_organic_toggle": brand_organic_toggle,
            "is_aigc": is_aigc,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunks,
        },
    }
    init_data = _post("/v2/post/publish/video/init/", token, json=init_body)
    upload_url = init_data["data"]["upload_url"]
    publish_id = init_data["data"]["publish_id"]

    # 2. Upload chunks
    with open(file_path, "rb") as fh:
        for chunk_idx in range(total_chunks):
            start = chunk_idx * chunk_size
            data = fh.read(chunk_size)
            end = start + len(data) - 1

            for attempt in range(3):
                resp = requests.put(
                    upload_url,
                    data=data,
                    headers={
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                        "Content-Type": "video/mp4",
                        "Content-Length": str(len(data)),
                    },
                    timeout=120,
                )
                if resp.status_code in (200, 201, 206):
                    break
                if resp.status_code >= 500 and attempt < 2:
                    time.sleep(2)
                    continue
                resp.raise_for_status()

            if progress_callback:
                progress_callback((chunk_idx + 1) / total_chunks * 90)

    if progress_callback:
        progress_callback(90)

    return publish_id


def get_publish_status(token: dict, publish_id: str) -> dict:
    """
    Poll until the video is published or fails.
    Returns the final status dict with keys: status, fail_reason, publicaly_available_post_id
    """
    for _ in range(MAX_POLL):
        data = _post(
            "/v2/post/publish/status/fetch/",
            token,
            json={"publish_id": publish_id},
        )
        status_data = data.get("data", {})
        status = status_data.get("status", "")
        if status == "PUBLISH_COMPLETE":
            return status_data
        if status in ("FAILED", "PUBLISH_FAILED"):
            reason = status_data.get("fail_reason", "unknown")
            raise RuntimeError(f"TikTok publish failed: {reason}")
        time.sleep(POLL_INTERVAL)

    raise RuntimeError("Timed out waiting for TikTok publish to complete.")
