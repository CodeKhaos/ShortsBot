"""Shared custom widgets."""
import tkinter as tk
from tkcalendar import DateEntry as _DateEntry


class DateEntry(_DateEntry):
    """DateEntry that:
    - Closes its calendar popup when the user clicks outside it.
    - Patches a tkcalendar crash on Python 3.14 where focus_get() raises
      KeyError('popdown') when a ttk.Combobox dropdown is active.
    """

    # ------------------------------------------------------------------ #
    # Python 3.14 / tkcalendar compatibility fix                          #
    # ------------------------------------------------------------------ #
    def _on_focus_out_cal(self, event):
        try:
            super()._on_focus_out_cal(event)
        except KeyError:
            pass

    # ------------------------------------------------------------------ #
    # Close-on-outside-click                                              #
    # ------------------------------------------------------------------ #
    def drop_down(self):
        super().drop_down()
        if getattr(self, "_top_cal", None) is not None:
            # Delay by one event-loop tick so the click that *opened* the
            # calendar is fully consumed before we start watching.
            self.after(1, self._start_outside_watch)

    def _start_outside_watch(self):
        """Install a ButtonPress watcher on the root window."""
        if getattr(self, "_top_cal", None) is None:
            return  # calendar already closed before we got here
        root = self.winfo_toplevel()
        self._outside_bid = root.bind(
            "<ButtonPress>", self._on_outside_click, add="+"
        )

    def _on_outside_click(self, event):
        top = getattr(self, "_top_cal", None)
        if top is None:
            self._stop_outside_watch()
            return
        # Allow clicks inside the calendar Toplevel to pass through normally
        cx, cy = top.winfo_rootx(), top.winfo_rooty()
        cw, ch = top.winfo_width(), top.winfo_height()
        if not (cx <= event.x_root < cx + cw and cy <= event.y_root < cy + ch):
            self._stop_outside_watch()
            # Withdraw only if visible — drop_down() is a toggle and would
            # re-open the calendar if it's already in 'withdrawn' state.
            try:
                if top.wm_state() != "withdrawn":
                    top.withdraw()
            except Exception:
                pass

    def _stop_outside_watch(self):
        bid = getattr(self, "_outside_bid", None)
        if bid:
            try:
                self.winfo_toplevel().unbind("<ButtonPress>", bid)
            except Exception:
                pass
            self._outside_bid = None
