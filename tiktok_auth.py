"""TikTok OAuth 2.0 — multi-account token management."""

import hashlib
import json
import re
import secrets
import string
import threading
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import requests

TOKENS_DIR = Path("tiktok_tokens")
SCOPES = "user.info.basic,video.upload,video.publish,video.list"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
REDIRECT_URI = "http://localhost:8080/callback"


# ---------------------------------------------------------------------------
# One-shot local callback server
# ---------------------------------------------------------------------------

class _Result:
    code: str | None = None
    error: str | None = None


class _Handler(BaseHTTPRequestHandler):
    result: _Result
    event: threading.Event

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            _Handler.result.code = params["code"][0]
        elif "error" in params:
            _Handler.result.error = params.get("error_description", params["error"])[0]
        else:
            _Handler.result.error = "No code or error returned."

        body = b"<html><body><h1>Authorization complete - you can close this tab.</h1></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        _Handler.event.set()

    def log_message(self, *_):
        pass


def _run_oauth_flow(client_key: str, client_secret: str, use_pkce: bool = True) -> dict:
    """Authorization code flow.  PKCE (S256) is used when use_pkce=True."""
    state = secrets.token_urlsafe(16)

    params = {
        "client_key": client_key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
    }

    code_verifier: str | None = None
    if use_pkce:
        alphabet = string.ascii_letters + string.digits
        code_verifier = "".join(secrets.choice(alphabet) for _ in range(64))
        # TikTok's S256 challenge is the SHA256 hex digest — NOT base64url as per
        # RFC 7636. Their own docs show: SHA256(verifier).toString(CryptoJS.enc.Hex)
        code_challenge = hashlib.sha256(code_verifier.encode("ascii")).hexdigest()
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    auth_url = AUTH_URL + "?" + urlencode(params)

    result = _Result()
    done = threading.Event()
    _Handler.result = result
    _Handler.event = done

    server = HTTPServer(("localhost", 8080), _Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    webbrowser.open(auth_url)
    done.wait(timeout=300)
    server.server_close()

    if result.error:
        raise RuntimeError(f"TikTok auth error: {result.error}")
    if not result.code:
        raise RuntimeError("Auth timed out — no code received within 5 minutes.")

    token_params = {
        "client_key": client_key,
        "client_secret": client_secret,
        "code": result.code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }
    if code_verifier is not None:
        token_params["code_verifier"] = code_verifier

    resp = requests.post(
        TOKEN_URL,
        data=token_params,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(f"Token exchange failed: {data}")
    return data


# ---------------------------------------------------------------------------
# Token file helpers
# ---------------------------------------------------------------------------

def _token_path(label: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", label).strip("_") or "tiktok_account"
    return TOKENS_DIR / f"{safe}.json"


def _load_token_file(label: str) -> dict | None:
    path = _token_path(label)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _save_token_file(label: str, data: dict) -> None:
    TOKENS_DIR.mkdir(exist_ok=True)
    _token_path(label).write_text(json.dumps(data, indent=2))


def _refresh_token(stored: dict, client_key: str, client_secret: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": stored["refresh_token"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_credentials(label: str, client_secrets_path: str) -> dict:
    """
    Return a valid token dict for `label`.
    Refreshes automatically; runs full OAuth if no token exists.
    Returned dict always has 'access_token'.
    """
    secrets_data = _read_secrets(client_secrets_path)
    client_key = secrets_data["client_key"]
    client_secret = secrets_data["client_secret"]

    stored = _load_token_file(label)

    if stored and stored.get("access_token"):
        # Check expiry — refresh 60s before actual expiry
        expires_at = stored.get("expires_at", 0)
        if datetime.utcnow().timestamp() < expires_at - 60:
            return stored
        # Try refresh
        if stored.get("refresh_token"):
            try:
                refreshed = _refresh_token(stored, client_key, client_secret)
                refreshed = _annotate_expiry(refreshed)
                _save_token_file(label, refreshed)
                return refreshed
            except Exception:
                pass

    # Full flow
    token = _run_oauth_flow(client_key, client_secret)
    token = _annotate_expiry(token)
    _save_token_file(label, token)
    return token


def add_account(label: str, client_secrets_path: str) -> dict:
    """Force a fresh OAuth flow for a new account."""
    secrets_data = _read_secrets(client_secrets_path)
    token = _run_oauth_flow(secrets_data["client_key"], secrets_data["client_secret"])
    token = _annotate_expiry(token)
    _save_token_file(label, token)
    return token


def remove_account(label: str) -> None:
    path = _token_path(label)
    if path.exists():
        path.unlink()


def _annotate_expiry(token: dict) -> dict:
    expires_in = token.get("expires_in", 86400)
    token["expires_at"] = (datetime.utcnow() + timedelta(seconds=expires_in)).timestamp()
    return token


def _read_secrets(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except Exception as e:
        raise RuntimeError(
            f"Could not read TikTok client secrets from '{path}'.\n"
            f"Expected JSON with 'client_key' and 'client_secret'.\n{e}"
        ) from e
