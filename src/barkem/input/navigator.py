"""
High-level UI navigation using D-pad sequences.

MenuNavigator  — main menu → create private match
LobbyNavigator — 3-column lobby navigation and player placement

LOBBY LAYOUT (from the screenshot):
    ┌─────────────────┬──────────────────────┬─────────────────────┐
    │  LEFT COLUMN    │  CENTER COLUMN       │  RIGHT COLUMN       │
    │  Match Details  │  Unassigned Players  │  THE BOUNDLESS (T1) │
    │                 │  (grows as players   │    slot 0            │
    │  Game Mode  ▼   │   join below)        │    slot 1            │
    │  Arena      ▼   │                      │    slot 2            │
    │  Variant    ▼   │  ─────────────────   │                     │
    │  Condition  ▼   │  SPECTATORS          │  THE LIVE WIRES(T2) │
    │  Game Show  ▼   │    slot 0            │    slot 0            │
    │                 │    slot 1            │    slot 1            │
    │                 │    slot 2            │    slot 2            │
    └─────────────────┴──────────────────────┴─────────────────────┘

    After anchor (B-spam) → cursor on first unassigned slot (center).
    LEFT  → match details column
    RIGHT → teams column
    UP/DOWN → navigate within current column
"""

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from barkem.input.controller import GamepadController


# ═══════════════════════════════════════════════════════════════════════════
#  MENU NAVIGATOR
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class MenuSequences:
    """
    D-pad sequences for menu navigation.

    The main menu wraps infinitely — no anchor works there.
    The "Change Game Mode" button is found via template matching.

    The game mode selection screen CAN be anchored: UP×7 resets to
    the top, then DOWN×7 reaches Private Match.
    """

    # Game mode screen → anchor to top, then down to Private Match
    mode_anchor_up: int = 7
    mode_down_to_private: int = 7

    # Private Match screen → Create Game (usually just confirm)
    private_to_create: list[str] = field(
        default_factory=lambda: ["a"]
    )


class MenuNavigator:
    """
    Navigate the game's main menu system via D-pad.

    The main menu step uses VISION (template matching on every press)
    to find "Change Game Mode".  Everything after that uses fixed
    sequences because those screens can be anchored.
    """

    def __init__(
        self,
        controller: GamepadController,
        capture,                           # ScreenCapture — grabs frames
        matcher,                           # TemplateMatcher — finds templates
        sequences: Optional[MenuSequences] = None,
        transition_wait: float = 0.5,
    ):
        self.ctrl = controller
        self.capture = capture
        self.matcher = matcher
        self.seq = sequences or MenuSequences()
        self.transition_wait = transition_wait

    def _find_template(self, template_name: str) -> bool:
        """Grab a frame and check if a template is visible."""
        frame = self.capture.grab()
        if frame is None:
            return False
        return self.matcher.find(frame, template_name) is not None

    def navigate_to_template(
        self,
        direction: str,
        template_name: str,
        max_presses: int = 20,
    ) -> bool:
        """
        Press *direction* repeatedly until *template_name* appears.

        Returns True if found, False if max_presses exhausted.
        """
        # Check before pressing in case we're already on it
        if self._find_template(template_name):
            return True

        for _ in range(max_presses):
            self.ctrl.press(direction)
            time.sleep(0.15)  # brief settle for the UI to update
            if self._find_template(template_name):
                return True

        return False

    def go_to_create_game(self) -> bool:
        """
        Main Menu → Change Game Mode → Private Match → Create Game.

        Returns True on success, False if any step failed to find
        the expected template.

        Requires template: ``change_game_mode_selected.png``
          — the "Change Game Mode" button WITH the white selection
            outline visible.  Capture this at your resolution.
        """
        # ── Step 1: Main menu → find "Change Game Mode" ──────────────
        # The main menu wraps, so just press UP until the template
        # matches (it's the last item in the right column — UP wraps
        # to it from the top).
        found = self.navigate_to_template(
            direction="up",
            template_name="change_game_mode_selected",
            max_presses=15,
        )
        if not found:
            return False

        self.ctrl.confirm()
        time.sleep(self.transition_wait)

        # ── Step 2: Game mode screen → Private Match ─────────────────
        # This screen CAN be anchored: UP×7 to top, DOWN×7 to PM.
        self.ctrl.press("up", self.seq.mode_anchor_up)
        time.sleep(0.1)
        self.ctrl.press("down", self.seq.mode_down_to_private)
        self.ctrl.confirm()
        time.sleep(self.transition_wait)

        # ── Step 3: Private Match screen → Create Game ───────────────
        self.ctrl.navigate(self.seq.private_to_create)
        time.sleep(self.transition_wait)

        return True

    def start_match(self, start_sequence: list[str]) -> None:
        """Navigate to and press the Start Match button (inside lobby)."""
        self.ctrl.anchor()
        self.ctrl.navigate(start_sequence)
        self.ctrl.confirm()


# ═══════════════════════════════════════════════════════════════════════════
#  LOBBY COLUMNS
# ═══════════════════════════════════════════════════════════════════════════


class LobbyColumn(Enum):
    """The three navigable columns in the lobby screen."""
    DETAILS = auto()   # left  — match config dropdowns
    CENTER  = auto()   # mid   — unassigned players + spectators
    TEAMS   = auto()   # right — team 1 + team 2 slots


# ── Dropdown positions within the LEFT (details) column ───────────────────

class DropdownSlot(Enum):
    """Order of dropdowns in the match details column (top to bottom)."""
    GAME_MODE  = 0
    ARENA      = 1
    VARIANT    = 2
    CONDITION  = 3
    GAME_SHOW  = 4


# ═══════════════════════════════════════════════════════════════════════════
#  LOBBY GRID CONFIG
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class LobbyGrid:
    """
    Layout config for the 3-column lobby UI.

    CENTER column (anchor lands here):
      The unassigned list is dynamic.  With 1 player there are 2 rows
      (the player + 1 empty "---" slot).  With 8 players there are 9
      rows (8 players + 1 empty slot).  Spectators sit directly below.
      The bot figures out the total unassigned row count at runtime
      via OCR and passes it into placement methods.

    TEAMS column (RIGHT):
      Team 1 at the top (3 rows), Team 2 below (3 rows).
      If pressing Down from the last T1 slot goes straight to the
      first T2 slot, set gap_between_teams = 0.  If the cursor gets
      stuck on a non-selectable row between them, set it to 1.

    DETAILS column (LEFT):
      Game Mode (row 0), Arena (1), Variant (2), Condition (3),
      Game Show (4).

    CONTEXT MENU:
      The bot's own context menu has fewer options than other players'.
      "Move in Lobby" is at a different row for each.
    """

    # ── Teams column ──────────────────────────────────────────────────
    team1_rows: int = 3
    team2_rows: int = 3
    gap_between_teams: int = 0

    # ── Context menu offsets ──────────────────────────────────────────
    # D-pad Downs from the top of the context menu to "Move in Lobby"
    context_move_self: int = 1   # when selecting the bot itself
    context_move_other: int = 2  # when selecting another player

    # ── Dropdown anchoring ────────────────────────────────────────────
    # UP presses to guarantee the cursor is at index 0 inside an open
    # dropdown (mode, map, variant, condition, game show).  Dropdowns
    # don't wrap, so spamming UP past the top is harmless.
    dropdown_anchor_up: int = 14


# ═══════════════════════════════════════════════════════════════════════════
#  LOBBY NAVIGATOR
# ═══════════════════════════════════════════════════════════════════════════


class LobbyNavigator:
    """
    3-column lobby navigation and player placement.

    After anchor (B-spam) the cursor is on the first unassigned slot
    in the CENTER column.  LEFT/RIGHT switch columns, UP/DOWN move
    within the current column.
    """

    def __init__(
        self,
        controller: GamepadController,
        grid: Optional[LobbyGrid] = None,
        step_wait: float = 0.3,
    ):
        self.ctrl = controller
        self.grid = grid or LobbyGrid()
        self.step_wait = step_wait

        self._col = LobbyColumn.CENTER
        self._row = 0

    # ── Anchor / reset ────────────────────────────────────────────────

    def anchor(self) -> None:
        """B-spam → cursor resets to first unassigned slot in CENTER."""
        self.ctrl.anchor()
        self._col = LobbyColumn.CENTER
        self._row = 0

    # ── Column switching ──────────────────────────────────────────────

    def go_to_column(self, target: LobbyColumn) -> None:
        """Switch to a different column via LEFT/RIGHT."""
        if target == self._col:
            return

        if self._col == LobbyColumn.CENTER:
            if target == LobbyColumn.DETAILS:
                self.ctrl.press("left")
            else:  # TEAMS
                self.ctrl.press("right")
        elif self._col == LobbyColumn.DETAILS:
            self.ctrl.press("right")  # details → center
            if target == LobbyColumn.TEAMS:
                self.ctrl.press("right")  # center → teams
        elif self._col == LobbyColumn.TEAMS:
            self.ctrl.press("left")   # teams → center
            if target == LobbyColumn.DETAILS:
                self.ctrl.press("left")  # center → details

        self._col = target
        self._row = 0  # column switch likely resets vertical position
        time.sleep(self.step_wait)

    # ── Row navigation (within current column) ────────────────────────

    def go_to_row(self, target_row: int) -> None:
        """Move UP/DOWN within the current column to a specific row."""
        diff = target_row - self._row
        if diff == 0:
            return
        direction = "down" if diff > 0 else "up"
        self.ctrl.press(direction, abs(diff))
        self._row = target_row

    # ── Center column helpers ─────────────────────────────────────────

    def go_to_unassigned(self, slot: int) -> None:
        """Navigate to an unassigned player slot (0-based) in CENTER."""
        if self._col != LobbyColumn.CENTER:
            self.anchor()
        self.go_to_row(slot)

    def go_to_spectator(self, slot: int, unassigned_total: int) -> None:
        """
        Navigate to a spectator slot in CENTER.

        Args:
            slot: 0-based spectator slot index (0, 1, or 2).
            unassigned_total: total visible unassigned rows including
                              empty trailing slots.  E.g. 8 players
                              + 1 empty "---" = 9.
        """
        if self._col != LobbyColumn.CENTER:
            self.anchor()
        self.go_to_row(unassigned_total + slot)

    # ── Teams column helpers ──────────────────────────────────────────

    def go_to_team_slot(self, team: int, slot: int) -> None:
        """
        Navigate to a team slot.

        Args:
            team: 1 or 2.
            slot: 0-based position within the team.
        """
        self.go_to_column(LobbyColumn.TEAMS)
        if team == 1:
            self.go_to_row(slot)
        else:
            row = self.grid.team1_rows + self.grid.gap_between_teams + slot
            self.go_to_row(row)

    # ── Details column helpers ────────────────────────────────────────

    def go_to_dropdown(self, dropdown: DropdownSlot) -> None:
        """Navigate to a specific dropdown in the match details column."""
        self.go_to_column(LobbyColumn.DETAILS)
        self.go_to_row(dropdown.value)

    def select_dropdown_option(self, dropdown: DropdownSlot, option_index: int) -> None:
        """
        Open a dropdown and pick an option by index.

        Anchors to index 0 first by spamming UP (``dropdown_anchor_up``
        presses) — dropdown lists don't wrap, so this guarantees we're
        at the top regardless of any previously-highlighted entry.
        Then counts DOWN to the target.

        Args:
            dropdown: Which dropdown (GAME_MODE, ARENA, etc.).
            option_index: Zero-based position of the desired option.
        """
        self.go_to_dropdown(dropdown)
        self.ctrl.confirm()
        time.sleep(self.step_wait)

        # Anchor to top of the dropdown list
        self.ctrl.press("up", self.grid.dropdown_anchor_up)
        time.sleep(self.step_wait)

        if option_index > 0:
            self.ctrl.press("down", option_index)
        self.ctrl.confirm()
        time.sleep(self.step_wait)
        self._row = dropdown.value

    # ── Player placement ──────────────────────────────────────────────

    def _open_move_in_lobby(self, unassigned_slot: int, is_bot: bool) -> None:
        """
        Navigate to a player, open context menu, select "Move in Lobby".

        Args:
            unassigned_slot: 0-based row in the unassigned list.
            is_bot: True if selecting the bot itself (fewer menu items).
        """
        self.anchor()
        self.go_to_row(unassigned_slot)
        time.sleep(self.step_wait)

        # Open context menu
        self.ctrl.confirm()
        time.sleep(self.step_wait)

        # Navigate to "Move in Lobby" (different offset for bot vs others)
        offset = self.grid.context_move_self if is_bot else self.grid.context_move_other
        self.ctrl.press("down", offset)
        self.ctrl.confirm()
        time.sleep(self.step_wait)

    def move_player_to_team(
        self,
        unassigned_slot: int,
        team: int,
        team_slot: int,
        is_bot: bool = False,
    ) -> None:
        """
        Move a player from the unassigned list to a team slot.

        Args:
            unassigned_slot: 0-based index in the unassigned list.
            team: 1 or 2.
            team_slot: 0-based position within the team.
            is_bot: True if moving the bot itself.
        """
        self._open_move_in_lobby(unassigned_slot, is_bot)

        # Placement mode — RIGHT to teams column, DOWN to slot
        self.ctrl.press("right")
        time.sleep(self.step_wait)

        if team == 1:
            target_row = team_slot
        else:
            target_row = self.grid.team1_rows + self.grid.gap_between_teams + team_slot

        if target_row > 0:
            self.ctrl.press("down", target_row)

        self.ctrl.confirm()
        time.sleep(self.step_wait)

    def move_bot_to_spectator(
        self,
        bot_slot: int,
        unassigned_total: int,
        spectator_slot: int = 0,
    ) -> None:
        """
        Move the bot to a spectator slot.

        Args:
            bot_slot: 0-based row where the bot sits in unassigned.
            unassigned_total: total visible unassigned rows (players
                              + empty slots).
            spectator_slot: 0-based spectator slot (0, 1, or 2).
        """
        self._open_move_in_lobby(bot_slot, is_bot=True)

        # In placement mode, spectators are below unassigned in CENTER.
        spec_row = unassigned_total + spectator_slot
        if spec_row > 0:
            self.ctrl.press("down", spec_row)

        self.ctrl.confirm()
        time.sleep(self.step_wait)
