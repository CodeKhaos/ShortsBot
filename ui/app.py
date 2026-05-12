"""Main application window."""

import json
import threading
import tkinter as tk
from datetime import datetime, date
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog
import pytz
from ui.widgets import DateEntry

from ui.video_table import VideoTable
from ui.settings_panel import SettingsPanel
from ui.upload_tab import UploadTab
from ui.bulk_upload_tab import BulkUploadTab
from ui.tiktok_manage_tab import TikTokManageTab
from ui.tiktok_upload_tab import TikTokUploadTab
from scheduler import generate_slots, format_schedule_summary
from youtube_api import build_service, fetch_my_videos, batch_update_videos
from auth import load_credentials, add_account, remove_account
import tiktok_auth

CONFIG_PATH = Path("config.json")


class App(tk.Tk):
    def __init__(self, creds, config: dict, on_config_change=None):
        super().__init__()
        self._creds = creds
        self._config = config
        self._on_config_change = on_config_change
        self._service = build_service(creds)
        self._videos: list[dict] = []
        self._dry_run = tk.BooleanVar(value=False)

        self.title("YouTube Shorts Manager")
        self.geometry("1100x780")
        self.minsize(900, 600)
        self._build()
        self.after(100, self._load_videos)

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------
    def _build(self):

        # ── Top-level platform notebook ───────────────────────────────
        platform_nb = ttk.Notebook(self)
        platform_nb.pack(fill="both", expand=True, padx=6, pady=4)

        # ── YouTube platform tab ──────────────────────────────────────
        yt_frame = ttk.Frame(platform_nb)
        platform_nb.add(yt_frame, text="  YouTube  ")
        self._build_youtube_platform(yt_frame)

        # ── TikTok platform tab ───────────────────────────────────────
        tk_frame = ttk.Frame(platform_nb)
        platform_nb.add(tk_frame, text="  TikTok  ")
        self._build_tiktok_platform(tk_frame)

    def _build_youtube_platform(self, parent):
        """YouTube tab: account bar + sub-notebook (Manage / Upload)."""
        # Account bar (YouTube-specific)
        self._build_yt_account_bar(parent)
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=4)

        # Sub-notebook
        yt_nb = ttk.Notebook(parent)
        yt_nb.pack(fill="both", expand=True, padx=4, pady=(2, 4))

        manage_frame = ttk.Frame(yt_nb)
        yt_nb.add(manage_frame, text="📋  Manage Videos")
        self._build_manage_content(manage_frame)

        self.upload_tab = UploadTab(
            yt_nb, get_service=lambda: self._service, config=self._config
        )
        yt_nb.add(self.upload_tab, text="⬆  Upload Short")

        self.bulk_upload_tab = BulkUploadTab(
            yt_nb, get_service=lambda: self._service, config=self._config
        )
        yt_nb.add(self.bulk_upload_tab, text="⬆⬆  Bulk Upload")

    def _build_yt_account_bar(self, parent):
        bar = ttk.Frame(parent, padding=(6, 3))
        bar.pack(fill="x", side="top")
        ttk.Label(bar, text="Account:").pack(side="left")
        self.account_var = tk.StringVar(value=self._config.get("active_account", ""))
        self.account_combo = ttk.Combobox(
            bar, textvariable=self.account_var,
            values=self._config.get("accounts", []),
            width=22, state="readonly",
        )
        self.account_combo.pack(side="left", padx=(4, 2))
        self.account_combo.bind("<<ComboboxSelected>>", self._on_account_selected)
        ttk.Button(bar, text="+ Add Account", command=self._add_account).pack(side="left", padx=2)
        ttk.Button(bar, text="✕ Remove", command=self._remove_account).pack(side="left", padx=2)

    def _build_yt_action_toolbar(self, parent):
        """Toolbar for the Manage Videos tab — refresh, scheduling, save, copy."""
        toolbar = ttk.Frame(parent, padding=(6, 3))
        toolbar.pack(fill="x", side="top")

        # ── Refresh + load limit ──────────────────────────────────────
        ttk.Button(toolbar, text="↺ Refresh", command=self._load_videos).pack(side="left", padx=2)
        ttk.Label(toolbar, text="Load:").pack(side="left", padx=(6, 2))
        self.load_limit_var = tk.StringVar(value=str(self._config.get("load_limit", 25)))
        ttk.Entry(toolbar, textvariable=self.load_limit_var, width=5).pack(side="left")
        ttk.Label(toolbar, text="videos (0=all)").pack(side="left", padx=(2, 0))

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)

        # ── Schedule mode selector ────────────────────────────────────
        ttk.Label(toolbar, text="Schedule:").pack(side="left", padx=(0, 4))
        self._sched_mode = tk.StringVar(value="Bulk Schedule")
        mode_combo = ttk.Combobox(
            toolbar, textvariable=self._sched_mode,
            values=["Bulk Schedule", "Schedule Date"],
            width=14, state="readonly",
        )
        mode_combo.pack(side="left", padx=(0, 6))

        # ── Bulk Schedule panel ───────────────────────────────────────
        self._bulk_frame = ttk.Frame(toolbar)
        self._bulk_frame.pack(side="left")
        ttk.Label(self._bulk_frame, text="Start Date:").pack(side="left", padx=(0, 4))
        self._bulk_date_picker = DateEntry(
            self._bulk_frame, width=12, date_pattern="yyyy-mm-dd",
            background="darkblue", foreground="white", borderwidth=2,
        )
        self._bulk_date_picker.set_date(date.today())
        self._bulk_date_picker.pack(side="left", padx=(0, 6))
        ttk.Button(
            self._bulk_frame, text="⚡ Auto-Schedule Selected",
            command=self._auto_schedule,
        ).pack(side="left", padx=2)

        # ── Schedule Date panel ───────────────────────────────────────
        self._date_frame = ttk.Frame(toolbar)
        # (not packed yet — hidden until mode switches)
        ttk.Label(self._date_frame, text="Date:").pack(side="left", padx=(0, 4))
        self._sched_date_picker = DateEntry(
            self._date_frame, width=12, date_pattern="yyyy-mm-dd",
            background="darkblue", foreground="white", borderwidth=2,
        )
        self._sched_date_picker.set_date(date.today())
        self._sched_date_picker.pack(side="left", padx=(0, 6))
        ttk.Label(self._date_frame, text="Time:").pack(side="left", padx=(0, 4))
        self._sched_hour = tk.StringVar(value="07")
        self._sched_min  = tk.StringVar(value="00")
        ttk.Spinbox(
            self._date_frame, textvariable=self._sched_hour,
            values=[f"{h:02d}" for h in range(24)],
            width=3, wrap=True, state="readonly",
        ).pack(side="left")
        ttk.Label(self._date_frame, text=":").pack(side="left")
        ttk.Spinbox(
            self._date_frame, textvariable=self._sched_min,
            values=["00","05","10","15","20","25","30","35","40","45","50","55"],
            width=3, wrap=True, state="readonly",
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            self._date_frame, text="📅 Apply Date to Selected",
            command=self._apply_schedule_date,
        ).pack(side="left", padx=2)

        # swap panels when mode changes
        mode_combo.bind("<<ComboboxSelected>>", self._on_sched_mode_change)

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)

        # ── Shared action buttons ─────────────────────────────────────
        ttk.Button(toolbar, text="💾 Apply & Save Selected", command=self._apply_save).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="📋 Copy Schedule", command=self._copy_schedule).pack(
            side="left", padx=2
        )
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Checkbutton(toolbar, text="Dry Run", variable=self._dry_run).pack(side="left")

    def _on_sched_mode_change(self, _event=None):
        if self._sched_mode.get() == "Bulk Schedule":
            self._date_frame.pack_forget()
            self._bulk_frame.pack(side="left")
        else:
            self._bulk_frame.pack_forget()
            self._date_frame.pack(side="left")

    def _build_manage_content(self, parent):
        self._build_yt_action_toolbar(parent)

        paned = ttk.PanedWindow(parent, orient="vertical")
        paned.pack(fill="both", expand=True)

        table_frame = ttk.LabelFrame(paned, text="Videos (private / scheduled)", padding=4)
        self.video_table = VideoTable(table_frame, on_select=self._on_video_select)
        self.video_table.pack(fill="both", expand=True)
        paned.add(table_frame, weight=3)

        bottom = ttk.Frame(paned)
        paned.add(bottom, weight=2)

        self.settings_panel = SettingsPanel(
            bottom, config=self._config, on_change=self._on_settings_change
        )
        self.settings_panel.pack(side="left", fill="both", expand=True, padx=(0, 4))

        log_frame = ttk.LabelFrame(bottom, text="Status Log", padding=4)
        log_frame.pack(side="right", fill="both", expand=True)

        self.log_text = tk.Text(
            log_frame, width=38, state="disabled", wrap="word", font=("Courier", 9)
        )
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        self.progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(
            parent, variable=self.progress_var, maximum=100, mode="determinate"
        ).pack(fill="x", side="bottom", padx=0, pady=(0, 2))

    def _build_tiktok_platform(self, parent):
        """TikTok tab: account bar + sub-notebook (Manage / Upload)."""
        self._tiktok_token: dict | None = None
        self._tiktok_accounts: list[str] = self._config.get("tiktok_accounts", [])
        self._tiktok_active: str = self._config.get("tiktok_active_account", "")

        # Account bar
        tk_bar = ttk.Frame(parent, padding=(6, 3))
        tk_bar.pack(fill="x", side="top")
        ttk.Label(tk_bar, text="TikTok Account:").pack(side="left")
        self.tk_account_var = tk.StringVar(value=self._tiktok_active)
        self.tk_account_combo = ttk.Combobox(
            tk_bar, textvariable=self.tk_account_var,
            values=self._tiktok_accounts, width=22, state="readonly",
        )
        self.tk_account_combo.pack(side="left", padx=(4, 2))
        self.tk_account_combo.bind("<<ComboboxSelected>>", self._on_tk_account_selected)
        ttk.Button(tk_bar, text="+ Add Account", command=self._tk_add_account).pack(
            side="left", padx=2
        )
        ttk.Button(tk_bar, text="✕ Remove", command=self._tk_remove_account).pack(
            side="left", padx=2
        )

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=4)

        # Sub-notebook
        tk_nb = ttk.Notebook(parent)
        tk_nb.pack(fill="both", expand=True, padx=4, pady=(2, 4))

        self.tk_manage_tab = TikTokManageTab(
            tk_nb, get_token=lambda: self._tiktok_token, config=self._config
        )
        tk_nb.add(self.tk_manage_tab, text="📋  Manage Videos")

        self.tk_upload_tab = TikTokUploadTab(
            tk_nb, get_token=lambda: self._tiktok_token, config=self._config
        )
        tk_nb.add(self.tk_upload_tab, text="⬆  Upload Short")

        # Load token for active account if one is set
        if self._tiktok_active and self._tiktok_active in self._tiktok_accounts:
            self.after(200, lambda: self._tk_load_token(self._tiktok_active, silent=True))

    # ------------------------------------------------------------------
    # TikTok account management
    # ------------------------------------------------------------------
    def _on_tk_account_selected(self, _event=None):
        label = self.tk_account_var.get()
        if label != self._tiktok_active:
            self._tk_load_token(label)

    def _tk_load_token(self, label: str, silent: bool = False):
        secrets_path = self._config.get("tiktok_client_secrets_path", "tiktok_client_secrets.json")
        if not silent:
            self._tk_log(f"Authenticating '{label}'…")

        def worker():
            try:
                token = tiktok_auth.load_credentials(label, secrets_path)
                self.after(0, lambda t=token: self._tk_apply_token(label, t))
            except Exception as exc:
                self.after(0, lambda e=exc: self._tk_log(f"Auth failed: {e}", error=True))

        threading.Thread(target=worker, daemon=True).start()

    def _tk_apply_token(self, label: str, token: dict):
        self._tiktok_token = token
        self._tiktok_active = label
        self._config["tiktok_active_account"] = label
        self.tk_account_var.set(label)
        self._save_config()
        self._tk_log(f"Signed in as '{label}'.")
        self.tk_manage_tab.load_videos()

    def _tk_add_account(self):
        label = simpledialog.askstring(
            "Add TikTok Account", "Enter a name for this TikTok account:", parent=self
        )
        if not label:
            return
        label = label.strip()
        if label in self._tiktok_accounts:
            messagebox.showerror("Duplicate", f"Account '{label}' already exists.")
            return
        secrets_path = self._config.get("tiktok_client_secrets_path", "tiktok_client_secrets.json")
        self._tk_log(f"Starting TikTok OAuth for '{label}' — check your browser…")

        def worker():
            try:
                token = tiktok_auth.add_account(label, secrets_path)
                self.after(0, lambda t=token: self._tk_finish_add(label, t))
            except Exception as exc:
                self.after(0, lambda e=exc: self._tk_log(f"OAuth failed: {e}", error=True))

        threading.Thread(target=worker, daemon=True).start()

    def _tk_finish_add(self, label: str, token: dict):
        self._tiktok_accounts.append(label)
        self._config["tiktok_accounts"] = self._tiktok_accounts
        self.tk_account_combo["values"] = self._tiktok_accounts
        self._save_config()
        self._tk_log(f"Account '{label}' added.")
        self._tk_apply_token(label, token)

    def _tk_remove_account(self):
        label = self.tk_account_var.get()
        if not label:
            return
        if len(self._tiktok_accounts) <= 1:
            messagebox.showerror("Cannot Remove", "At least one account must remain.")
            return
        if not messagebox.askyesno(
            "Remove TikTok Account", f"Remove '{label}' and delete its saved token?"
        ):
            return
        tiktok_auth.remove_account(label)
        self._tiktok_accounts.remove(label)
        self._config["tiktok_accounts"] = self._tiktok_accounts
        new_active = self._tiktok_accounts[0]
        self.tk_account_combo["values"] = self._tiktok_accounts
        self._save_config()
        self._tk_log(f"Removed '{label}'.")
        self._tk_load_token(new_active)

    def _tk_log(self, msg: str, error: bool = False):
        """Write to the TikTok manage tab log (best-effort)."""
        try:
            self.tk_manage_tab._log(msg, error=error)
        except Exception:
            pass

    def _on_settings_change(self):
        """Called when settings panel saves a preset — also refresh upload tabs."""
        self._save_config()
        self.upload_tab.refresh_presets()
        self.bulk_upload_tab.refresh_presets()

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------
    def _on_account_selected(self, _event=None):
        label = self.account_var.get()
        if label == self._config.get("active_account"):
            return
        self._switch_account(label)

    def _switch_account(self, label: str):
        self._log(f"Switching to account '{label}'…")
        secrets_path = self._config.get("client_secrets_path", "client_secrets.json")

        def worker():
            try:
                creds = load_credentials(label, secrets_path)
                service = build_service(creds)
                self.after(0, lambda: self._apply_account_switch(label, creds, service))
            except Exception as exc:
                self.after(0, lambda e=exc: self._log(
                    f"Failed to switch account: {e}", error=True
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_account_switch(self, label: str, creds, service):
        self._creds = creds
        self._service = service
        self._config["active_account"] = label
        self.account_var.set(label)
        self._save_config()
        self._log(f"Switched to '{label}'.")
        self._load_videos()

    def _add_account(self):
        label = simpledialog.askstring(
            "Add Account",
            "Enter a name for the new YouTube account:",
            parent=self,
        )
        if not label:
            return
        label = label.strip()
        if not label:
            return
        if label in self._config.get("accounts", []):
            messagebox.showerror("Duplicate", f"Account '{label}' already exists.")
            return

        secrets_path = self._config.get("client_secrets_path", "client_secrets.json")
        self._log(f"Starting OAuth for '{label}' — check your browser…")

        def worker():
            try:
                creds = add_account(label, secrets_path)
                service = build_service(creds)
                self.after(0, lambda: self._finish_add_account(label, creds, service))
            except Exception as exc:
                self.after(0, lambda e=exc: self._log(
                    f"OAuth failed for '{label}': {e}", error=True
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_add_account(self, label: str, creds, service):
        self._config.setdefault("accounts", []).append(label)
        self.account_combo["values"] = self._config["accounts"]
        self._save_config()
        self._log(f"Account '{label}' added.")
        self._apply_account_switch(label, creds, service)

    def _remove_account(self):
        label = self.account_var.get()
        if not label:
            return
        accounts = self._config.get("accounts", [])
        if len(accounts) <= 1:
            messagebox.showerror(
                "Cannot Remove", "At least one account must remain."
            )
            return
        if not messagebox.askyesno(
            "Remove Account",
            f"Remove '{label}' and delete its saved token?",
        ):
            return

        remove_account(label)
        accounts.remove(label)
        self._config["accounts"] = accounts

        # Switch to the first remaining account
        new_active = accounts[0]
        self._config["active_account"] = new_active
        self.account_combo["values"] = accounts
        self._save_config()
        self._log(f"Removed '{label}'. Switching to '{new_active}'…")
        self._switch_account(new_active)

    # ------------------------------------------------------------------
    # Load videos
    # ------------------------------------------------------------------
    def _load_videos(self):
        active = self._config.get("active_account", "")
        self.title(f"YouTube Shorts Manager — {active}" if active else "YouTube Shorts Manager")
        self._log("Fetching videos…")
        self.progress_var.set(0)

        try:
            limit = int(self.load_limit_var.get())
        except ValueError:
            limit = 25

        def worker():
            try:
                videos = fetch_my_videos(self._service, limit=limit)
                self.after(0, lambda: self._on_videos_loaded(videos))
            except Exception as exc:
                self.after(0, lambda e=exc: self._log(
                    f"ERROR fetching videos: {e}", error=True
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _on_videos_loaded(self, videos: list[dict]):
        self._videos = videos
        self.video_table.load_videos(videos)
        self._log(f"Loaded {len(videos)} video(s).")
        self.progress_var.set(0)

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------
    def _on_video_select(self, idx: int, video: dict):
        self.settings_panel.load_video(video)

    # ------------------------------------------------------------------
    # Auto-schedule
    # ------------------------------------------------------------------
    def _auto_schedule(self):
        checked = self.video_table.get_checked_indices()
        if not checked:
            messagebox.showinfo("Auto-Schedule", "No videos checked.")
            return

        start = datetime.combine(self._bulk_date_picker.get_date(), datetime.min.time())
        slots = generate_slots(
            start_date=start,
            count=len(checked),
            schedule_times=self._config.get("schedule_times", ["07:00", "21:00"]),
            timezone=self._config.get("timezone", "America/Los_Angeles"),
        )

        for i, idx in enumerate(checked):
            video = self._videos[idx]
            self.settings_panel.set_schedule(slots[i])
            video.setdefault("status", {})["publishAt"] = slots[i]

        self.video_table.load_videos(self._videos)
        self._log(f"Assigned {len(slots)} slot(s) starting "
                  f"{self._bulk_date_picker.get_date().strftime('%Y-%m-%d')}.")

    def _apply_schedule_date(self):
        """Apply the same date/time to all checked videos."""
        checked = self.video_table.get_checked_indices()
        if not checked:
            messagebox.showinfo("Schedule Date", "No videos checked.")
            return

        date_str = self._sched_date_picker.get().strip()
        if not date_str:
            messagebox.showerror("Schedule Date", "Please select a date.")
            return

        try:
            time_str = f"{self._sched_hour.get()}:{self._sched_min.get()}"
            tz = pytz.timezone(self._config.get("timezone", "America/Los_Angeles"))
            naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            publish_at = tz.localize(naive, is_dst=None).astimezone(pytz.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except Exception as exc:
            messagebox.showerror("Schedule Date", f"Invalid date/time: {exc}")
            return

        for idx in checked:
            video = self._videos[idx]
            video.setdefault("status", {})["publishAt"] = publish_at

        # Refresh panel if one of the updated videos is currently open
        self.settings_panel.set_schedule(publish_at)
        self.video_table.load_videos(self._videos)
        self._log(f"Set {len(checked)} video(s) to {date_str} {time_str} (local).")

    # ------------------------------------------------------------------
    # Apply & Save
    # ------------------------------------------------------------------
    def _apply_save(self):
        checked_indices = self.video_table.get_checked_indices()
        if not checked_indices:
            messagebox.showinfo("Apply & Save", "No videos checked.")
            return

        dry = self._dry_run.get()
        if dry:
            self._log("--- DRY RUN (no API calls) ---")

        updates = []
        for idx in checked_indices:
            video = self._videos[idx]
            vid_id = video["id"]
            snippet = video.get("snippet", {})
            status = video.get("status", {})

            updates.append({
                "video_id": vid_id,
                "existing_video": video,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "tags": snippet.get("tags", self._config.get("default_tags", [])),
                "publish_at": status.get("publishAt"),
                "privacy_status": status.get("privacyStatus", "private"),
                "category_id": str(snippet.get("categoryId", "20")),
                "default_language": snippet.get("defaultLanguage"),
                "default_audio_language": snippet.get("defaultAudioLanguage"),
                "license": status.get("license", "youtube"),
                "embeddable": status.get("embeddable", True),
                "made_for_kids": status.get("selfDeclaredMadeForKids", False),
                "contains_synthetic_media": status.get("containsSyntheticMedia", False),
                "public_stats_viewable": status.get("publicStatsViewable", False),
            })

        # If one video is checked and it's currently open in the panel, use panel values
        panel_vals = self.settings_panel.get_values()
        if panel_vals.get("video_id") and len(updates) == 1:
            if updates[0]["video_id"] == panel_vals["video_id"]:
                existing = updates[0]["existing_video"]
                updates[0].update(panel_vals)
                updates[0]["existing_video"] = existing

        total = len(updates)
        self.progress_var.set(0)
        self._log(f"Starting batch update of {total} video(s)…")

        def progress_cb(done, total, vid_id, success, error):
            pct = done / total * 100
            self.after(0, lambda: self.progress_var.set(pct))
            if success:
                self.after(0, lambda v=vid_id: self._log(f"✓ {v}"))
                self.after(0, lambda v=vid_id: self.video_table.set_row_status(v, "saved", "#00aa00"))
            else:
                self.after(0, lambda v=vid_id, e=error: self._log(f"✗ {v}: {e}", error=True))
                self.after(0, lambda v=vid_id: self.video_table.set_row_status(v, "error", "#cc0000"))

        def worker():
            try:
                results = batch_update_videos(
                    self._service, updates, dry_run=dry, progress_callback=progress_cb
                )
                ok = sum(1 for r in results if r["success"])
                self.after(0, lambda: self._log(f"Done: {ok}/{total} succeeded."))
            except Exception as exc:
                self.after(0, lambda e=exc: self._log(f"Batch error: {e}", error=True))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Copy schedule
    # ------------------------------------------------------------------
    def _copy_schedule(self):
        checked_indices = self.video_table.get_checked_indices()
        if not checked_indices:
            messagebox.showinfo("Copy Schedule", "No videos checked.")
            return

        titles, slots = [], []
        for idx in checked_indices:
            video = self._videos[idx]
            publish_at = video.get("status", {}).get("publishAt", "")
            if publish_at:
                titles.append(video.get("snippet", {}).get("title", "(no title)"))
                slots.append(publish_at)

        if not slots:
            messagebox.showinfo("Copy Schedule", "No scheduled times found on checked videos.")
            return

        summary = format_schedule_summary(
            titles, slots, self._config.get("timezone", "America/Los_Angeles")
        )
        self.clipboard_clear()
        self.clipboard_append(summary)
        self._log("Schedule copied to clipboard.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _log(self, msg: str, error: bool = False):
        self.log_text.configure(state="normal")
        self.log_text.tag_configure("error", foreground="#cc0000")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n", "error" if error else "")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _save_config(self):
        try:
            CONFIG_PATH.write_text(json.dumps(self._config, indent=2))
            if self._on_config_change:
                self._on_config_change()
        except Exception as exc:
            self._log(f"Config save failed: {exc}", error=True)
