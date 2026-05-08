"""Scrollable video list with thumbnails, checkboxes, and selection callback."""

import io
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime

import pytz
import requests
from PIL import Image, ImageTk


THUMB_W, THUMB_H = 80, 45
PLACEHOLDER_COLOR = "#333333"


class VideoTable(ttk.Frame):
    def __init__(self, parent, on_select=None):
        super().__init__(parent)
        self._on_select = on_select
        self._videos: list[dict] = []
        self._check_vars: list[tk.BooleanVar] = []
        self._thumb_cache: dict[str, ImageTk.PhotoImage] = {}
        self._selected_index: int | None = None
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build(self):
        columns = ("select", "thumb", "title", "status", "scheduled")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")

        self.tree.heading("select", text="✓")
        self.tree.heading("thumb", text="Thumbnail")
        self.tree.heading("title", text="Title")
        self.tree.heading("status", text="Status")
        self.tree.heading("scheduled", text="Scheduled Date")

        self.tree.column("select", width=30, stretch=False, anchor="center")
        self.tree.column("thumb", width=90, stretch=False, anchor="center")
        self.tree.column("title", width=300, stretch=True)
        self.tree.column("status", width=90, stretch=False, anchor="center")
        self.tree.column("scheduled", width=160, stretch=False)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-1>", self._on_click)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_videos(self, videos: list[dict]):
        self._videos = videos
        self._check_vars = [tk.BooleanVar(value=False) for _ in videos]
        self._selected_index = None
        self._refresh_rows()

    def get_checked_videos(self) -> list[dict]:
        return [v for v, c in zip(self._videos, self._check_vars) if c.get()]

    def get_checked_indices(self) -> list[int]:
        return [i for i, c in enumerate(self._check_vars) if c.get()]

    def set_row_status(self, video_id: str, status_text: str, color: str = ""):
        for item in self.tree.get_children():
            vals = list(self.tree.item(item, "values"))
            idx = self.tree.index(item)
            if idx < len(self._videos) and self._videos[idx]["id"] == video_id:
                vals[3] = status_text
                self.tree.item(item, values=vals)
                if color:
                    self.tree.tag_configure(f"row_{video_id}", foreground=color)
                    self.tree.item(item, tags=(f"row_{video_id}",))
                break

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _refresh_rows(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for i, video in enumerate(self._videos):
            snippet = video.get("snippet", {})
            status = video.get("status", {})

            title = snippet.get("title", "(no title)")
            privacy = status.get("privacyStatus", "")
            publish_at = status.get("publishAt", "")

            if publish_at:
                try:
                    utc_dt = pytz.utc.localize(
                        datetime.strptime(publish_at, "%Y-%m-%dT%H:%M:%SZ")
                    )
                    sched_str = utc_dt.strftime("%Y-%m-%d %H:%M UTC")
                except Exception:
                    sched_str = publish_at
            else:
                sched_str = ""

            check_str = "☑" if self._check_vars[i].get() else "☐"
            iid = self.tree.insert(
                "",
                "end",
                values=(check_str, "", title, privacy, sched_str),
                tags=(f"row_{i}",),
            )

            # Async thumbnail fetch
            thumb_url = self._get_thumb_url(snippet)
            if thumb_url:
                threading.Thread(
                    target=self._fetch_thumb,
                    args=(iid, thumb_url),
                    daemon=True,
                ).start()

    def _get_thumb_url(self, snippet: dict) -> str | None:
        thumbs = snippet.get("thumbnails", {})
        for key in ("default", "medium", "high"):
            t = thumbs.get(key, {})
            if t.get("url"):
                return t["url"]
        return None

    def _fetch_thumb(self, iid: str, url: str):
        if url in self._thumb_cache:
            self._set_thumb(iid, self._thumb_cache[url])
            return
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).resize((THUMB_W, THUMB_H), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._thumb_cache[url] = photo
            self.after(0, lambda: self._set_thumb(iid, photo))
        except Exception:
            pass

    def _set_thumb(self, iid: str, photo: ImageTk.PhotoImage):
        try:
            self.tree.item(iid)  # raises if deleted
        except tk.TclError:
            return
        # Treeview can't display images in cells natively without a tag trick;
        # we store the photo reference and use a label overlay approach via image column.
        self.tree.item(iid, image=photo)
        # Keep reference so GC doesn't collect it
        if not hasattr(self, "_photo_refs"):
            self._photo_refs = []
        self._photo_refs.append(photo)

    def _on_click(self, event: tk.Event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        idx = self.tree.index(iid)
        if col == "#1":  # checkbox column
            self._check_vars[idx].set(not self._check_vars[idx].get())
            vals = list(self.tree.item(iid, "values"))
            vals[0] = "☑" if self._check_vars[idx].get() else "☐"
            self.tree.item(iid, values=vals)

    def _on_tree_select(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        self._selected_index = idx
        if self._on_select and idx < len(self._videos):
            self._on_select(idx, self._videos[idx])
