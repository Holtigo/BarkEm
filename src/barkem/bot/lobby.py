"""
Phase 2 — Lobby creation flow.

LobbyCreator orchestrates the controller + vision pieces that already
exist (MenuNavigator, LobbyNavigator, capture, OCR) into one method:
``create_and_read_code()``.

Steps:
  1. Vision-guided main-menu → Change Game Mode → Private Match → Create
  2. Wait for the LOBBY screen to be detected
  3. Optionally pick a mode + map via dropdown indices
  4. OCR the lobby code from the configured region

Kept separate from ``barkem.py`` to avoid bloating the state-machine
class, and so it can be exercised standalone via
``python -m barkem.tools.create_lobby``.
"""

import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from rapidfuzz import fuzz

from barkem.input.controller import GamepadController
from barkem.input.navigator import (
    MenuNavigator,
    LobbyNavigator,
    DropdownSlot,
)
from barkem.input.window import WindowManager
from barkem.vision.capture import ScreenCapture
from barkem.vision.ocr import TextReader
from barkem.vision.regions import ScreenRegions, Region
from barkem.vision.state_detector import GameStateDetector, GameScreen


# Map DropdownSlot → attribute name on regions.dropdowns
_DROPDOWN_REGION_ATTR = {
    DropdownSlot.GAME_MODE: "game_mode",
    DropdownSlot.ARENA:     "arena",
    DropdownSlot.VARIANT:   "variant",
    DropdownSlot.CONDITION: "condition",
    DropdownSlot.GAME_SHOW: "game_show",
}


@dataclass
class LobbyCreationResult:
    success: bool
    lobby_code: Optional[str] = None
    error: Optional[str] = None


class LobbyCreator:
    """Phase 2 entry point: create a private match lobby and OCR its code."""

    def __init__(
        self,
        menu_nav: MenuNavigator,
        lobby_nav: LobbyNavigator,
        capture: ScreenCapture,
        text_reader: TextReader,
        regions: ScreenRegions,
        state_detector: GameStateDetector,
        mode_indices: dict[str, int],
        map_indices: dict[str, int],
        lobby_settle_timeout: float = 8.0,
        verify_attempts: int = 3,
        verify_settle: float = 0.6,
        verify_fuzzy_threshold: int = 75,
        window_manager: Optional[WindowManager] = None,
        focus_settle: float = 0.5,
    ):
        self.menu = menu_nav
        self.lobby = lobby_nav
        self.capture = capture
        self.ocr = text_reader
        self.regions = regions
        self.detector = state_detector
        self.mode_indices = mode_indices
        self.map_indices = map_indices
        self.lobby_settle_timeout = lobby_settle_timeout
        self.verify_attempts = verify_attempts
        self.verify_settle = verify_settle
        self.verify_fuzzy_threshold = verify_fuzzy_threshold
        self.window = window_manager
        self.focus_settle = focus_settle

    # ── Public API ──────────────────────────────────────────────────────

    def create_and_read_code(
        self,
        mode: Optional[str] = None,
        map_name: Optional[str] = None,
    ) -> LobbyCreationResult:
        """End-to-end: focus game, navigate from main menu, create lobby, return code."""
        if self.window is not None:
            if not self.window.focus():
                return LobbyCreationResult(
                    success=False,
                    error=(
                        f"Could not focus game window matching "
                        f"{self.window.window_title!r}."
                    ),
                )
            time.sleep(self.focus_settle)

        if not self.menu.go_to_create_game():
            return LobbyCreationResult(
                success=False,
                error="Could not navigate to Create Game (template not found).",
            )

        if not self._wait_for_lobby():
            return LobbyCreationResult(
                success=False,
                error=f"Lobby screen not detected within {self.lobby_settle_timeout}s.",
            )

        if mode:
            ok, err = self._select_with_verify(
                DropdownSlot.GAME_MODE, mode, self.mode_indices,
            )
            if not ok:
                return LobbyCreationResult(success=False, error=err)

        if map_name:
            ok, err = self._select_with_verify(
                DropdownSlot.ARENA, map_name, self.map_indices,
            )
            if not ok:
                return LobbyCreationResult(success=False, error=err)

        code = self.read_lobby_code()
        if not code or len(code) < 4:
            return LobbyCreationResult(
                success=False,
                lobby_code=code,
                error="Lobby code OCR failed or returned <4 chars.",
            )
        return LobbyCreationResult(success=True, lobby_code=code)

    def read_lobby_code(self) -> Optional[str]:
        """OCR the lobby code from the configured region."""
        region = self.regions.lobby.lobby_code
        if region.is_zero:
            return None
        frame = self._grab()
        if frame is None:
            return None
        return self.ocr.read_lobby_code(self._crop(frame, region.as_tuple()))

    def select_and_verify(
        self,
        slot: DropdownSlot,
        expected_label: str,
        option_index: int,
    ) -> tuple[bool, Optional[str]]:
        """
        Open a dropdown, pick an option, then OCR the displayed value
        and retry up to ``verify_attempts`` times if it doesn't match.

        Returns (ok, error_message).  If the OCR region for this
        dropdown isn't configured, skips verification and returns OK.
        """
        region = self._dropdown_region(slot)
        last_seen: str = ""

        for attempt in range(1, self.verify_attempts + 1):
            self.lobby.select_dropdown_option(slot, option_index)

            # No OCR region configured → trust the input, can't verify
            if region is None or region.is_zero:
                return True, None

            time.sleep(self.verify_settle)
            seen = self._read_region(region)
            last_seen = seen
            if self._fuzzy_match(seen, expected_label):
                return True, None
            # Mismatch — re-anchor and try again
            self.lobby.anchor()

        return False, (
            f"{slot.name} verification failed after {self.verify_attempts} "
            f"attempts: expected ~{expected_label!r}, last OCR={last_seen!r}"
        )

    # ── Internals ───────────────────────────────────────────────────────

    def _select_with_verify(
        self,
        slot: DropdownSlot,
        key: str,
        index_map: dict[str, int],
    ) -> tuple[bool, Optional[str]]:
        idx = index_map.get(key)
        if idx is None:
            return False, f"Unknown {slot.name.lower()}: {key}"
        return self.select_and_verify(slot, key, idx)

    def _dropdown_region(self, slot: DropdownSlot) -> Optional[Region]:
        attr = _DROPDOWN_REGION_ATTR.get(slot)
        if not attr:
            return None
        return getattr(self.regions.dropdowns, attr, None)

    def _read_region(self, region: Region) -> str:
        frame = self._grab()
        if frame is None:
            return ""
        return self.ocr.read_text(self._crop(frame, region.as_tuple())).strip()

    def _fuzzy_match(self, seen: str, expected_key: str) -> bool:
        """Compare OCR'd dropdown value against the config key."""
        if not seen:
            return False
        # Normalise: "final_round" → "final round"; case-insensitive
        seen_n = seen.lower().replace("_", " ").strip()
        expected_n = expected_key.lower().replace("_", " ").strip()
        # Exact substring match wins outright
        if expected_n in seen_n or seen_n in expected_n:
            return True
        return fuzz.ratio(seen_n, expected_n) >= self.verify_fuzzy_threshold

    def _wait_for_lobby(self) -> bool:
        deadline = time.time() + self.lobby_settle_timeout
        while time.time() < deadline:
            frame = self._grab()
            if frame is not None and self.detector.is_screen(frame, GameScreen.LOBBY):
                return True
            time.sleep(0.25)
        return False

    def _grab(self) -> Optional[np.ndarray]:
        for _ in range(5):
            frame = self.capture.grab()
            if frame is not None:
                return frame
            time.sleep(0.05)
        return None

    @staticmethod
    def _crop(frame: np.ndarray, region: tuple[int, int, int, int]) -> np.ndarray:
        x1, y1, x2, y2 = region
        return frame[y1:y2, x1:x2]
