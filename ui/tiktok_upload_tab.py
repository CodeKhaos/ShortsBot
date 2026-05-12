"""TikTok — upload tab with all available Content Posting API v2 fields."""

import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import pytz

from tiktok_api import upload_video, get_publish_status, query_creator_info

PRIVACY_OPTIONS = [
    "SELF_ONLY",
    "MUTUAL_FOLLOW_FRIENDS",
    "FOLLOWER_OF_CREATOR",
    "PUBLIC_TO_EVERYONE",
]
PRIVACY_LABELS = {
    "SELF_ONLY": "Private (only me)",
    "MUTUAL_FOLLOW_FRIENDS": "Friends",
    "FOLLOWER_OF_CREATOR": "Followers",
    "PUBLIC_TO_EVERYONE": "Public",
}
VIDEO_FILETYPES = [
    ("Video files", "*.mp4 *.mov *.avi *.mkv *.webm *.flv *.wmv *.mpeg *.mpg *.m4v"),
    ("All files", "*.*"),
]


class TikTokUploadTab(ttk.Frame):
    def __init__(self, parent, get_token, config: dict):
        super().__init__(parent)
        self._get_token = get_token
        self._config = config
        self._uploading = False
        self._creator_info: dict = {}
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build(self):
        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # ── Left: scrollable form ─────────────────────────────────────
        form_outer = ttk.LabelFrame(self, text="Video Details", padding=(6, 4))
        form_outer.grid(row=0, column=0, sticky="nsew", padx=(6, 3), pady=6)
        form_outer.rowconfigure(0, weight=1)
        form_outer.columnconfigure(0, weight=1)

        canvas = tk.Canvas(form_outer, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(form_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._form = ttk.Frame(canvas)
        fid = canvas.create_window((0, 0), window=self._form, anchor="nw")
        self._form.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(fid, width=e.width))
        def _scroll(event, c=canvas):
            if (c.winfo_rootx() <= event.x_root < c.winfo_rootx() + c.winfo_width()
                    and c.winfo_rooty() <= event.y_root < c.winfo_rooty() + c.winfo_height()):
                c.yview_scroll(int(-1 * event.delta / 120), "units")
        canvas.bind_all("<MouseWheel>", _scroll, add=True)

        self._build_form()

        # ── Right: controls, log, progress ───────────────────────────
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(3, 6), pady=6)
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        ttk.Button(
            right, text="📋 Fetch Account Settings", command=self._fetch_creator_info
        ).grid(row=0, column=0, sticky="ew", pady=(0, 4))

        self._upload_btn = ttk.Button(
            right, text="⬆  Upload to TikTok", command=self._start_upload
        )
        self._upload_btn.grid(row=1, column=0, sticky="ew", pady=(0, 4))

        log_frame = ttk.LabelFrame(right, text="Upload Log", padding=4)
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self._log_text = tk.Text(
            log_frame, state="disabled", wrap="word", font=("Courier", 9)
        )
        log_sb = ttk.Scrollbar(log_frame, command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_sb.set)
        self._log_text.grid(row=0, column=0, sticky="nsew")
        log_sb.grid(row=0, column=1, sticky="ns")

        self._progress_var = tk.DoubleVar(value=0)
        self._progress_lbl = tk.StringVar(value="")
        ttk.Label(right, textvariable=self._progress_lbl).grid(
            row=3, column=0, sticky="w", pady=(4, 0)
        )
        ttk.Progressbar(
            right, variable=self._progress_var, maximum=100, mode="determinate"
        ).grid(row=4, column=0, sticky="ew", pady=(2, 0))

    def _build_form(self):
        f = self._form
        r = 0

        def lbl(text, row, col=0, **kw):
            ttk.Label(f, text=text).grid(row=row, column=col, sticky="w", pady=2, **kw)

        # ── File picker ───────────────────────────────────────────────
        lbl("Video File: *", r)
        self.video_path_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.video_path_var, width=44).grid(
            row=r, column=1, columnspan=3, sticky="ew", padx=(4, 0)
        )
        ttk.Button(f, text="Browse…", command=self._pick_video).grid(
            row=r, column=4, padx=(4, 0)
        )
        r += 1

        ttk.Separator(f, orient="horizontal").grid(
            row=r, column=0, columnspan=5, sticky="ew", pady=6
        )
        r += 1

        # ── Title / Caption ───────────────────────────────────────────
        lbl("Title / Caption: *", r)
        self.title_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.title_var, width=44).grid(
            row=r, column=1, columnspan=4, sticky="ew", padx=(4, 0)
        )
        lbl("(max 2200 chars)", r, 5, padx=(4, 0))
        r += 1

        ttk.Separator(f, orient="horizontal").grid(
            row=r, column=0, columnspan=6, sticky="ew", pady=6
        )
        r += 1

        # ── Privacy ───────────────────────────────────────────────────
        lbl("Privacy:", r)
        self.privacy_var = tk.StringVar(value="SELF_ONLY")
        privacy_combo = ttk.Combobox(
            f, textvariable=self.privacy_var,
            values=[f"{PRIVACY_LABELS[p]}  ({p})" for p in PRIVACY_OPTIONS],
            width=34, state="readonly",
        )
        privacy_combo.current(0)
        privacy_combo.grid(row=r, column=1, columnspan=3, sticky="w", padx=(4, 0))
        # Store raw values for retrieval
        self._privacy_display = [f"{PRIVACY_LABELS[p]}  ({p})" for p in PRIVACY_OPTIONS]
        r += 1

        # ── Thumbnail timestamp ───────────────────────────────────────
        lbl("Cover Timestamp:", r)
        self.cover_ts_var = tk.StringVar(value="0")
        ttk.Entry(f, textvariable=self.cover_ts_var, width=10).grid(
            row=r, column=1, sticky="w", padx=(4, 0)
        )
        lbl("ms (0 = auto)", r, 2, padx=(4, 0))
        r += 1

        ttk.Separator(f, orient="horizontal").grid(
            row=r, column=0, columnspan=6, sticky="ew", pady=6
        )
        r += 1

        # ── Interaction toggles ───────────────────────────────────────
        lbl("Disable:", r)
        tog_frame = ttk.Frame(f)
        tog_frame.grid(row=r, column=1, columnspan=4, sticky="w", padx=(4, 0))

        self.disable_duet_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tog_frame, text="Duet", variable=self.disable_duet_var).pack(
            side="left", padx=(0, 10)
        )
        self.disable_comment_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tog_frame, text="Comments", variable=self.disable_comment_var).pack(
            side="left", padx=(0, 10)
        )
        self.disable_stitch_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tog_frame, text="Stitch", variable=self.disable_stitch_var).pack(
            side="left"
        )
        r += 1

        ttk.Separator(f, orient="horizontal").grid(
            row=r, column=0, columnspan=6, sticky="ew", pady=6
        )
        r += 1

        # ── Disclosure / content labels ───────────────────────────────
        lbl("Content Disclosure:", r)
        disc_frame = ttk.Frame(f)
        disc_frame.grid(row=r, column=1, columnspan=4, sticky="w", padx=(4, 0))

        self.brand_content_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            disc_frame, text="Paid Partnership (brand_content)",
            variable=self.brand_content_var,
            command=self._on_brand_content_toggle,
        ).pack(anchor="w")

        self.brand_organic_var = tk.BooleanVar(value=False)
        self._brand_organic_chk = ttk.Checkbutton(
            disc_frame, text="Branded Organic Content (brand_organic)",
            variable=self.brand_organic_var,
        )
        self._brand_organic_chk.pack(anchor="w")

        self.aigc_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            disc_frame, text="AI-Generated Content (is_aigc)",
            variable=self.aigc_var,
        ).pack(anchor="w")
        r += 1

        f.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------
    # Creator info preflight
    # ------------------------------------------------------------------
    def _fetch_creator_info(self):
        self._log("Fetching account settings…")

        def worker():
            try:
                token = self._get_token()
                if not token:
                    self.after(0, lambda: self._log("No TikTok account active.", error=True))
                    return
                info = query_creator_info(token)
                self.after(0, lambda i=info: self._apply_creator_info(i))
            except Exception as exc:
                self.after(0, lambda e=exc: self._log(f"Could not fetch settings: {e}", error=True))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_creator_info(self, info: dict):
        self._creator_info = info
        name = info.get("creator_nickname") or info.get("creator_username", "")
        self._log(f"Account: @{name}")

        # Update privacy options to only those the account allows
        allowed = info.get("privacy_level_options", PRIVACY_OPTIONS)
        display = [
            f"{PRIVACY_LABELS.get(p, p)}  ({p})"
            for p in PRIVACY_OPTIONS
            if p in allowed
        ]
        # Find privacy combobox and update
        for widget in self._form.winfo_children():
            if isinstance(widget, ttk.Combobox) and self.privacy_var in (
                widget.cget("textvariable"),
            ):
                widget["values"] = display
                break

        if info.get("duet_disabled"):
            self.disable_duet_var.set(True)
        if info.get("stitch_disabled"):
            self.disable_stitch_var.set(True)
        if info.get("comment_disabled"):
            self.disable_comment_var.set(True)

        max_dur = info.get("max_video_post_duration_sec", 60)
        self._log(f"Max video duration: {max_dur}s")

    # ------------------------------------------------------------------
    # File picker
    # ------------------------------------------------------------------
    def _pick_video(self):
        path = filedialog.askopenfilename(
            title="Select Video File", filetypes=VIDEO_FILETYPES
        )
        if path:
            self.video_path_var.set(path)
            if not self.title_var.get():
                self.title_var.set(Path(path).stem)

    def _on_brand_content_toggle(self):
        # brand_organic must be true when brand_content is true
        if self.brand_content_var.get():
            self.brand_organic_var.set(True)

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------
    def _get_privacy_value(self) -> str:
        display = self.privacy_var.get()
        for p in PRIVACY_OPTIONS:
            if p in display:
                return p
        return "SELF_ONLY"

    def _start_upload(self):
        if self._uploading:
            return

        video_path = self.video_path_var.get().strip()
        if not video_path or not Path(video_path).is_file():
            messagebox.showerror("Missing File", "Please select a valid video file.")
            return
        title = self.title_var.get().strip()
        if not title:
            messagebox.showerror("Missing Title", "Please enter a title / caption.")
            return

        try:
            cover_ts = int(self.cover_ts_var.get().strip() or 0)
        except ValueError:
            cover_ts = 0

        params = dict(
            file_path=video_path,
            title=title,
            privacy_level=self._get_privacy_value(),
            disable_duet=self.disable_duet_var.get(),
            disable_comment=self.disable_comment_var.get(),
            disable_stitch=self.disable_stitch_var.get(),
            video_cover_timestamp_ms=cover_ts,
            brand_content_toggle=self.brand_content_var.get(),
            brand_organic_toggle=self.brand_organic_var.get(),
            is_aigc=self.aigc_var.get(),
        )

        self._uploading = True
        self._upload_btn.configure(state="disabled")
        self._progress_var.set(0)
        self._log(f"Starting upload: {Path(video_path).name}")

        def progress_cb(pct):
            self.after(0, lambda p=pct: self._set_progress(p))

        def worker():
            try:
                token = self._get_token()
                if not token:
                    self.after(0, lambda: self._log("No TikTok account active.", error=True))
                    return

                publish_id = upload_video(
                    token=token, progress_callback=progress_cb, **params
                )
                self.after(0, lambda: self._log(
                    f"Upload complete — polling publish status… (publish_id: {publish_id})"
                ))

                status = get_publish_status(token, publish_id)
                vid_ids = status.get("publicaly_available_post_id", [])
                vid_id = vid_ids[0] if vid_ids else "?"
                self.after(0, lambda v=vid_id: self._log(f"✓ Published! Video ID: {v}"))
                self.after(0, lambda: self._set_progress(100))

            except Exception as exc:
                self.after(0, lambda e=exc: self._log(f"Upload failed: {e}", error=True))
            finally:
                self.after(0, self._upload_done)

        threading.Thread(target=worker, daemon=True).start()

    def _upload_done(self):
        self._uploading = False
        self._upload_btn.configure(state="normal")

    def _set_progress(self, pct: float):
        self._progress_var.set(pct)
        self._progress_lbl.set(f"{pct:.0f}%")

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------
    def _log(self, msg: str, error: bool = False):
        self._log_text.configure(state="normal")
        self._log_text.tag_configure("error", foreground="#cc0000")
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_text.insert("end", f"[{ts}] {msg}\n", "error" if error else "")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")
