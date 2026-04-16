"""
Input simulation using pydirectinput.

Uses click-based "Move in Lobby" workflow instead of drag-and-drop:
  1. Click player in unassigned list → context menu opens
  2. Click "Move in Lobby" in context menu
  3. Click destination slot (team or spectator)

Uses SendInput() with DirectInput scan codes — same input path as physical
hardware. No known EAC detection signatures.
"""

import random
import time
from dataclasses import dataclass
from typing import Optional

import pydirectinput

from barkem.vision.regions import ClickTarget


@dataclass
class InputConfig:
    """Configuration for input simulation."""

    click_delay_min: float = 0.1
    click_delay_max: float = 0.3
    typing_interval: float = 0.1
    humanize_movement: bool = True
    # Pause between steps in multi-click workflows (context menu, placement)
    workflow_step_delay_min: float = 0.3
    workflow_step_delay_max: float = 0.6


class InputController:
    """
    Handles mouse and keyboard input simulation.

    All player movement uses the click-based "Move in Lobby" approach:
    no dragging needed.
    """

    def __init__(self, config: Optional[InputConfig] = None):
        self.config = config or InputConfig()

    # ── Low-Level Input ────────────────────────────────────────────────────

    def _random_delay(self, min_val: float, max_val: float) -> None:
        """Sleep for a random duration within range."""
        time.sleep(random.uniform(min_val, max_val))

    def _workflow_pause(self) -> None:
        """Pause between steps in a multi-click workflow."""
        self._random_delay(
            self.config.workflow_step_delay_min,
            self.config.workflow_step_delay_max,
        )

    def move_to(self, x: int, y: int, duration: Optional[float] = None) -> None:
        """
        Move mouse to coordinates.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
            duration: Optional movement duration in seconds.
        """
        if duration is None:
            duration = random.uniform(0.1, 0.3)

        pydirectinput.moveTo(x, y, duration=duration)

    def click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """
        Click at coordinates (or current position if not specified).

        Args:
            x: Optional X coordinate.
            y: Optional Y coordinate.
        """
        if x is not None and y is not None:
            self.move_to(x, y)
            self._random_delay(0.05, 0.15)  # Settle time

        pydirectinput.click()
        self._random_delay(self.config.click_delay_min, self.config.click_delay_max)

    def click_target(self, target: ClickTarget) -> None:
        """Click a ClickTarget from the regions config."""
        self.click(target.x, target.y)

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """Double-click at coordinates."""
        if x is not None and y is not None:
            self.move_to(x, y)
            self._random_delay(0.05, 0.15)

        pydirectinput.doubleClick()
        self._random_delay(self.config.click_delay_min, self.config.click_delay_max)

    def type_text(self, text: str) -> None:
        """
        Type text with human-like intervals.

        Args:
            text: Text to type.
        """
        for char in text:
            pydirectinput.press(char.lower())
            interval = self.config.typing_interval
            self._random_delay(interval * 0.5, interval * 1.5)

    def press(self, key: str) -> None:
        """
        Press a single key.

        Args:
            key: Key to press (e.g., 'enter', 'escape', 'p').
        """
        pydirectinput.press(key)
        self._random_delay(0.05, 0.15)

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> None:
        """
        Scroll the mouse wheel.

        Args:
            clicks: Number of scroll clicks. Positive = up, negative = down.
            x: Optional X coordinate to scroll at.
            y: Optional Y coordinate to scroll at.
        """
        if x is not None and y is not None:
            self.move_to(x, y)
            self._random_delay(0.05, 0.1)

        pydirectinput.scroll(clicks)
        self._random_delay(0.1, 0.2)

    # ── High-Level: Move in Lobby Workflow ─────────────────────────────────

    def move_player_via_context_menu(
            self,
            player_slot_click: ClickTarget,
            move_in_lobby_button: ClickTarget,
            destination_slot_click: ClickTarget,
    ) -> None:
        """
        Move a player to a team/spectator slot using the "Move in Lobby" workflow.

        Steps:
          1. Click the player's slot in the unassigned list → context menu opens
          2. Click "Move in Lobby" in the context menu → placement mode
          3. Click the destination slot → player is moved

        Args:
            player_slot_click: Where to click to select the player (opens context menu).
            move_in_lobby_button: The "Move in Lobby" button in the context menu.
                                  Use context_menu.move_in_lobby_self for the bot,
                                  or context_menu.move_in_lobby_other for other players.
            destination_slot_click: The target slot to place the player into
                                   (e.g., team1_slot1_click, spectator_slot1_click).
        """
        # Step 1: Click on the player to open context menu
        self.click_target(player_slot_click)
        self._workflow_pause()

        # Step 2: Click "Move in Lobby"
        self.click_target(move_in_lobby_button)
        self._workflow_pause()

        # Step 3: Click the destination slot
        self.click_target(destination_slot_click)
        self._workflow_pause()

    def move_bot_to_spectator(
            self,
            bot_slot_click: ClickTarget,
            move_in_lobby_self: ClickTarget,
            spectator_slot_click: ClickTarget,
    ) -> None:
        """
        Move the bot itself to a spectator slot.

        Uses move_in_lobby_self since the bot's context menu has
        fewer options than other players'.

        Args:
            bot_slot_click: Where the bot appears in the unassigned list.
            move_in_lobby_self: The "Move in Lobby" button for the bot.
            spectator_slot_click: The spectator slot to place the bot into.
        """
        self.move_player_via_context_menu(
            player_slot_click=bot_slot_click,
            move_in_lobby_button=move_in_lobby_self,
            destination_slot_click=spectator_slot_click,
        )

    def move_player_to_team(
            self,
            player_slot_click: ClickTarget,
            move_in_lobby_other: ClickTarget,
            team_slot_click: ClickTarget,
    ) -> None:
        """
        Move another player to a team slot.

        Uses move_in_lobby_other since other players' context menus have
        more options than the bot's.

        Args:
            player_slot_click: Where the player appears in the unassigned list.
            move_in_lobby_other: The "Move in Lobby" button for other players.
            team_slot_click: The team slot to place the player into.
        """
        self.move_player_via_context_menu(
            player_slot_click=player_slot_click,
            move_in_lobby_button=move_in_lobby_other,
            destination_slot_click=team_slot_click,
        )

    # ── High-Level: Menu Navigation ────────────────────────────────────────

    def click_sequence(self, *targets: ClickTarget, delay: Optional[float] = None) -> None:
        """
        Click a sequence of targets with pauses between each.

        Useful for menu navigation (Play → Private Match → Create Game).

        Args:
            *targets: ClickTarget instances to click in order.
            delay: Optional override for the pause between clicks.
        """
        for target in targets:
            self.click_target(target)
            if delay is not None:
                time.sleep(delay)
            else:
                self._workflow_pause()

    # ── High-Level: Dropdown Selection ─────────────────────────────────────

    def select_from_dropdown(
            self,
            dropdown_opener: ClickTarget,
            option: ClickTarget,
            scroll_clicks: int = 0,
    ) -> None:
        """
        Open a dropdown and select an option, with optional scrolling.

        Args:
            dropdown_opener: Click target to open the dropdown.
            option: Click target for the desired option.
            scroll_clicks: Number of scroll clicks needed to reach the option.
                           Positive = scroll up, negative = scroll down.
        """
        # Open the dropdown
        self.click_target(dropdown_opener)
        self._workflow_pause()

        # Scroll if needed
        if scroll_clicks != 0:
            # Scroll at the dropdown's position
            self.scroll(scroll_clicks, dropdown_opener.x, dropdown_opener.y)
            self._random_delay(0.2, 0.4)

        # Click the option
        self.click_target(option)
        self._workflow_pause()