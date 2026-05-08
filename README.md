# ShortsBot

A desktop app for managing and publishing YouTube Shorts and TikTok videos. Built with Python + tkinter.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)

---

## Features

### YouTube
- OAuth 2.0 authentication with multi-account support
- Browse your private and scheduled videos with thumbnails
- Edit all available metadata fields per video:
  - Title, Description, Tags, Category
  - Privacy, License, Language, Audio Language
  - Made for Kids, Synthetic Media, publicStatsViewable, Embeddable
- Auto-schedule selected videos to 7 AM / 9 PM PT slots (2 per day)
- Batch apply & save changes to multiple videos at once
- Upload new Shorts with all insert fields including thumbnail
- Copy publish schedule to clipboard
- Dry Run mode — preview API calls without sending them
- Tag presets saved per game/series in `config.json`

### TikTok
- OAuth 2.0 + PKCE authentication with multi-account support
- Browse your TikTok videos with thumbnails and stats
- Delete videos
- Upload new videos with all Content Posting API v2 fields:
  - Title / Caption, Privacy Level
  - Disable Duet / Comments / Stitch
  - Cover Timestamp, Paid Partnership, Branded Organic, AI-Generated
- Fetch account settings to see what your account allows
- Resumable chunked upload with live progress bar

---

## Setup

### Requirements

- Python 3.10+
- A Google Cloud project with YouTube Data API v3 enabled
- A TikTok developer app (optional, for TikTok features)

### Install dependencies

```bash
pip install -r requirements.txt
```

### YouTube credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project and enable **YouTube Data API v3**
3. Go to **APIs & Services → Credentials → Create OAuth 2.0 Client ID**
4. Application type: **Desktop app**
5. Download the JSON and save it as `client_secrets.json` in the app folder

### TikTok credentials (optional)

1. Create an app at [developers.tiktok.com](https://developers.tiktok.com)
2. Add the **Content Posting API** and **Video List** products
3. Add `http://localhost:8080/callback` as a redirect URI
4. Create `tiktok_client_secrets.json` in the app folder:

```json
{
  "client_key": "your_client_key",
  "client_secret": "your_client_secret"
}
```

### Run

```bash
python main.py
```

On first launch you'll be prompted to name your YouTube account and complete the OAuth flow in your browser. The token is saved to `tokens/` for future runs.

---

## File Structure

```
ShortsBot/
├── main.py                    # Entry point
├── auth.py                    # YouTube OAuth flow + token management
├── youtube_api.py             # YouTube Data API v3 calls
├── tiktok_auth.py             # TikTok OAuth 2.0 + PKCE flow
├── tiktok_api.py              # TikTok Content Posting API v2 calls
├── scheduler.py               # 7 AM / 9 PM slot assignment logic
├── ui/
│   ├── app.py                 # Main window + platform notebooks
│   ├── video_table.py         # Scrollable YouTube video list
│   ├── settings_panel.py      # Per-video settings panel
│   ├── upload_tab.py          # YouTube upload tab
│   ├── tiktok_manage_tab.py   # TikTok video list + delete
│   └── tiktok_upload_tab.py   # TikTok upload tab
├── config.json                # User config (tags, timezone, schedules)
├── requirements.txt
├── client_secrets.json        # you provide (not in repo)
└── tiktok_client_secrets.json # you provide (not in repo)
```

---

## Config

`config.json` is created automatically on first run. Key fields:

| Field | Default | Description |
|---|---|---|
| `default_tags` | GoodKhaos tag set | Tags pre-filled on every video |
| `timezone` | `America/Los_Angeles` | Used for schedule display and conversion |
| `schedule_times` | `["07:00", "21:00"]` | Daily publish slots (24h local time) |
| `load_limit` | `25` | Videos to fetch on refresh (0 = all) |
| `tag_presets` | `{}` | Named tag sets saved per game/series |

---

## Notes

- Tokens are stored in `tokens/` (YouTube) and `tiktok_tokens/` (TikTok) — gitignored, never committed
- YouTube scheduled videos must have `privacyStatus: private` — the app enforces this automatically
- TikTok uploads use resumable chunked uploads (10 MB chunks) so large files work reliably
- The YouTube batch update preserves all fields you don't explicitly change (description, embeddable, license, etc.)
