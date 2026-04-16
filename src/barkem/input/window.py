"""
Window management — find and focus the game window by fuzzy title match.

Works for both the local Steam version ("THE FINALS") and the GeForce
NOW Chrome window ("THE FINALS on GeForce NOW - ..."), since we score
all visible top-level windows with rapidfuzz and pick the best match.

Windows-only (uses win32gui).  On other platforms ``focus()`` no-ops
and returns False so the bot can still run for testing.
"""

import sys
import time
from dataclasses import dataclass
from typing import Optional

from rapidfuzz import fuzz


@dataclass
class WindowRect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:  return self.right - self.left
    @property
    def height(self) -> int: return self.bottom - self.top
    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)


class WindowManager:
    """Find and focus the game window by (fuzzy) title."""

    def __init__(
        self,
        window_title: str = "THE FINALS",
        match_threshold: int = 60,
    ):
        self.window_title = window_title
        self.match_threshold = match_threshold
        self._hwnd: Optional[int] = None
        self._available = sys.platform == "win32"

    # ── Discovery ──────────────────────────────────────────────────────

    def _enumerate_windows(self) -> list[tuple[int, str]]:
        """Return [(hwnd, title)] for every visible top-level window."""
        if not self._available:
            return []
        import win32gui

        results: list[tuple[int, str]] = []

        def _cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if title:
                results.append((hwnd, title))

        win32gui.EnumWindows(_cb, None)
        return results

    def find_window(self) -> Optional[int]:
        """
        Find the best-matching window by title.  Tries exact match
        first, then a fuzzy partial-ratio search over all visible
        windows, picking the highest score above ``match_threshold``.
        """
        if not self._available:
            return None
        import win32gui

        # Exact match — fast path
        hwnd = win32gui.FindWindow(None, self.window_title)
        if hwnd:
            self._hwnd = hwnd
            return hwnd

        # Fuzzy match across all visible windows
        target = self.window_title.lower()
        best_score = 0
        best_hwnd: Optional[int] = None
        for h, title in self._enumerate_windows():
            score = fuzz.partial_ratio(target, title.lower())
            if score > best_score:
                best_score = score
                best_hwnd = h

        if best_hwnd and best_score >= self.match_threshold:
            self._hwnd = best_hwnd
            return best_hwnd
        return None

    def find_window_title(self) -> Optional[str]:
        """Return the title of the matched window (for logging)."""
        if not self._available:
            return None
        import win32gui
        hwnd = self.find_window()
        if not hwnd:
            return None
        return win32gui.GetWindowText(hwnd)

    # ── State ──────────────────────────────────────────────────────────

    def is_window_open(self) -> bool:
        return self.find_window() is not None

    def is_focused(self) -> bool:
        if not self._available:
            return False
        import win32gui
        return win32gui.GetForegroundWindow() == self._hwnd

    def get_rect(self) -> Optional[WindowRect]:
        if not self._available:
            return None
        import win32gui
        hwnd = self.find_window()
        if not hwnd:
            return None
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return WindowRect(left, top, right, bottom)

    # ── Actions ────────────────────────────────────────────────────────

    def focus(self) -> bool:
        """Bring the matched window to the foreground."""
        if not self._available:
            return False
        import win32con
        import win32gui

        hwnd = self.find_window()
        if not hwnd:
            return False

        try:
            # Restore if minimised, then raise to front
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            # SetForegroundWindow can fail if the calling thread isn't
            # the foreground one; fall back to a show-window nudge.
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            except Exception:
                return False

        time.sleep(0.2)
        return self.is_focused()

    def wait_for_window(self, timeout: float = 30.0) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            if self.is_window_open():
                return True
            time.sleep(0.5)
        return False
