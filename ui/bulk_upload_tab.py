"""Bulk upload tab — select multiple files, unique titles, shared settings."""

import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import pytz

from youtube_api import upload_video
from ui.settings_panel import CATEGORIES, CATEGORY_NAMES
from ui.widgets import DateEntry

VIDEO_FILETYPES = [
    ("Video files", "*.mp4 *.mov *.avi *.mkv *.webm *.flv *.wmv *.mpeg *.mpg *.m4v"),
    ("All files", "*.*"),
]


class BulkUploadTab(ttk.Frame):
    def __init__(self, parent, get_service, config: dict, log_callback=None):
        super().__init__(parent)
        self._get_service = get_service
        self._config = config
        self._external_log = log_callback
        self._uploading = False
        self._files: list[dict] = []   # {"path": str, "title_var": StringVar, "row": Frame}
        self._build()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build(self):
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        paned = ttk.PanedWindow(self, orient="vertical")
        paned.grid(row=0, column=0, sticky="nsew")

        # ── Top: file list ────────────────────────────────────────────
        file_frame = ttk.LabelFrame(paned, text="Files to Upload", padding=(6, 4))
        paned.add(file_frame, weight=1)
        self._build_file_list(file_frame)

        # ── Bottom: shared settings (left) + controls (right) ─────────
        bottom = ttk.Frame(paned)
        paned.add(bottom, weight=2)
        bottom.rowconfigure(0, weight=1)
        bottom.columnconfigure(0, weight=3)
        bottom.columnconfigure(1, weight=1)

        settings_outer = ttk.LabelFrame(bottom, text="Shared Settings", padding=(6, 4))
        settings_outer.grid(row=0, column=0, sticky="nsew", padx=(6, 3), pady=6)
        settings_outer.rowconfigure(0, weight=1)
        settings_outer.columnconfigure(0, weight=1)
        self._build_settings(settings_outer)

        right = ttk.Frame(bottom)
        right.grid(row=0, column=1, sticky="nsew", padx=(3, 6), pady=6)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        self._upload_btn = ttk.Button(right, text="⬆  Upload All", command=self._start_upload)
        self._upload_btn.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        log_frame = ttk.LabelFrame(right, text="Upload Log", padding=4)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self._log_text = tk.Text(log_frame, state="disabled", wrap="word", font=("Courier", 9))
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

    # ------------------------------------------------------------------
    # File list
    # ------------------------------------------------------------------
    def _build_file_list(self, parent):
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        # Toolbar
        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Button(toolbar, text="+ Add Files", command=self._add_files).pack(side="left", padx=2)
        ttk.Button(toolbar, text="✕ Clear All", command=self._clear_files).pack(side="left", padx=2)
        ttk.Label(
            toolbar,
            text="Each file gets its own title; all other settings are shared.",
            foreground="#666666",
        ).pack(side="left", padx=(12, 0))

        # Scrollable rows
        container = ttk.Frame(parent)
        container.grid(row=1, column=0, sticky="nsew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        self._file_canvas = tk.Canvas(
            container, borderwidth=0, highlightthickness=0, height=120
        )
        vsb = ttk.Scrollbar(container, orient="vertical", command=self._file_canvas.yview)
        self._file_canvas.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        self._file_canvas.grid(row=0, column=0, sticky="nsew")

        self._file_inner = ttk.Frame(self._file_canvas)
        self._file_win_id = self._file_canvas.create_window(
            (0, 0), window=self._file_inner, anchor="nw"
        )
        self._file_inner.bind("<Configure>", lambda e: self._file_canvas.configure(
            scrollregion=self._file_canvas.bbox("all")
        ))
        self._file_canvas.bind("<Configure>", lambda e: self._file_canvas.itemconfig(
            self._file_win_id, width=e.width
        ))

        # Column headers
        hdr = ttk.Frame(self._file_inner)
        hdr.pack(fill="x", padx=4, pady=(0, 2))
        ttk.Label(hdr, text="Filename", width=35, font=("", 9, "bold")).pack(side="left")
        ttk.Label(hdr, text="Title  (edit per file)", font=("", 9, "bold")).pack(
            side="left", padx=(4, 0)
        )

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select Video Files", filetypes=VIDEO_FILETYPES
        )
        for path in paths:
            # Skip duplicates
            if any(f["path"] == path for f in self._files):
                continue
            self._add_file_row(path)

    def _add_file_row(self, path: str):
        title_var = tk.StringVar(value=Path(path).stem)
        row = ttk.Frame(self._file_inner)
        row.pack(fill="x", padx=4, pady=1)

        ttk.Label(row, text=Path(path).name, width=35, anchor="w").pack(side="left")
        ttk.Entry(row, textvariable=title_var).pack(side="left", fill="x", expand=True, padx=(4, 4))
        ttk.Button(
            row, text="✕", width=2,
            command=lambda r=row, p=path: self._remove_file(r, p),
        ).pack(side="right")

        self._files.append({"path": path, "title_var": title_var, "row": row})

    def _remove_file(self, row_frame: ttk.Frame, path: str):
        self._files = [f for f in self._files if f["path"] != path]
        row_frame.destroy()

    def _clear_files(self):
        for entry in self._files:
            entry["row"].destroy()
        self._files.clear()

    # ------------------------------------------------------------------
    # Shared settings form
    # ------------------------------------------------------------------
    def _build_settings(self, parent):
        canvas = tk.Canvas(parent, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        f = ttk.Frame(canvas)
        fid = canvas.create_window((0, 0), window=f, anchor="nw")
        f.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(fid, width=e.width))

        def _scroll(event, c=canvas):
            if (c.winfo_rootx() <= event.x_root < c.winfo_rootx() + c.winfo_width()
                    and c.winfo_rooty() <= event.y_root < c.winfo_rooty() + c.winfo_height()):
                c.yview_scroll(int(-1 * event.delta / 120), "units")
        canvas.bind_all("<MouseWheel>", _scroll, add=True)

        r = 0

        def lbl(text, row, col=0, **kw):
            ttk.Label(f, text=text).grid(row=row, column=col, sticky="w", pady=2, **kw)

        # ── Description ───────────────────────────────────────────────
        lbl("Description:", r)
        self.desc_text = tk.Text(f, width=48, height=4, wrap="word")
        self.desc_text.grid(row=r, column=1, columnspan=4, sticky="ew", padx=(4, 0))
        ttk.Scrollbar(f, command=self.desc_text.yview).grid(row=r, column=5, sticky="ns")
        r += 1

        # ── Tags ──────────────────────────────────────────────────────
        lbl("Tags:", r)
        self.tags_text = tk.Text(f, width=48, height=2, wrap="word")
        self.tags_text.grid(row=r, column=1, columnspan=4, sticky="ew", padx=(4, 0))
        ttk.Scrollbar(f, command=self.tags_text.yview).grid(row=r, column=5, sticky="ns")
        self.tags_text.insert("1.0", ", ".join(self._config.get("default_tags", [])))

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
            width=22, state="readonly",
        ).grid(row=r, column=1, columnspan=2, sticky="w", padx=(4, 0))
        lbl("Privacy:", r, 3, padx=(8, 0))
        self.privacy_var = tk.StringVar(value="private")
        ttk.Combobox(
            f, textvariable=self.privacy_var,
            values=["private", "scheduled", "unlisted", "public"],
            width=10, state="readonly",
        ).grid(row=r, column=4, sticky="w", padx=(4, 0))
        r += 1

        # ── License + Language ────────────────────────────────────────
        lbl("License:", r)
        self.license_var = tk.StringVar(value="youtube")
        ttk.Combobox(
            f, textvariable=self.license_var,
            values=["youtube", "creativeCommon"],
            width=16, state="readonly",
        ).grid(row=r, column=1, columnspan=2, sticky="w", padx=(4, 0))
        lbl("Language:", r, 3, padx=(8, 0))
        self.lang_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.lang_var, width=8).grid(
            row=r, column=4, sticky="w", padx=(4, 0)
        )
        lbl("(e.g. en)", r, 5, padx=(2, 0))
        r += 1

        # ── Audio language ────────────────────────────────────────────
        lbl("Audio Lang:", r)
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

        # ── Schedule ──────────────────────────────────────────────────
        lbl("Schedule Date:", r)
        self.date_picker = DateEntry(
            f, width=12, date_pattern="yyyy-mm-dd",
            background="darkblue", foreground="white", borderwidth=2,
        )
        self.date_picker.grid(row=r, column=1, sticky="w", padx=(4, 0))
        self.date_picker.delete(0, "end")
        lbl("Time:", r, 2, padx=(8, 0))
        self._hour_var = tk.StringVar(value="07")
        self._min_var  = tk.StringVar(value="00")
        ttk.Spinbox(
            f, textvariable=self._hour_var,
            values=[f"{h:02d}" for h in range(24)],
            width=3, wrap=True, state="readonly",
        ).grid(row=r, column=3, sticky="w", padx=(4, 0))
        lbl(":", r, 4)
        ttk.Spinbox(
            f, textvariable=self._min_var,
            values=["00","05","10","15","20","25","30","35","40","45","50","55"],
            width=3, wrap=True, state="readonly",
        ).grid(row=r, column=5, sticky="w")
        lbl("(local tz — blank = immediate)", r, 6, padx=(6, 0))
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
        ttk.Checkbutton(chk, text="Notify Subscribers", variable=self.notify_var).pack(side="left")

        f.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------
    # Presets
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

    def refresh_presets(self):
        self._refresh_presets()

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------
    def _build_publish_at(self) -> str | None:
        date_str = self.date_picker.get().strip()
        if not date_str:
            return None
        try:
            time_str = f"{self._hour_var.get()}:{self._min_var.get()}"
            tz = pytz.timezone(self._config.get("timezone", "America/Los_Angeles"))
            naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            return tz.localize(naive, is_dst=None).astimezone(pytz.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except Exception:
            return None

    def _start_upload(self):
        if self._uploading:
            return

        # Validate
        to_upload = []
        for entry in self._files:
            path = entry["path"]
            title = entry["title_var"].get().strip()
            if not Path(path).is_file():
                messagebox.showerror("Missing File", f"File not found:\n{path}")
                return
            if not title:
                messagebox.showerror(
                    "Missing Title", f"Please enter a title for:\n{Path(path).name}"
                )
                return
            to_upload.append({"path": path, "title": title})

        if not to_upload:
            messagebox.showinfo("No Files", "Add at least one video file.")
            return

        privacy = self.privacy_var.get()
        publish_at = self._build_publish_at()

        # "scheduled" is a UI alias for private + publish_at
        if privacy == "scheduled":
            if not publish_at:
                messagebox.showerror(
                    "Schedule Required",
                    "Please set a Schedule Date/Time when using 'scheduled' privacy.",
                )
                return
            privacy = "private"

        tags = [t.strip() for t in self.tags_text.get("1.0", "end").strip().split(",") if t.strip()]
        shared = dict(
            description=self.desc_text.get("1.0", "end").rstrip("\n"),
            tags=tags,
            category_id=CATEGORIES.get(self.category_var.get(), "20"),
            privacy_status=privacy,
            publish_at=publish_at,
            default_language=self.lang_var.get().strip() or None,
            default_audio_language=self.audio_lang_var.get().strip() or None,
            license=self.license_var.get(),
            embeddable=self.embeddable_var.get(),
            made_for_kids=self.made_for_kids_var.get(),
            contains_synthetic_media=self.synthetic_media_var.get(),
            public_stats_viewable=self.public_stats_var.get(),
            notify_subscribers=self.notify_var.get(),
        )

        self._uploading = True
        self._upload_btn.configure(state="disabled")
        self._progress_var.set(0)
        self._log(f"Starting bulk upload — {len(to_upload)} file(s)…")

        def worker():
            service = self._get_service()
            total = len(to_upload)
            failed = 0
            for i, item in enumerate(to_upload):
                name = Path(item["path"]).name
                self.after(0, lambda n=name, idx=i: self._log(
                    f"[{idx + 1}/{total}] {n}"
                ))

                def progress_cb(pct, i=i):
                    overall = (i + pct / 100) / total * 100
                    self.after(0, lambda p=overall: self._set_progress(p))

                try:
                    result = upload_video(
                        service=service,
                        file_path=item["path"],
                        title=item["title"],
                        progress_callback=progress_cb,
                        **shared,
                    )
                    vid_id = result.get("id", "?")
                    self.after(0, lambda n=name, v=vid_id: self._log(f"  ✓ id={v}  {n}"))
                except Exception as exc:
                    failed += 1
                    self.after(0, lambda n=name, e=exc: self._log(
                        f"  ✗ {n}: {e}", error=True
                    ))

            ok = total - failed
            self.after(0, lambda: self._set_progress(100))
            self.after(0, lambda: self._log(
                f"Done — {ok}/{total} succeeded." + (f"  {failed} failed." if failed else "")
            ))
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
        if self._external_log:
            self._external_log(msg, error)
