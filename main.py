"""Entry point for YouTube Shorts Manager."""

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

CONFIG_PATH = Path("config.json")
DEFAULT_CONFIG = {
    "accounts": [],
    "active_account": "",
    "default_tags": [
        "goodkhaos", "good khaos", "goodchaos", "good chaos", "good kaos", "goodkaos",
        "gk", "biblekhaos", "bible khaos"
    ],
    "timezone": "America/Los_Angeles",
    "schedule_times": ["07:00", "21:00"],
    "client_secrets_path": "client_secrets.json",
    "tiktok_client_secrets_path": "tiktok_client_secrets.json",
    "tiktok_accounts": [],
    "tiktok_active_account": "",
    "load_limit": 25,
    "tag_presets": {},
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


def main():
    config = load_config()
    secrets_path = config.get("client_secrets_path", "client_secrets.json")

    if not Path(secrets_path).exists():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Missing credentials",
            f"OAuth credentials file not found: {secrets_path}\n\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials,\n"
            "name it 'client_secrets.json', and place it in the app folder.",
        )
        sys.exit(1)

    from auth import load_credentials, add_account

    # First launch — no accounts saved yet
    if not config.get("accounts"):
        root = tk.Tk()
        root.withdraw()
        label = simpledialog.askstring(
            "Add Account",
            "Enter a name for this YouTube account\n(e.g. 'GoodKhaos'):",
            parent=root,
        )
        root.destroy()
        if not label:
            sys.exit(0)
        label = label.strip()
        try:
            creds = add_account(label, secrets_path)
        except Exception as exc:
            root2 = tk.Tk()
            root2.withdraw()
            messagebox.showerror("Auth Error", f"OAuth failed:\n{exc}")
            root2.destroy()
            sys.exit(1)
        config["accounts"].append(label)
        config["active_account"] = label
        save_config(config)
    else:
        active = config.get("active_account") or config["accounts"][0]
        config["active_account"] = active
        try:
            creds = load_credentials(active, secrets_path)
        except Exception as exc:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Auth Error", f"OAuth failed for '{active}':\n{exc}")
            root.destroy()
            sys.exit(1)

    from ui.app import App
    app = App(creds=creds, config=config, on_config_change=lambda: save_config(config))
    app.mainloop()
    save_config(config)


if __name__ == "__main__":
    main()
