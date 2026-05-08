"""OAuth 2.0 flow and token management — multi-account support."""

import re
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube"]
TOKENS_DIR = Path("tokens")


def _token_path(label: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", label).strip("_") or "account"
    return TOKENS_DIR / f"{safe}.json"


def load_credentials(label: str, client_secrets_path: str) -> Credentials:
    """Return valid credentials for `label`, refreshing or re-authing as needed."""
    TOKENS_DIR.mkdir(exist_ok=True)
    path = _token_path(label)
    creds = None

    if path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(path), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            path.write_text(creds.to_json())
            return creds
        except Exception:
            creds = None

    # Full OAuth flow — opens browser
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    path.write_text(creds.to_json())
    return creds


def add_account(label: str, client_secrets_path: str) -> Credentials:
    """Run a fresh OAuth flow for a new account label and save its token."""
    TOKENS_DIR.mkdir(exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    _token_path(label).write_text(creds.to_json())
    return creds


def remove_account(label: str) -> None:
    """Delete the saved token for `label`."""
    path = _token_path(label)
    if path.exists():
        path.unlink()
