"""
Phase 5 test tool — live in-match chat watcher.

Continuously:
  1. Holds Menu to open in-match chat
  2. OCRs ``regions.chat.in_match_chat_area``
  3. Presses B to close chat
  4. Prints parsed messages + any -em pause / -em unpause / -em continue
     commands from named captains
  5. Sleeps ``--poll`` seconds, repeats

Use this to calibrate the in-match chat region and the
``menu_hold_duration`` / ``chat_open_settle`` timings before running
the full match monitor.  Unlike ``ready_watch`` (which polls a
persistent lobby chat), this tool actually drives the controller to
open chat each tick.

Usage:
    python -m barkem.tools.match_chat_watch --captain1 Alice#1234
    python -m barkem.tools.match_chat_watch --captain1 A#1234 --captain2 B#5678 --poll 3
    python -m barkem.tools.match_chat_watch --raw        # dump raw OCR lines too
"""

import argparse
import time

from barkem.config import get_settings
from barkem.input.controller import GamepadConfig, GamepadController
from barkem.vision.capture import ScreenCapture
from barkem.vision.chat import ChatReader
from barkem.vision.ocr import TextReader
from barkem.vision.regions import load_regions_from_dict


def main() -> None:
    p = argparse.ArgumentParser(
        description="BarkEm — live in-match chat watcher (hold-Menu + OCR)"
    )
    p.add_argument("--captain1", default=None)
    p.add_argument("--captain2", default=None)
    p.add_argument("--poll", type=float, default=5.0,
                   help="Seconds between chat-open polls.  Default 5.")
    p.add_argument("--hold", type=float, default=None,
                   help="Menu hold duration.  Default from settings.")
    p.add_argument("--settle", type=float, default=None,
                   help="Wait after opening chat before OCR.  Default from settings.")
    p.add_argument("--raw", action="store_true")
    p.add_argument("--delay", type=int, default=3)
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    settings = get_settings()
    hold = args.hold if args.hold is not None else settings.monitoring.menu_hold_duration
    settle = args.settle if args.settle is not None else settings.monitoring.chat_open_settle

    regions = load_regions_from_dict(settings.regions)
    chat_region = regions.chat.in_match_chat_area
    if chat_region.is_zero:
        p.error(
            "regions.chat.in_match_chat_area is [0,0,0,0] — configure it in "
            "settings.yaml first."
        )

    reader = TextReader(
        upscale_factor=settings.vision.ocr_upscale_factor,
        tesseract_cmd=settings.vision.tesseract_cmd,
    )
    chat = ChatReader(chat_region=chat_region.as_tuple(), text_reader=reader)

    pad = GamepadController(
        config=GamepadConfig(
            button_delay=settings.input.button_delay,
            hold_duration=settings.input.hold_duration,
            verbose=args.debug,
        )
    )
    pad.connect()

    cap = ScreenCapture(target_fps=settings.vision.capture_fps)
    cap.start()

    captains = [c for c in (args.captain1, args.captain2) if c]
    seen_commands: set[str] = set()

    try:
        for i in range(args.delay, 0, -1):
            print(f"Warming up in {i}...")
            time.sleep(1)

        print(
            f"[in-match-chat-watch] poll={args.poll}s hold={hold}s settle={settle}s "
            f"region={chat_region.as_tuple()}"
        )
        print("             Ctrl-C to stop.\n")

        tick = 0
        while True:
            tick += 1

            # Open chat
            pad.press_hold("start", hold)
            time.sleep(settle)

            frame = cap.grab()
            if frame is None:
                pad.press("b")
                time.sleep(args.poll)
                continue

            if args.raw:
                x1, y1, x2, y2 = chat_region.as_tuple()
                raw = reader.read_text(frame[y1:y2, x1:x2], psm=6)
                print(f"[{tick:04d}] raw OCR:")
                for line in raw.splitlines():
                    if line.strip():
                        print(f"    | {line}")

            msgs = chat.read_chat(frame)
            for m in msgs:
                print(f"[{tick:04d}]  {m.player_name}: {m.message}")

            for cmd in ("pause", "unpause", "continue"):
                for c in captains:
                    match = chat.find_command(frame, command=cmd, allowed_players=[c])
                    if match is None:
                        continue
                    idx, total, msg, who = match
                    key = f"{who}:{cmd}:{msg.message}:{idx}/{total}"
                    if key in seen_commands:
                        continue
                    seen_commands.add(key)
                    print(
                        f"[{tick:04d}]  >>> {cmd.upper()} from {who} "
                        f"(index {idx}/{total}) <<<"
                    )

            # Close chat
            pad.press("b")
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\n[in-match-chat-watch] interrupted.")
    finally:
        pad.disconnect()
        cap.stop()


if __name__ == "__main__":
    main()
