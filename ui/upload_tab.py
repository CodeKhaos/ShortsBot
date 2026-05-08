"""Upload tab — all fields available on videos.insert."""

import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import pytz

from youtube_api import upload_video, set_thumbnail
from ui.settings_panel import CATEGORIES, CATEGORY_NAMES

# Maps display label → mimetype hint accepted by the file dialog
VIDEO_FILETYPES = [
    ("Video files", "*.mp4 *.mov *.avi *.mkv *.webm *.flv *.wmv *.mpeg *.mpg *.m4v"),
    ("All files", "*.*"),
]
IMAGE_FILETYPES = [
    ("Images", "*.jpg *.jpeg *.png *.webp *.bmp"),
    ("All files", "*.*"),
]


class UploadTab(ttk.Frame):
    def __init__(self, parent, get_service, config: dict, log_callback=None):
        """
        get_service: callable that returns the current youtube service
        log_callback: optional fn(msg, error=False) to write to a shared log
        """
        super().__init__(parent)
        self._get_service = get_service
        self._config = config
        self._external_log = log_callback
        self._uploading = False
        self._build()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build(self):
        # Split: left = scrollable form, right = log + progress
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
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(
            int(-1 * e.delta / 120), "units"))

        self._build_form()

        # ── Right: log + progress + upload button ─────────────────────
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(3, 6), pady=6)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self._upload_btn = ttk.Button(
            right, text="⬆  Upload Video", command=self._start_upload
        )
        self._upload_btn.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        log_frame = ttk.LabelFrame(right, text="Upload Log", padding=4)
        log_frame.grid(row=1, column=0, sticky="nsew")
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
            row=2, column=0, sticky="w", pady=(4, 0)
        )
        ttk.Progressbar(
            right, variable=self._progress_var, maximum=100, mode="determinate"
        ).grid(row=3, column=0, sticky="ew", pady=(2, 0))

    def _build_form(self):
        f = self._form
        r = 0

        def lbl(text, row, col=0, **kw):
            ttk.Label(f, text=text).grid(row=row, column=col, sticky="w", pady=2, **kw)

        # ── File pickers ──────────────────────────────────────────────
        lbl("Video File: *", r)
        self.video_path_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.video_path_var, width=42).grid(
            row=r, column=1, columnspan=3, sticky="ew", padx=(4, 0)
        )
        ttk.Button(f, text="Browse…", command=self._pick_video).grid(
            row=r, column=4, padx=(4, 0)
        )
        r += 1

        lbl("Thumbnail:", r)
        self.thumb_path_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.thumb_path_var, width=42).grid(
            row=r, column=1, columnspan=3, sticky="ew", padx=(4, 0)
        )
        ttk.Button(f, text="Browse…", command=self._pick_thumbnail).grid(
            row=r, column=4, padx=(4, 0)
        )
        lbl("(optional, max 2 MB)", r, 5, padx=(6, 0))
        r += 1

        ttk.Separator(f, orient="horizontal").grid(
            row=r, column=0, columnspan=6, sticky="ew", pady=6
        )
        r += 1

        # ── Title ─────────────────────────────────────────────────────
        lbl("Title: *", r)
        self.title_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.title_var, width=52).grid(
            row=r, column=1, columnspan=4, sticky="ew", padx=(4, 0)
        )
        r += 1

        # ── Description ───────────────────────────────────────────────
        lbl("Description:", r)
        self.desc_text = tk.Text(f, width=52, height=5, wrap="word")
        self.desc_text.grid(row=r, column=1, columnspan=4, sticky="ew", padx=(4, 0))
        ttk.Scrollbar(f, command=self.desc_text.yview).grid(row=r, column=5, sticky="ns")
        r += 1

        # ── Tags ──────────────────────────────────────────────────────
        lbl("Tags:", r)
        self.tags_text = tk.Text(f, width=52, height=3, wrap="word")
        self.tags_text.grid(row=r, column=1, columnspan=4, sticky="ew", padx=(4, 0))
        ttk.Scrollbar(f, command=self.tags_text.yview).grid(row=r, column=5, sticky="ns")
        # Pre-fill with default tags
        default_tags = self._config.get("default_tags", [])
        self.tags_text.insert("1.0", ", ".join(default_tags))

        # Preset selector
        preset_frame = ttk.Frame(f)
        preset_frame.grid(row=r, column=6, sticky="nw", padx=(8, 0))
        ttk.Label(preset_frame, text="Tag Preset:").pack(anchor="w")
        self.preset_var = tk.StringVar(value="default")
        self.preset_combo = ttk.Combobox(
            preset_frame, textvariable=self.preset_var, width=14, state="readonly"
        )
        self.preset_combo.pack(anchor="w")
        self.preset_combo.bind("<<ComboboxSelected>>", self._load_preset)
        self._refresh_presets()
        r += 1

        ttk.Separator(f, orient="horizontal").grid(
            row=r, column=0, columnspan=7, sticky="ew", pady=6
        )
        r += 1

        # ── Category + Privacy ────────────────────────────────────────
        lbl("Category:", r)
        self.category_var = tk.StringVar(value="Gaming")
        ttk.Combobox(
            f, textvariable=self.category_var, values=CATEGORY_NAMES,
            width=22, state="readonly"
        ).grid(row=r, column=1, columnspan=2, sticky="w", padx=(4, 0))
        lbl("Privacy:", r, 3, padx=(8, 0))
        self.privacy_var = tk.StringVar(value="private")
        ttk.Combobox(
            f, textvariable=self.privacy_var,
            values=["private", "unlisted", "public"],
            width=10, state="readonly"
        ).grid(row=r, column=4, sticky="w", padx=(4, 0))
        r += 1

        # ── License + Language ────────────────────────────────────────
        lbl("License:", r)
        self.license_var = tk.StringVar(value="youtube")
        ttk.Combobox(
            f, textvariable=self.license_var,
            values=["youtube", "creativeCommon"],
            width=16, state="readonly"
        ).grid(row=r, column=1, columnspan=2, sticky="w", padx=(4, 0))
        lbl("Default Language:", r, 3, padx=(8, 0))
        self.lang_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.lang_var, width=8).grid(
            row=r, column=4, sticky="w", padx=(4, 0)
        )
        lbl("(e.g. en)", r, 5, padx=(2, 0))
        r += 1

        # ── Audio language ────────────────────────────────────────────
        lbl("Audio Language:", r)
        self.audio_lang_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.audio_lang_var, width=8).grid(
            row=r, column=1, sticky="w", padx=(4, 0)
        )
        lbl("(e.g. en)", r, 2, padx=(2, 0))
        r += 1

        ttk.Separator(f, orient="horizontal").grid(
            row=r, column=0, columnspan=7, sticky="ew", pady=6
        )
        r += 1

        # ── Schedule date / time ──────────────────────────────────────
        lbl("Schedule Date:", r)
        self.date_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.date_var, width=12).grid(
            row=r, column=1, sticky="w", padx=(4, 0)
        )
        lbl("Time (HH:MM):", r, 2, padx=(8, 0))
        self.time_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.time_var, width=8).grid(
            row=r, column=3, sticky="w", padx=(4, 0)
        )
        lbl("(local tz — leave blank for immediate)", r, 4, padx=(6, 0))
        r += 1

        ttk.Separator(f, orient="horizontal").grid(
            row=r, column=0, columnspan=7, sticky="ew", pady=6
        )
        r += 1

        # ── Checkboxes ────────────────────────────────────────────────
        chk = ttk.Frame(f)
        chk.grid(row=r, column=0, columnspan=7, sticky="w", pady=(2, 4))

        self.made_for_kids_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(chk, text="Made for Kids", variable=self.made_for_kids_var).pack(
            side="left", padx=(0, 10)
        )
        self.synthetic_media_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(chk, text="Contains Synthetic Media", variable=self.synthetic_media_var).pack(
            side="left", padx=(0, 10)
        )
        self.public_stats_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(chk, text="publicStatsViewable", variable=self.public_stats_var).pack(
            side="left", padx=(0, 10)
        )
        self.embeddable_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(chk, text="Embeddable", variable=self.embeddable_var).pack(
            side="left", padx=(0, 10)
        )
        self.notify_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(chk, text="Notify Subscribers", variable=self.notify_var).pack(
            side="left"
        )

        f.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------
    # File pickers
    # ------------------------------------------------------------------
    def _pick_video(self):
        path = filedialog.askopenfilename(
            title="Select Video File", filetypes=VIDEO_FILETYPES
        )
        if path:
            self.video_path_var.set(path)
            # Auto-fill title from filename if blank
            if not self.title_var.get():
                self.title_var.set(Path(path).stem)

    def _pick_thumbnail(self):
        path = filedialog.askopenfilename(
            title="Select Thumbnail Image", filetypes=IMAGE_FILETYPES
        )
        if path:
            self.thumb_path_var.set(path)

    # ------------------------------------------------------------------
    # Tag presets
    # ------------------------------------------------------------------
    def _refresh_presets(self):
        self.preset_combo["values"] = ["default"] + list(
            self._config.get("tag_presets", {}).keys()
        )

    def _load_preset(self, _event=None):
        name = self.preset_var.get()
        tags = (
            self._config.get("default_tags", [])
            if name == "default"
            else self._config.get("tag_presets", {}).get(name, [])
        )
        self.tags_text.delete("1.0", "end")
        self.tags_text.insert("1.0", ", ".join(tags))

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------
    def _start_upload(self):
        if self._uploading:
            return

        video_path = self.video_path_var.get().strip()
        if not video_path or not Path(video_path).is_file():
            messagebox.showerror("Missing File", "Please select a valid video file.")
            return
        title = self.title_var.get().strip()
        if not title:
            messagebox.showerror("Missing Title", "Please enter a title.")
            return

        publish_at = self._build_publish_at()
        tags = [t.strip() for t in self.tags_text.get("1.0", "end").strip().split(",") if t.strip()]
        lang = self.lang_var.get().strip() or None
        audio_lang = self.audio_lang_var.get().strip() or None

        params = dict(
            file_path=video_path,
            title=title,
            description=self.desc_text.get("1.0", "end").rstrip("\n"),
            tags=tags,
            category_id=CATEGORIES.get(self.category_var.get(), "20"),
            privacy_status=self.privacy_var.get(),
            publish_at=publish_at,
            default_language=lang,
            default_audio_language=audio_lang,
            license=self.license_var.get(),
            embeddable=self.embeddable_var.get(),
            made_for_kids=self.made_for_kids_var.get(),
            contains_synthetic_media=self.synthetic_media_var.get(),
            public_stats_viewable=self.public_stats_var.get(),
            notify_subscribers=self.notify_var.get(),
        )
        thumb_path = self.thumb_path_var.get().strip() or None

        self._uploading = True
        self._upload_btn.configure(state="disabled")
        self._progress_var.set(0)
        self._log(f"Starting upload: {Path(video_path).name}")

        def progress_cb(pct):
            self.after(0, lambda p=pct: self._set_progress(p))

        def worker():
            try:
                service = self._get_service()
                result = upload_video(service=service, progress_callback=progress_cb, **params)
                video_id = result.get("id", "?")
                self.after(0, lambda: self._log(f"✓ Uploaded — video ID: {video_id}"))

                if thumb_path and Path(thumb_path).is_file():
                    self.after(0, lambda: self._log("Setting thumbnail…"))
                    try:
                        set_thumbnail(service, video_id, thumb_path)
                        self.after(0, lambda: self._log("✓ Thumbnail set."))
                    except Exception as te:
                        self.after(0, lambda e=te: self._log(
                            f"Thumbnail failed: {e}", error=True
                        ))
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

    def _build_publish_at(self) -> str | None:
        date_str = self.date_var.get().strip()
        time_str = self.time_var.get().strip()
        if not date_str or not time_str:
            return None
        try:
            tz = pytz.timezone(self._config.get("timezone", "America/Los_Angeles"))
            naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            local_dt = tz.localize(naive, is_dst=None)
            return local_dt.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None

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
        if self._external_log:
            self._external_log(msg, error)

    def refresh_presets(self):
        """Called by the main app when tag presets change."""
        self._refresh_presets()
