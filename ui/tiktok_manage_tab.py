"""TikTok — manage (list + delete) tab."""

import io
import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

import requests
from PIL import Image, ImageTk

from tiktok_api import fetch_my_videos, delete_video

THUMB_W, THUMB_H = 80, 45
PRIVACY_LABELS = {
    "PUBLIC_TO_EVERYONE": "Public",
    "MUTUAL_FOLLOW_FRIENDS": "Friends",
    "FOLLOWER_OF_CREATOR": "Followers",
    "SELF_ONLY": "Private",
}


class TikTokManageTab(ttk.Frame):
    def __init__(self, parent, get_token, config: dict):
        super().__init__(parent)
        self._get_token = get_token
        self._config = config
        self._videos: list[dict] = []
        self._photo_refs: list = []
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build(self):
        # Toolbar
        toolbar = ttk.Frame(self, padding=(4, 4))
        toolbar.pack(fill="x", side="top")

        ttk.Button(toolbar, text="↺ Refresh", command=self.load_videos).pack(
            side="left", padx=2
        )
        ttk.Label(toolbar, text="Load:").pack(side="left", padx=(8, 2))
        self.limit_var = tk.StringVar(value=str(self._config.get("load_limit", 25)))
        ttk.Entry(toolbar, textvariable=self.limit_var, width=5).pack(side="left")
        ttk.Label(toolbar, text="videos (0=all)").pack(side="left", padx=(2, 0))

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(toolbar, text="🗑 Delete Selected", command=self._delete_selected).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="🌐 Open in Browser", command=self._open_in_browser).pack(
            side="left", padx=2
        )

        # Table
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=6, pady=4)

        cols = ("thumb", "title", "privacy", "duration", "views", "likes", "comments", "date")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        for col, width, label in [
            ("thumb",    90,  "Thumbnail"),
            ("title",    260, "Title"),
            ("privacy",  80,  "Privacy"),
            ("duration", 70,  "Duration"),
            ("views",    70,  "Views"),
            ("likes",    70,  "Likes"),
            ("comments", 80,  "Comments"),
            ("date",     140, "Posted"),
        ]:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, stretch=(col == "title"))

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Log
        log_frame = ttk.LabelFrame(self, text="Log", padding=4)
        log_frame.pack(fill="x", side="bottom", padx=6, pady=(0, 4))
        self.log_text = tk.Text(
            log_frame, height=4, state="disabled", wrap="word", font=("Courier", 9)
        )
        sb = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="x", expand=True)
        sb.pack(side="right", fill="y")

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    def load_videos(self):
        try:
            limit = int(self.limit_var.get())
        except ValueError:
            limit = 25
        self._log("Fetching TikTok videos…")

        def worker():
            try:
                token = self._get_token()
                if not token:
                    self.after(0, lambda: self._log("No TikTok account active.", error=True))
                    return
                videos = fetch_my_videos(token, limit=limit)
                self.after(0, lambda v=videos: self._populate(v))
            except Exception as exc:
                self.after(0, lambda e=exc: self._log(f"Error: {e}", error=True))

        threading.Thread(target=worker, daemon=True).start()

    def _populate(self, videos: list[dict]):
        self._videos = videos
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._photo_refs.clear()
        self._log(f"Loaded {len(videos)} video(s).")

        for v in videos:
            ts = v.get("create_time", 0)
            date_str = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else ""
            dur = v.get("duration", 0)
            dur_str = f"{dur}s" if dur else ""
            privacy = PRIVACY_LABELS.get(v.get("privacy_level", ""), v.get("privacy_level", ""))

            iid = self.tree.insert("", "end", values=(
                "", v.get("title", "")[:80],
                privacy, dur_str,
                v.get("view_count", ""), v.get("like_count", ""),
                v.get("comment_count", ""), date_str,
            ))

            thumb_url = v.get("cover_image_url")
            if thumb_url:
                threading.Thread(
                    target=self._fetch_thumb, args=(iid, thumb_url), daemon=True
                ).start()

    def _fetch_thumb(self, iid: str, url: str):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).resize((THUMB_W, THUMB_H), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._photo_refs.append(photo)
            self.after(0, lambda i=iid, p=photo: self._set_thumb(i, p))
        except Exception:
            pass

    def _set_thumb(self, iid: str, photo):
        try:
            self.tree.item(iid, image=photo)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _selected_video(self) -> dict | None:
        sel = self.tree.selection()
        if not sel:
            return None
        idx = self.tree.index(sel[0])
        return self._videos[idx] if idx < len(self._videos) else None

    def _delete_selected(self):
        video = self._selected_video()
        if not video:
            messagebox.showinfo("Delete", "No video selected.")
            return
        title = video.get("title", video.get("id", "?"))
        if not messagebox.askyesno(
            "Delete Video",
            f"Permanently delete '{title}' from TikTok?\n\nThis cannot be undone.",
        ):
            return

        def worker():
            try:
                token = self._get_token()
                delete_video(token, video["id"])
                self.after(0, lambda: self._log(f"Deleted: {title}"))
                self.after(0, self.load_videos)
            except Exception as exc:
                self.after(0, lambda e=exc: self._log(f"Delete failed: {e}", error=True))

        threading.Thread(target=worker, daemon=True).start()

    def _open_in_browser(self):
        import webbrowser
        video = self._selected_video()
        if not video:
            messagebox.showinfo("Open", "No video selected.")
            return
        url = video.get("share_url") or video.get("embed_link")
        if url:
            webbrowser.open(url)
        else:
            messagebox.showinfo("Open", "No share URL available for this video.")

    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------
    def _log(self, msg: str, error: bool = False):
        self.log_text.configure(state="normal")
        self.log_text.tag_configure("error", foreground="#cc0000")
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n", "error" if error else "")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
