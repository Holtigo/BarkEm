"""
XInput controller emulation — cross-platform.

Windows: vgamepad + ViGEmBus (virtual Xbox 360 controller)
Linux:   evdev + uinput (kernel-native virtual gamepad)

The backend is selected automatically based on the OS.
All downstream code uses GamepadController without caring which.
"""

import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


# ── Config ────────────────────────────────────────────────────────────────

@dataclass
class GamepadConfig:
    """Timing config for gamepad input."""

    button_delay: float = 0.15
    hold_duration: float = 0.05
    anchor_presses: int = 5
    anchor_settle: float = 0.3


# ── Abstract backend ──────────────────────────────────────────────────────

class _GamepadBackend(ABC):
    """Minimal interface each OS backend must implement."""

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def press_button(self, button: str) -> None: ...

    @abstractmethod
    def release_button(self, button: str) -> None: ...


# ── Windows backend (vgamepad) ────────────────────────────────────────────

class _WindowsBackend(_GamepadBackend):

    def __init__(self):
        self._pad = None
        self._button_map = None

    def connect(self) -> None:
        import vgamepad as vg

        self._button_map = {
            "a": vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
            "b": vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
            "x": vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
            "y": vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
            "start": vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
            "back": vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
            "up": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
            "down": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
            "left": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
            "right": vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
            "lb": vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
            "rb": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
        }
        self._pad = vg.VX360Gamepad()
        self._pad.reset()
        self._pad.update()

    def disconnect(self) -> None:
        if self._pad:
            self._pad.reset()
            self._pad.update()
            self._pad = None

    def press_button(self, button: str) -> None:
        self._pad.press_button(self._button_map[button])
        self._pad.update()

    def release_button(self, button: str) -> None:
        self._pad.release_button(self._button_map[button])
        self._pad.update()


# ── Linux backend (evdev / uinput) ────────────────────────────────────────

class _LinuxBackend(_GamepadBackend):

    def __init__(self):
        self._device = None
        self._button_map = None

    def connect(self) -> None:
        import evdev
        from evdev import UInput, ecodes, AbsInfo

        self._button_map = {
            "a": ecodes.BTN_SOUTH,
            "b": ecodes.BTN_EAST,
            "x": ecodes.BTN_WEST,
            "y": ecodes.BTN_NORTH,
            "start": ecodes.BTN_START,
            "back": ecodes.BTN_SELECT,
            "lb": ecodes.BTN_TL,
            "rb": ecodes.BTN_TR,
            # D-pad uses ABS hat axes, handled specially
            "up": "hat_up",
            "down": "hat_down",
            "left": "hat_left",
            "right": "hat_right",
        }

        capabilities = {
            ecodes.EV_KEY: [
                ecodes.BTN_SOUTH, ecodes.BTN_EAST,
                ecodes.BTN_WEST, ecodes.BTN_NORTH,
                ecodes.BTN_START, ecodes.BTN_SELECT,
                ecodes.BTN_TL, ecodes.BTN_TR,
            ],
            ecodes.EV_ABS: [
                (ecodes.ABS_HAT0X, AbsInfo(0, -1, 1, 0, 0, 0)),
                (ecodes.ABS_HAT0Y, AbsInfo(0, -1, 1, 0, 0, 0)),
            ],
        }

        self._device = UInput(
            events=capabilities,
            name="BarkEm Virtual Gamepad",
            vendor=0x045E,   # Microsoft
            product=0x028E,  # Xbox 360 Controller
        )

    def disconnect(self) -> None:
        if self._device:
            self._device.close()
            self._device = None

    def press_button(self, button: str) -> None:
        from evdev import ecodes

        mapped = self._button_map[button]
        if mapped == "hat_up":
            self._device.write(ecodes.EV_ABS, ecodes.ABS_HAT0Y, -1)
        elif mapped == "hat_down":
            self._device.write(ecodes.EV_ABS, ecodes.ABS_HAT0Y, 1)
        elif mapped == "hat_left":
            self._device.write(ecodes.EV_ABS, ecodes.ABS_HAT0X, -1)
        elif mapped == "hat_right":
            self._device.write(ecodes.EV_ABS, ecodes.ABS_HAT0X, 1)
        else:
            self._device.write(ecodes.EV_KEY, mapped, 1)
        self._device.syn()

    def release_button(self, button: str) -> None:
        from evdev import ecodes

        mapped = self._button_map[button]
        if mapped in ("hat_up", "hat_down"):
            self._device.write(ecodes.EV_ABS, ecodes.ABS_HAT0Y, 0)
        elif mapped in ("hat_left", "hat_right"):
            self._device.write(ecodes.EV_ABS, ecodes.ABS_HAT0X, 0)
        else:
            self._device.write(ecodes.EV_KEY, mapped, 0)
        self._device.syn()


# ── Public controller (backend-agnostic) ──────────────────────────────────

VALID_BUTTONS = {"a", "b", "x", "y", "start", "back", "up", "down", "left", "right", "lb", "rb"}


def _create_backend() -> _GamepadBackend:
    if sys.platform == "win32":
        return _WindowsBackend()
    elif sys.platform.startswith("linux"):
        return _LinuxBackend()
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")


class GamepadController:
    """
    Virtual gamepad for UI navigation.

    Identical API on Windows and Linux — backend is selected automatically.
    """

    def __init__(self, config: Optional[GamepadConfig] = None):
        self.config = config or GamepadConfig()
        self._backend: Optional[_GamepadBackend] = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    def connect(self) -> None:
        if self._backend is None:
            self._backend = _create_backend()
        self._backend.connect()

    def disconnect(self) -> None:
        if self._backend:
            self._backend.disconnect()
            self._backend = None

    @property
    def backend(self) -> _GamepadBackend:
        if self._backend is None:
            self.connect()
        return self._backend

    # ── Low-level ──────────────────────────────────────────────────────

    def press(self, button: str, count: int = 1) -> None:
        button = button.lower()
        for _ in range(count):
            self.backend.press_button(button)
            time.sleep(self.config.hold_duration)
            self.backend.release_button(button)
            time.sleep(self.config.button_delay)

    # ── Mid-level ─────────────────────────────────────────────────────

    def anchor(self, presses: Optional[int] = None) -> None:
        self.press("b", presses or self.config.anchor_presses)
        time.sleep(self.config.anchor_settle)

    def navigate(self, sequence: list[str]) -> None:
        for action in sequence:
            self.press(action)

    def navigate_relative(self, direction: str, count: int) -> None:
        if count > 0:
            self.press(direction, count)

    def confirm(self) -> None:
        self.press("a")

    def cancel(self) -> None:
        self.press("b")

    def pause_toggle(self) -> None:
        self.press("start")
