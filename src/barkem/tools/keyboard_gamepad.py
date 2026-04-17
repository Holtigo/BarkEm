"""
Keyboard → Virtual Gamepad Emulator

Maps your keyboard to a virtual Xbox 360 controller so you can test
D-pad navigation without a physical gamepad.

Usage:
    python -m barkem.tools.keyboard_gamepad

Keybindings:
    Arrow keys  →  D-pad
    Enter       →  A (confirm)
    Backspace   →  B (cancel / anchor)
    Space       →  Start
    Tab         →  Back / Select
    X           →  X button
    Y           →  Y button
    L           →  LB             R           →  RB
    ,           →  LT             .           →  RT
    [           →  LS (click)     ]           →  RS (click)
    Escape      →  Quit

Requires: pip install keyboard vgamepad
"""

import sys
import time

try:
    import keyboard
except ImportError:
    print("Install the keyboard package:  pip install keyboard")
    print("Note: requires admin/root on Linux.")
    sys.exit(1)

try:
    import vgamepad as vg
except ImportError:
    print("Install vgamepad + ViGEmBus driver:")
    print("  pip install vgamepad")
    print("  https://github.com/ViGEm/ViGEmBus/releases")
    sys.exit(1)


# ── Key → Button mapping ─────────────────────────────────────────────────

# Button keys — a simple press_button() works for these.
KEYMAP = {
    "up":        vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
    "down":      vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
    "left":      vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
    "right":     vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
    "enter":     vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
    "backspace": vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
    "space":     vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
    "tab":       vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
    "x":         vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
    "y":         vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
    "l":         vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
    "r":         vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
    "[":         vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_THUMB,
    "]":         vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB,
}

# Trigger keys — triggers are analog axes in XInput, so pulse them
# to max and back to 0 instead of using press_button().
TRIGGERMAP = {
    ",": "left_trigger",
    ".": "right_trigger",
}

HOLD_MS = 80          # how long the virtual button stays held (ms)
COOLDOWN_MS = 150     # minimum gap between repeated presses of the same key


def main():
    print("=" * 60)
    print("  BarkEm Keyboard → Gamepad Emulator")
    print("=" * 60)
    print()
    print("  Arrows → D-pad    Enter → A    Backspace → B")
    print("  Space  → Start    Tab   → Back")
    print("  X → X   Y → Y    L → LB   R → RB")
    print("  , → LT  . → RT    [ → LS (click)   ] → RS (click)")
    print()
    print("  Keys are SUPPRESSED — they won't reach the game as")
    print("  keyboard input (no accidental chat opens).")
    print()
    print("  Press ESC to quit.")
    print()

    pad = vg.VX360Gamepad()
    pad.reset()
    pad.update()
    print("  Virtual gamepad connected.")
    print()

    import threading

    last_press: dict[str, float] = {}
    lock = threading.Lock()

    def tap(key: str):
        """Press-hold-release with cooldown to prevent skipping."""
        now = time.time()
        with lock:
            prev = last_press.get(key, 0)
            if (now - prev) * 1000 < COOLDOWN_MS:
                return  # too soon, ignore repeat
            last_press[key] = now

        label = key.upper().rjust(10)
        print(f"  ▼ {label}")

        if key in TRIGGERMAP:
            axis = TRIGGERMAP[key]
            getattr(pad, axis)(value=255)
            pad.update()
            time.sleep(HOLD_MS / 1000)
            getattr(pad, axis)(value=0)
            pad.update()
        else:
            btn = KEYMAP[key]
            pad.press_button(btn)
            pad.update()
            time.sleep(HOLD_MS / 1000)
            pad.release_button(btn)
            pad.update()

    # Register each key individually with suppress=True so the
    # original keystroke never reaches the foreground window.
    for key_name in list(KEYMAP) + list(TRIGGERMAP):
        keyboard.on_press_key(key_name, lambda e, k=key_name: tap(k), suppress=True)

    try:
        keyboard.wait("esc")
    except KeyboardInterrupt:
        pass

    # Cleanup
    pad.reset()
    pad.update()
    keyboard.unhook_all()
    print()
    print("  Gamepad disconnected. Bye!")


if __name__ == "__main__":
    main()
