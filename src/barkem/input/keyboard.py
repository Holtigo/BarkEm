"""
Virtual keyboard input — cross-platform.

Windows: pynput.keyboard (user-space input injection)
Linux:   evdev UInput keyboard device

Used alongside GamepadController when the bot needs to type chat
messages (Phase 5 pause-countdown flow).  The gamepad on-screen
keyboard would work but is ~10x slower.

Both backends speak the same tiny API:

    kb = KeyboardController()
    kb.connect()
    kb.type_string("Pausing in 3...")
    kb.press_enter()
    kb.disconnect()
"""

import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class KeyboardConfig:
    """Timing for virtual keyboard input."""

    key_delay: float = 0.02       # delay between individual key presses
    enter_delay: float = 0.1      # delay after Enter (message send)
    verbose: bool = False


# ── Abstract backend ──────────────────────────────────────────────────────

class _KeyboardBackend(ABC):

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def type_char(self, ch: str) -> None: ...

    @abstractmethod
    def press_enter(self) -> None: ...


# ── Windows backend (pynput) ──────────────────────────────────────────────

class _WindowsKeyboardBackend(_KeyboardBackend):

    def __init__(self):
        self._kb = None
        self._Key = None

    def connect(self) -> None:
        from pynput.keyboard import Controller, Key
        self._kb = Controller()
        self._Key = Key

    def disconnect(self) -> None:
        self._kb = None
        self._Key = None

    def type_char(self, ch: str) -> None:
        """
        Explicit press/release instead of pynput's high-level ``type()``.

        ``Controller.type(ch)`` wraps shift-modified keys as
        ``shift↓ key↓ key↑ shift↑`` back-to-back with no gaps, which
        The Finals' chat widget has been observed to mis-sample — the
        first real uppercase letter after a burst of lowercase input
        (e.g. leading spaces) is dropped outright.  Inserting a tiny
        sleep on each side of the key press gives the receiving end
        time to latch the modifier state before the key event.
        """
        import time as _t
        if ch.isupper() or ch in '!@#$%^&*()_+{}|:"<>?~':
            self._kb.press(self._Key.shift)
            _t.sleep(0.008)
            self._kb.press(ch)
            _t.sleep(0.008)
            self._kb.release(ch)
            _t.sleep(0.008)
            self._kb.release(self._Key.shift)
        else:
            self._kb.press(ch)
            _t.sleep(0.008)
            self._kb.release(ch)

    def press_enter(self) -> None:
        self._kb.press(self._Key.enter)
        self._kb.release(self._Key.enter)


# ── Linux backend (evdev/uinput) ──────────────────────────────────────────

class _LinuxKeyboardBackend(_KeyboardBackend):
    """
    Creates a second UInput device (keyboard) alongside the gamepad one.

    Only handles the printable ASCII subset we need for chat messages
    plus Enter.  No shift/ctrl handling for special characters.
    """

    def __init__(self):
        self._device = None
        self._keymap = None

    def connect(self) -> None:
        from evdev import UInput, ecodes

        # Minimum keymap: lowercase letters + digits + space + enter
        # + a few symbols used in countdown messages ('.', '-').
        self._keymap = {
            " ": (ecodes.KEY_SPACE, False),
            ".": (ecodes.KEY_DOT, False),
            ",": (ecodes.KEY_COMMA, False),
            "-": (ecodes.KEY_MINUS, False),
            "_": (ecodes.KEY_MINUS, True),
            "!": (ecodes.KEY_1, True),
            ":": (ecodes.KEY_SEMICOLON, True),
            ";": (ecodes.KEY_SEMICOLON, False),
            "'": (ecodes.KEY_APOSTROPHE, False),
            "/": (ecodes.KEY_SLASH, False),
            "\n": (ecodes.KEY_ENTER, False),
        }
        for i, ch in enumerate("0123456789"):
            self._keymap[ch] = (getattr(ecodes, f"KEY_{ch}"), False)
        for ch in "abcdefghijklmnopqrstuvwxyz":
            self._keymap[ch] = (getattr(ecodes, f"KEY_{ch.upper()}"), False)
            self._keymap[ch.upper()] = (getattr(ecodes, f"KEY_{ch.upper()}"), True)

        # Capabilities: every key we might emit + LEFTSHIFT for upper/symbol
        keycodes = {code for code, _ in self._keymap.values()}
        keycodes.add(ecodes.KEY_LEFTSHIFT)
        keycodes.add(ecodes.KEY_ENTER)

        capabilities = {ecodes.EV_KEY: sorted(keycodes)}
        self._device = UInput(
            events=capabilities,
            name="BarkEm Virtual Keyboard",
        )

    def disconnect(self) -> None:
        if self._device:
            self._device.close()
            self._device = None

    def type_char(self, ch: str) -> None:
        from evdev import ecodes
        if ch not in self._keymap:
            return
        code, shift = self._keymap[ch]
        if shift:
            self._device.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)
        self._device.write(ecodes.EV_KEY, code, 1)
        self._device.syn()
        self._device.write(ecodes.EV_KEY, code, 0)
        if shift:
            self._device.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
        self._device.syn()

    def press_enter(self) -> None:
        from evdev import ecodes
        self._device.write(ecodes.EV_KEY, ecodes.KEY_ENTER, 1)
        self._device.syn()
        self._device.write(ecodes.EV_KEY, ecodes.KEY_ENTER, 0)
        self._device.syn()


# ── Public controller ─────────────────────────────────────────────────────

def _create_keyboard_backend() -> _KeyboardBackend:
    if sys.platform == "win32":
        return _WindowsKeyboardBackend()
    elif sys.platform.startswith("linux"):
        return _LinuxKeyboardBackend()
    raise RuntimeError(f"Unsupported platform: {sys.platform}")


class KeyboardController:
    """
    Virtual keyboard used for typing chat messages.

    Separate from GamepadController so the two can co-exist without
    conflicting — The Finals accepts both simultaneously.
    """

    def __init__(self, config: Optional[KeyboardConfig] = None):
        self.config = config or KeyboardConfig()
        self._backend: Optional[_KeyboardBackend] = None

    def connect(self) -> None:
        if self._backend is None:
            self._backend = _create_keyboard_backend()
        self._backend.connect()

    def disconnect(self) -> None:
        if self._backend:
            self._backend.disconnect()
            self._backend = None

    @property
    def backend(self) -> _KeyboardBackend:
        if self._backend is None:
            self.connect()
        return self._backend

    def type_string(self, text: str) -> None:
        if self.config.verbose:
            print(f"    [kb] type {text!r}")
        for ch in text:
            self.backend.type_char(ch)
            time.sleep(self.config.key_delay)

    def press_enter(self) -> None:
        if self.config.verbose:
            print("    [kb] Enter")
        self.backend.press_enter()
        time.sleep(self.config.enter_delay)

    def send_message(self, text: str, warmup_delay: float = 0.0) -> None:
        """Type a message and press Enter.

        A short leading-space prefix absorbs any first-keystroke
        hiccup when chat opens (GeForce NOW occasionally drops the
        very first character after a gamepad→keyboard focus swap).
        Trailing spaces are invisible in chat so this is harmless.

        The real first-letter-dropping bug we hit earlier turned out
        to be pynput's ``Controller.type()`` mishandling uppercase /
        shift-modified keys on The Finals' chat widget — addressed by
        typing in lowercase at the caller level, not here.

        ``warmup_delay`` is kept for callers that want a longer
        settle after chat-open before real text lands.
        """
        if not text:
            self.press_enter()
            return

        for _ in range(3):
            self.backend.type_char(" ")
            time.sleep(self.config.key_delay)

        if warmup_delay > 0:
            time.sleep(warmup_delay)

        self.type_string(text)
        self.press_enter()
