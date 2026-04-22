"""
Input module — XInput controller emulation and UI navigation.
"""

from barkem.input.controller import GamepadController, GamepadConfig
from barkem.input.keyboard import KeyboardController, KeyboardConfig
from barkem.input.navigator import (
    MenuNavigator, MenuSequences,
    LobbyNavigator, LobbyGrid, LobbyColumn, DropdownSlot,
)
from barkem.input.window import WindowManager

__all__ = [
    "GamepadController",
    "GamepadConfig",
    "KeyboardController",
    "KeyboardConfig",
    "MenuNavigator",
    "MenuSequences",
    "LobbyNavigator",
    "LobbyGrid",
    "LobbyColumn",
    "DropdownSlot",
    "WindowManager",
]
