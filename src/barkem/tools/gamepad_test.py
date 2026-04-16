"""
BarkEm Gamepad Test & Calibration Tool

Test that the virtual gamepad works and calibrate D-pad navigation
sequences by watching what happens on screen.

Usage:
    python -m barkem.tools.gamepad_test              # Interactive test
    python -m barkem.tools.gamepad_test --sequence    # Run a D-pad sequence
    python -m barkem.tools.gamepad_test --anchor      # Test B-spam anchor

The interactive mode lets you type button names to send them one at a
time, so you can count presses while watching the game.
"""

import argparse
import sys
import time


def check_vgamepad():
    try:
        import vgamepad  # noqa: F401
        return True
    except ImportError:
        print("[!] vgamepad not installed.")
        print("    pip install vgamepad")
        print("    Also install ViGEmBus: https://github.com/ViGEm/ViGEmBus/releases")
        return False


def run_interactive():
    """Interactive button sender — type a button name, it gets pressed."""
    from barkem.input.controller import GamepadController, VALID_BUTTONS

    print("=" * 60)
    print("  BarkEm Gamepad Interactive Test")
    print("=" * 60)
    print()
    print(f"  Available buttons: {', '.join(sorted(VALID_BUTTONS))}")
    print()
    print("  Type a button name and press Enter to send it.")
    print("  Type a number after (e.g. 'down 3') to repeat.")
    print("  Type 'anchor' to test B-spam anchoring.")
    print("  Type 'seq a,down,down,a' to run a sequence.")
    print("  Type 'quit' to exit.")
    print()

    ctrl = GamepadController()
    ctrl.connect()
    print("  Virtual gamepad connected.")
    print()

    press_count = 0

    try:
        while True:
            raw = input("  > ").strip().lower()
            if not raw:
                continue
            if raw in ("quit", "q", "exit"):
                break

            if raw == "anchor":
                print("    Anchoring (5x B)...")
                ctrl.anchor()
                press_count = 0
                print(f"    Done. Position reset to 0.")
                continue

            if raw.startswith("seq "):
                seq = [s.strip() for s in raw[4:].split(",") if s.strip()]
                print(f"    Running sequence: {seq}")
                ctrl.navigate(seq)
                # Track position for D-pad directions
                for s in seq:
                    if s == "down":
                        press_count += 1
                    elif s == "up":
                        press_count -= 1
                print(f"    Done. Estimated position: {press_count}")
                continue

            parts = raw.split()
            button = parts[0]
            count = int(parts[1]) if len(parts) > 1 else 1

            if button not in VALID_BUTTONS:
                print(f"    Unknown button '{button}'")
                continue

            ctrl.press(button, count)

            # Track position
            if button == "down":
                press_count += count
            elif button == "up":
                press_count -= count
            elif button == "b":
                pass  # don't track B, use anchor to reset

            print(f"    Pressed {button} x{count}  (position ≈ {press_count})")

    except (KeyboardInterrupt, EOFError):
        pass

    ctrl.disconnect()
    print()
    print("  Gamepad disconnected.")


def run_sequence(sequence_str: str):
    """Run a comma-separated button sequence."""
    from barkem.input.controller import GamepadController

    seq = [s.strip() for s in sequence_str.split(",") if s.strip()]
    print(f"Running sequence: {seq}")

    ctrl = GamepadController()
    ctrl.connect()

    print("Anchoring first...")
    ctrl.anchor()
    time.sleep(0.5)

    print("Executing sequence...")
    ctrl.navigate(seq)

    print("Done.")
    ctrl.disconnect()


def run_anchor():
    """Test anchoring."""
    from barkem.input.controller import GamepadController

    ctrl = GamepadController()
    ctrl.connect()

    print("Pressing B x5 (anchor)...")
    ctrl.anchor()
    print("Done. The game UI should be at its root state.")

    ctrl.disconnect()


def main():
    parser = argparse.ArgumentParser(
        description="BarkEm Gamepad Test & Calibration Tool",
    )
    parser.add_argument(
        "--sequence", "-s", type=str, default=None,
        help="Run a comma-separated button sequence (e.g. 'down,down,a')",
    )
    parser.add_argument(
        "--anchor", action="store_true",
        help="Test B-spam anchoring",
    )
    args = parser.parse_args()

    if not check_vgamepad():
        sys.exit(1)

    if args.anchor:
        run_anchor()
    elif args.sequence:
        run_sequence(args.sequence)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
