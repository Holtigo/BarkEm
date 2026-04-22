"""
Game state detection using template matching.

Identifies which screen the game is currently showing:
main menu, private match setup, lobby, in-match, scoreboard, etc.
"""

from enum import Enum, auto
from typing import Optional

import numpy as np

from barkem.vision.templates import TemplateMatcher, MatchResult


class GameScreen(Enum):
    """Known game screens that can be detected."""
    UNKNOWN = auto()
    MAIN_MENU = auto()
    PLAY_MENU = auto()            # After clicking Play
    PRIVATE_MATCH_SETUP = auto()   # Mode/map selection
    LOBBY = auto()                 # Waiting room with team slots
    MATCH_LOADING = auto()         # Loading screen before match
    MATCH_IN_PROGRESS = auto()     # Active gameplay
    MATCH_PAUSED = auto()          # Match is paused
    MATCH_SUMMARY = auto()         # "SUMMARY" screen between match and scoreboard
    MATCH_COMPLETE = auto()        # End-of-match banner
    SCOREBOARD = auto()            # Results screen


# Map template image names to game screens.
# Each screen can have multiple templates — any match = that screen.
# Template images must be placed in the templates/ directory.
SCREEN_TEMPLATES: dict[GameScreen, list[str]] = {
    GameScreen.MAIN_MENU: [
        "main_menu_indicator",
    ],
    GameScreen.PLAY_MENU: [
        "play_button",
    ],
    GameScreen.PRIVATE_MATCH_SETUP: [
        "private_match_tile",
        "create_game_button",
    ],
    GameScreen.LOBBY: [
        "lobby_code_region",
        "start_match_button",
    ],
    GameScreen.MATCH_LOADING: [
        "match_loading_screen",
    ],
    GameScreen.MATCH_IN_PROGRESS: [
        "match_in_progress_indicator",
    ],
    GameScreen.MATCH_SUMMARY: [
        "match_summary",
    ],
    GameScreen.MATCH_COMPLETE: [
        "match_complete_banner",
    ],
    GameScreen.SCOREBOARD: [
        "scoreboard_header",
        "return_to_lobby_button",
    ],
}


class GameStateDetector:
    """
    Detects the current game screen using template matching.

    Usage:
        detector = GameStateDetector(templates_dir="templates")
        screen, match = detector.detect(frame)
        if screen == GameScreen.LOBBY:
            # We're in the lobby
            ...
    """

    def __init__(
            self,
            templates_dir: str = "templates",
            threshold: float = 0.85,
    ):
        """
        Initialize the state detector.

        Args:
            templates_dir: Path to directory containing template .png files.
            threshold: Minimum confidence for a template match.
        """
        self.matcher = TemplateMatcher(
            templates_dir=templates_dir,
            threshold=threshold,
        )
        self.threshold = threshold
        self._last_screen: GameScreen = GameScreen.UNKNOWN
        self._last_confidence: float = 0.0

    def detect(
            self,
            frame: np.ndarray,
            candidates: Optional[list[GameScreen]] = None,
    ) -> tuple[GameScreen, Optional[MatchResult]]:
        """
        Detect the current game screen.

        Args:
            frame: BGR screenshot from DXcam.
            candidates: Optional list of screens to check (for optimization).
                        If None, checks all known screens.

        Returns:
            Tuple of (detected GameScreen, best MatchResult or None).
        """
        best_screen = GameScreen.UNKNOWN
        best_match: Optional[MatchResult] = None
        best_confidence = 0.0

        screens_to_check = candidates or list(SCREEN_TEMPLATES.keys())

        for screen in screens_to_check:
            templates = SCREEN_TEMPLATES.get(screen, [])
            for template_name in templates:
                result = self.matcher.find(frame, template_name)
                if result and result.confidence > best_confidence:
                    best_confidence = result.confidence
                    best_screen = screen
                    best_match = result

        self._last_screen = best_screen
        self._last_confidence = best_confidence

        return best_screen, best_match

    def is_screen(
            self,
            frame: np.ndarray,
            expected: GameScreen,
    ) -> bool:
        """
        Quick check if the current frame matches a specific screen.

        Args:
            frame: BGR screenshot.
            expected: The screen to check for.

        Returns:
            True if the frame matches the expected screen.
        """
        templates = SCREEN_TEMPLATES.get(expected, [])
        for template_name in templates:
            result = self.matcher.find(frame, template_name)
            if result:
                return True
        return False

    @property
    def last_screen(self) -> GameScreen:
        """The last detected game screen."""
        return self._last_screen

    @property
    def last_confidence(self) -> float:
        """Confidence of the last detection."""
        return self._last_confidence

    def get_available_templates(self) -> dict[GameScreen, list[str]]:
        """
        Check which template images actually exist on disk.

        Returns:
            Dict mapping GameScreen to list of available template names.
        """
        available = {}
        for screen, templates in SCREEN_TEMPLATES.items():
            found = []
            for name in templates:
                template = self.matcher.load_template(name)
                if template is not None:
                    found.append(name)
            if found:
                available[screen] = found
        return available

    def get_missing_templates(self) -> dict[GameScreen, list[str]]:
        """
        Check which template images are missing.

        Returns:
            Dict mapping GameScreen to list of missing template names.
        """
        missing = {}
        for screen, templates in SCREEN_TEMPLATES.items():
            not_found = []
            for name in templates:
                template = self.matcher.load_template(name)
                if template is None:
                    not_found.append(name)
            if not_found:
                missing[screen] = not_found
        return missing