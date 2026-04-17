"""
Phase 3 — OCR helpers for reading the lobby state.

LobbyReader answers three questions:
  • Who is in the unassigned list? (dynamic length — stops at first empty slot)
  • Who is in each team slot?
  • Which player is the context menu currently showing? (for verify-before-move)

Only depends on TextReader + ScreenRegions — no controller / no state machine.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from barkem.vision.ocr import TextReader
from barkem.vision.regions import LobbyRegions, ContextMenuRegions, Region


# Tokens that indicate an empty slot ("---", "ANY", etc.).
_EMPTY_TOKENS = {"", "-", "--", "---", "----"}


def _is_empty_text(name: str) -> bool:
    stripped = name.strip()
    if stripped.lower() in _EMPTY_TOKENS:
        return True
    return not any(c.isalnum() for c in stripped)


# ── Slot background-color classification ────────────────────────────────
#
# Each lobby slot has one of three background colours:
#   • #1d1a20 (dark)    — other player
#   • #f0f2f4 (white)   — the bot / local client
#   • #575c69 (grey)    — empty slot
#
# Classifying the slot's background lets us skip OCR on empty slots and
# also tag the bot slot without relying on text matching.

class SlotKind(Enum):
    PLAYER = "player"   # other player (dark bg)
    BOT    = "bot"      # local client (white bg)
    EMPTY  = "empty"    # "---" (grey bg)


# Reference BGR values (OpenCV / DXcam deliver BGR).
# Source hex was given RGB → flip to BGR here.
_REF_BGR = {
    SlotKind.PLAYER: np.array([0x20, 0x1a, 0x1d], dtype=np.int16),
    SlotKind.BOT:    np.array([0xf4, 0xf2, 0xf0], dtype=np.int16),
    SlotKind.EMPTY:  np.array([0x69, 0x5c, 0x57], dtype=np.int16),
}


def classify_slot_bg(roi: np.ndarray) -> SlotKind:
    """
    Classify a slot by its median background colour.

    ``roi`` should be the slot's row area (name region is fine — the
    background dominates the pixel count even with a name drawn over it,
    because the text is a small fraction of the region area).  Returns
    the closest of the three reference colours in BGR Euclidean space.
    """
    if roi is None or roi.size == 0:
        return SlotKind.EMPTY
    # Median per channel → robust against antialiased text pixels.
    med = np.median(roi.reshape(-1, roi.shape[-1]), axis=0).astype(np.int16)
    best, best_dist = SlotKind.EMPTY, None
    for kind, ref in _REF_BGR.items():
        dist = int(np.sum((med - ref) ** 2))
        if best_dist is None or dist < best_dist:
            best, best_dist = kind, dist
    return best


@dataclass
class LobbySnapshot:
    """One-shot read of every player slot in the lobby."""

    unassigned: list[str] = field(default_factory=list)   # non-empty OCR reads, in order
    unassigned_total_rows: int = 0                         # incl. trailing empty slot
    spectators: list[str] = field(default_factory=list)
    team1: list[Optional[str]] = field(default_factory=list)  # len == 3; None = empty slot
    team2: list[Optional[str]] = field(default_factory=list)

    def index_of(self, target: str, fuzzy_threshold: int = 75) -> Optional[int]:
        """Find *target* in the unassigned list.  Returns row index or None."""
        from rapidfuzz import fuzz
        best_i, best_score = None, 0
        t = target.lower().strip()
        for i, name in enumerate(self.unassigned):
            n = name.lower().strip()
            if t in n or n in t:
                return i
            score = fuzz.ratio(n, t)
            if score > best_score:
                best_score = score
                best_i = i
        return best_i if best_score >= fuzzy_threshold else None


class LobbyReader:
    """OCR helper that turns raw frames into a LobbySnapshot."""

    # Maximum number of unassigned slots defined in the regions schema.
    MAX_UNASSIGNED = 10

    def __init__(
        self,
        ocr: TextReader,
        lobby: LobbyRegions,
        context_menu: Optional[ContextMenuRegions] = None,
    ):
        self.ocr = ocr
        self.lobby = lobby
        self.context_menu = context_menu

    # ── Public ──────────────────────────────────────────────────────────

    def read_snapshot(self, frame: np.ndarray) -> LobbySnapshot:
        snap = LobbySnapshot()

        # Unassigned — stop at the first EMPTY slot (by background colour)
        for i in range(1, self.MAX_UNASSIGNED + 1):
            region = self._region(f"unassigned_player{i}_name")
            if region is None or region.is_zero:
                break
            kind, text = self._classify_and_read(frame, region)
            if kind == SlotKind.EMPTY:
                snap.unassigned_total_rows = i
                break
            snap.unassigned.append(text)
            snap.unassigned_total_rows = i
        else:
            snap.unassigned_total_rows = self.MAX_UNASSIGNED + 1

        # Spectators — up to 3; skip grey/empty slots
        for i in range(1, 4):
            region = self._region(f"spectator{i}_name")
            if region is None or region.is_zero:
                continue
            kind, text = self._classify_and_read(frame, region)
            if kind != SlotKind.EMPTY and text:
                snap.spectators.append(text)

        # Teams — fixed length 3
        snap.team1 = [self._read_team_slot(frame, f"team1_player{i}_name") for i in (1, 2, 3)]
        snap.team2 = [self._read_team_slot(frame, f"team2_player{i}_name") for i in (1, 2, 3)]
        return snap

    def read_context_menu_name(self, frame: np.ndarray) -> Optional[str]:
        """OCR the player name shown in the open context menu popup."""
        if self.context_menu is None:
            return None
        region = self.context_menu.player_name
        if region.is_zero:
            return None
        text = self._read(frame, region)
        return text or None

    # ── Internals ───────────────────────────────────────────────────────

    def _region(self, attr: str) -> Optional[Region]:
        return getattr(self.lobby, attr, None)

    def _roi(self, frame: np.ndarray, region: Region) -> np.ndarray:
        x1, y1, x2, y2 = region.as_tuple()
        return frame[y1:y2, x1:x2]

    def _read(self, frame: np.ndarray, region: Region) -> str:
        roi = self._roi(frame, region)
        if roi.size == 0:
            return ""
        return self.ocr.read_player_name(roi).strip()

    def _classify_and_read(
        self, frame: np.ndarray, region: Region,
    ) -> tuple[SlotKind, str]:
        """Classify slot by bg colour; only OCR if it's occupied."""
        roi = self._roi(frame, region)
        if roi.size == 0:
            return SlotKind.EMPTY, ""
        kind = classify_slot_bg(roi)
        if kind == SlotKind.EMPTY:
            return kind, ""
        text = self.ocr.read_player_name(roi).strip()
        if _is_empty_text(text):
            return kind, ""
        return kind, text

    def _read_team_slot(self, frame: np.ndarray, attr: str) -> Optional[str]:
        region = self._region(attr)
        if region is None or region.is_zero:
            return None
        kind, text = self._classify_and_read(frame, region)
        if kind == SlotKind.EMPTY or not text:
            return None
        return text
