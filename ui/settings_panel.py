"""Per-video settings panel — all writable YouTube snippet + status fields."""

import tkinter as tk
from tkinter import ttk
from datetime import datetime, date

from ui.widgets import DateEntry

import pytz

# YouTube video category IDs (name → id)
CATEGORIES = {
    "Film & Animation": "1",
    "Autos & Vehicles": "2",
    "Music": "10",
    "Pets & Animals": "15",
    "Sports": "17",
    "Travel & Events": "19",
    "Gaming": "20",
    "People & Blogs": "22",
    "Comedy": "23",
    "Entertainment": "24",
    "News & Politics": "25",
    "Howto & Style": "26",
    "Education": "27",
    "Science & Technology": "28",
    "Nonprofits & Activism": "29",
}
CATEGORY_NAMES = list(CATEGORIES.keys())
CATEGORY_IDS = {v: k for k, v in CATEGORIES.items()}  # id → name


class SettingsPanel(ttk.LabelFrame):
    def __init__(self, parent, config: dict, on_change=None):
        super().__init__(parent, text="Video Settings", padding=(6, 4))
        self._config = config
        self._on_change = on_change
        self._video_id: str | None = None
        self._build()

    # ------------------------------------------------------------------
    # Build — scrollable inner canvas so all fields are reachable
    # ------------------------------------------------------------------
    def _build(self):
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)

        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._inner = ttk.Frame(canvas)
        self._inner_id = canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")
        ))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(
            self._inner_id, width=e.width
        ))
        # Mouse-wheel scroll — only when pointer is inside this canvas
        def _scroll(event, c=canvas):
            if (c.winfo_rootx() <= event.x_root < c.winfo_rootx() + c.winfo_width()
                    and c.winfo_rooty() <= event.y_root < c.winfo_rooty() + c.winfo_height()):
                c.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _scroll, add=True)

        self._canvas = canvas
        self._build_fields()

    def _build_fields(self):
        f = self._inner
        row = 0

        def lbl(text, r, c, **kw):
            ttk.Label(f, text=text).grid(row=r, column=c, sticky="w", pady=2, **kw)

        # ── Title ──────────────────────────────────────────────────────
        lbl("Title:", row, 0)
        self.title_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.title_var, width=52).grid(
            row=row, column=1, columnspan=5, sticky="ew", padx=(4, 0)
        )
        row += 1

        # ── Description ───────────────────────────────────────────────
        lbl("Description:", row, 0)
        self.desc_text = tk.Text(f, width=52, height=4, wrap="word")
        self.desc_text.grid(row=row, column=1, columnspan=4, sticky="ew", padx=(4, 0))
        ttk.Scrollbar(f, command=self.desc_text.yview).grid(row=row, column=5, sticky="ns")
        self.desc_text.configure(yscrollcommand=lambda *a: None)
        row += 1

        # ── Schedule ──────────────────────────────────────────────────
        lbl("Schedule Date:", row, 0)
        self.date_picker = DateEntry(
            f, width=12, date_pattern="yyyy-mm-dd",
            background="darkblue", foreground="white", borderwidth=2,
        )
        self.date_picker.grid(row=row, column=1, sticky="w", padx=(4, 0))
        self.date_picker.delete(0, "end")   # start blank (no date pre-filled)
        lbl("Time:", row, 2, padx=(8, 0))
        self._hour_var = tk.StringVar(value="07")
        self._min_var  = tk.StringVar(value="00")
        ttk.Spinbox(
            f, textvariable=self._hour_var,
            values=[f"{h:02d}" for h in range(24)],
            width=3, wrap=True, state="readonly",
        ).grid(row=row, column=3, sticky="w", padx=(4, 0))
        lbl(":", row, 4)
        ttk.Spinbox(
            f, textvariable=self._min_var,
            values=["00", "05", "10", "15", "20", "25", "30", "35", "40", "45", "50", "55"],
            width=3, wrap=True, state="readonly",
        ).grid(row=row, column=5, sticky="w")
        lbl("(local tz)", row, 6, padx=(6, 0))
        row += 1

        # ── Category + Privacy ────────────────────────────────────────
        lbl("Category:", row, 0)
        self.category_var = tk.StringVar(value="Gaming")
        ttk.Combobox(
            f, textvariable=self.category_var, values=CATEGORY_NAMES,
            width=22, state="readonly"
        ).grid(row=row, column=1, columnspan=2, sticky="w", padx=(4, 0))

        lbl("Privacy:", row, 3, padx=(8, 0))
        self.privacy_var = tk.StringVar(value="private")
        ttk.Combobox(
            f, textvariable=self.privacy_var,
            values=["private", "scheduled", "unlisted", "public"],
            width=10, state="readonly"
        ).grid(row=row, column=4, sticky="w", padx=(4, 0))
        row += 1

        # ── License + Language ────────────────────────────────────────
        lbl("License:", row, 0)
        self.license_var = tk.StringVar(value="youtube")
        ttk.Combobox(
            f, textvariable=self.license_var,
            values=["youtube", "creativeCommon"],
            width=16, state="readonly"
        ).grid(row=row, column=1, columnspan=2, sticky="w", padx=(4, 0))

        lbl("Default Language:", row, 3, padx=(8, 0))
        self.lang_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.lang_var, width=8).grid(
            row=row, column=4, sticky="w", padx=(4, 0)
        )
        lbl("(e.g. en)", row, 5, padx=(2, 0))
        row += 1

        # ── Audio language ────────────────────────────────────────────
        lbl("Audio Language:", row, 0)
        self.audio_lang_var = tk.StringVar()
        ttk.Entry(f, textvariable=self.audio_lang_var, width=8).grid(
            row=row, column=1, sticky="w", padx=(4, 0)
        )
        lbl("(e.g. en)", row, 2, padx=(2, 0))
        row += 1

        # ── Tags ──────────────────────────────────────────────────────
        lbl("Tags:", row, 0)
        self.tags_text = tk.Text(f, width=52, height=3, wrap="word")
        self.tags_text.grid(row=row, column=1, columnspan=4, sticky="ew", padx=(4, 0))
        ttk.Scrollbar(f, command=self.tags_text.yview).grid(row=row, column=5, sticky="ns")
        self.tags_text.configure(yscrollcommand=lambda *a: None)

        # Preset selector alongside tags
        preset_frame = ttk.Frame(f)
        preset_frame.grid(row=row, column=6, sticky="nw", padx=(8, 0))
        lbl_p = ttk.Label(preset_frame, text="Tag Preset:")
        lbl_p.pack(anchor="w")
        self.preset_var = tk.StringVar(value="default")
        self.preset_combo = ttk.Combobox(
            preset_frame, textvariable=self.preset_var, width=16, state="readonly"
        )
        self.preset_combo.pack(anchor="w")
        self.preset_combo.bind("<<ComboboxSelected>>", self._load_preset)
        self._refresh_presets()
        row += 1

        # ── Checkboxes ────────────────────────────────────────────────
        chk = ttk.Frame(f)
        chk.grid(row=row, column=0, columnspan=7, sticky="w", pady=(6, 2))

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
            side="left"
        )
        row += 1

        # ── Save preset ───────────────────────────────────────────────
        sp = ttk.Frame(f)
        sp.grid(row=row, column=0, columnspan=7, sticky="w", pady=(4, 0))
        ttk.Label(sp, text="Save tags as preset:").pack(side="left")
        self.new_preset_var = tk.StringVar()
        ttk.Entry(sp, textvariable=self.new_preset_var, width=18).pack(side="left", padx=4)
        ttk.Button(sp, text="Save Preset", command=self._save_preset).pack(side="left")

        f.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_video(self, video: dict, default_slot: str | None = None):
        self._video_id = video["id"]
        snippet = video.get("snippet", {})
        status = video.get("status", {})

        self.title_var.set(snippet.get("title", ""))

        self.desc_text.delete("1.0", "end")
        self.desc_text.insert("1.0", snippet.get("description", ""))

        # Category
        cat_id = str(snippet.get("categoryId", "20"))
        self.category_var.set(CATEGORY_IDS.get(cat_id, "Gaming"))

        # Languages
        self.lang_var.set(snippet.get("defaultLanguage", ""))
        self.audio_lang_var.set(snippet.get("defaultAudioLanguage", ""))

        # Tags
        tags = snippet.get("tags", self._config.get("default_tags", []))
        self.tags_text.delete("1.0", "end")
        self.tags_text.insert("1.0", ", ".join(tags))

        # Schedule
        publish_at = status.get("publishAt") or default_slot or ""
        if publish_at:
            try:
                utc_dt = pytz.utc.localize(
                    datetime.strptime(publish_at, "%Y-%m-%dT%H:%M:%SZ")
                )
                tz = pytz.timezone(self._config.get("timezone", "America/Los_Angeles"))
                local_dt = utc_dt.astimezone(tz)
                self.date_picker.set_date(local_dt.date())
                self._hour_var.set(local_dt.strftime("%H"))
                self._min_var.set(local_dt.strftime("%M"))
            except Exception:
                self.date_picker.delete(0, "end")
                self._hour_var.set("07")
                self._min_var.set("00")
        else:
            self.date_picker.delete(0, "end")
            self._hour_var.set("07")
            self._min_var.set("00")

        # Status fields — show "scheduled" when the video is private with a future publish date
        raw_privacy = status.get("privacyStatus", "private")
        if raw_privacy == "private" and status.get("publishAt"):
            self.privacy_var.set("scheduled")
        else:
            self.privacy_var.set(raw_privacy)
        self.license_var.set(status.get("license", "youtube"))
        self.embeddable_var.set(status.get("embeddable", True))
        self.made_for_kids_var.set(status.get("selfDeclaredMadeForKids", False))
        self.synthetic_media_var.set(status.get("containsSyntheticMedia", False))
        self.public_stats_var.set(status.get("publicStatsViewable", False))

    def get_values(self) -> dict:
        tags_raw = self.tags_text.get("1.0", "end").strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

        lang = self.lang_var.get().strip() or None
        audio_lang = self.audio_lang_var.get().strip() or None

        # "scheduled" is a UI alias — the API expects "private" with a publish_at
        privacy = self.privacy_var.get()
        if privacy == "scheduled":
            privacy = "private"

        return {
            "video_id": self._video_id,
            "title": self.title_var.get().strip(),
            "description": self.desc_text.get("1.0", "end").rstrip("\n"),
            "category_id": CATEGORIES.get(self.category_var.get(), "20"),
            "default_language": lang,
            "default_audio_language": audio_lang,
            "tags": tags,
            "publish_at": self._build_publish_at(),
            "privacy_status": privacy,
            "license": self.license_var.get(),
            "embeddable": self.embeddable_var.get(),
            "made_for_kids": self.made_for_kids_var.get(),
            "contains_synthetic_media": self.synthetic_media_var.get(),
            "public_stats_viewable": self.public_stats_var.get(),
        }

    def set_schedule(self, utc_rfc3339: str):
        try:
            utc_dt = pytz.utc.localize(
                datetime.strptime(utc_rfc3339, "%Y-%m-%dT%H:%M:%SZ")
            )
            tz = pytz.timezone(self._config.get("timezone", "America/Los_Angeles"))
            local_dt = utc_dt.astimezone(tz)
            self.date_picker.set_date(local_dt.date())
            self._hour_var.set(local_dt.strftime("%H"))
            # snap minutes to nearest 5
            snap = round(local_dt.minute / 5) * 5
            self._min_var.set(f"{snap % 60:02d}")
        except Exception:
            pass

    def clear(self):
        self._video_id = None
        self.title_var.set("")
        self.desc_text.delete("1.0", "end")
        self.tags_text.delete("1.0", "end")
        self.date_picker.delete(0, "end")
        self._hour_var.set("07")
        self._min_var.set("00")
        self.category_var.set("Gaming")
        self.privacy_var.set("private")
        self.license_var.set("youtube")
        self.lang_var.set("")
        self.audio_lang_var.set("")
        self.embeddable_var.set(True)
        self.made_for_kids_var.set(False)
        self.synthetic_media_var.set(False)
        self.public_stats_var.set(False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_publish_at(self) -> str | None:
        date_str = self.date_picker.get().strip()
        if not date_str:
            return None
        try:
            time_str = f"{self._hour_var.get()}:{self._min_var.get()}"
            tz = pytz.timezone(self._config.get("timezone", "America/Los_Angeles"))
            naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            local_dt = tz.localize(naive, is_dst=None)
            return local_dt.astimezone(pytz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None

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

    def _save_preset(self):
        name = self.new_preset_var.get().strip()
        if not name:
            return
        tags = [
            t.strip()
            for t in self.tags_text.get("1.0", "end").strip().split(",")
            if t.strip()
        ]
        self._config.setdefault("tag_presets", {})[name] = tags
        self._refresh_presets()
        self.new_preset_var.set("")
        if self._on_change:
            self._on_change()
