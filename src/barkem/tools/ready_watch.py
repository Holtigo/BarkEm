"""
Phase 4 test tool — Live chat OCR + ready-command watcher.

Doesn't press any buttons.  Just polls the chat region, prints what
OCR sees each tick, and highlights any ``-em ready`` / ``-em pause`` /
``-em unpause`` commands from the named captains.

Use it to:
  • Verify your chat-region bounding box (``regions.chat.chat_area``)
    produces legible OCR.
  • Confirm that typing "-em ready" from a real account is detected.
  • Tune ``poll_interval`` — The Finals' chat fades, so if the bot
    polls too slowly it'll miss messages entirely.

Usage:
    # Pre-flight (warm up for 3s, game already focused, chat visible):
    python -m barkem.tools.ready_watch --captain1 Alice#1234

    # Watch for both captains, 0.75s polling:
    python -m barkem.tools.ready_watch \\
        --captain1 Alice#1234 --captain2 Bob#5678 \\
        --poll 0.75

    # Dump the raw OCR text on every tick (loud, for debugging):
    python -m barkem.tools.ready_watch --captain1 Alice#1234 --raw

    # No captain filter — print every parsed chat message (useful when
    # just testing that the chat region is right):
    python -m barkem.tools.ready_watch
"""

import argparse
import time

from barkem.config import get_settings
from barkem.vision.capture import ScreenCapture
from barkem.vision.chat import ChatReader
from barkem.vision.ocr import TextReader
from barkem.vision.regions import load_regions_from_dict


def main() -> None:
    p = argparse.ArgumentParser(description="BarkEm — Live chat + ready watcher")
    p.add_argument("--captain1", default=None,
                   help="Team 1 captain Embark ID (optional; if omitted, "
                        "all parsed messages are printed).")
    p.add_argument("--captain2", default=None, help="Team 2 captain Embark ID")
    p.add_argument("--poll", type=float, default=1.0,
                   help="Chat poll interval (seconds). Default 1.0.")
    p.add_argument("--raw", action="store_true",
                   help="Print the full OCR'd chat text every tick.")
    p.add_argument("--duration", type=float, default=0.0,
                   help="Stop after this many seconds. 0 = run forever.")
    p.add_argument("--delay", type=int, default=3,
                   help="Pre-flight countdown before monitoring starts.")
    args = p.parse_args()

    settings = get_settings()
    regions = load_regions_from_dict(settings.regions)
    chat_region = regions.chat.chat_area
    if chat_region.is_zero:
        p.error(
            "regions.chat.chat_area is not configured in settings.yaml — "
            "run `python -m barkem.tools.calibrate` to map it."
        )

    text_reader = TextReader(
        upscale_factor=settings.vision.ocr_upscale_factor,
        tesseract_cmd=settings.vision.tesseract_cmd,
    )
    chat = ChatReader(chat_region=chat_region.as_tuple(), text_reader=text_reader)

    cap = ScreenCapture(target_fps=settings.vision.capture_fps)
    cap.start()

    captains = [c for c in (args.captain1, args.captain2) if c]
    ready_seen: set[str] = set()

    try:
        for i in range(args.delay, 0, -1):
            print(f"Warming up in {i}...")
            time.sleep(1)
        print(
            f"\n[ready-watch] polling every {args.poll:.2f}s  "
            f"chat_region={chat_region.as_tuple()}"
        )
        if captains:
            print(f"[ready-watch] captains = {captains}")
        else:
            print("[ready-watch] no captains specified — printing ALL messages")
        print("             Ctrl-C to stop.\n")

        deadline = time.monotonic() + args.duration if args.duration > 0 else None
        tick = 0
        while True:
            if deadline and time.monotonic() > deadline:
                print(f"[ready-watch] reached duration {args.duration:.0f}s — exiting")
                break
            tick += 1
            frame = cap.grab()
            if frame is None:
                time.sleep(args.poll)
                continue

            msgs = chat.read_chat(frame)

            if args.raw:
                # One OCR pass dumped literal (useful to see noise)
                x1, y1, x2, y2 = chat_region.as_tuple()
                raw = text_reader.read_text(frame[y1:y2, x1:x2], psm=6)
                print(f"[{tick:04d}] raw OCR:")
                for line in raw.splitlines():
                    if line.strip():
                        print(f"    | {line}")

            for m in msgs:
                print(f"[{tick:04d}]  {m.player_name}: {m.message}")

            # Captain ready / pause / unpause detection
            for cmd in ("ready", "pause", "unpause"):
                for captain in captains:
                    matched = chat.check_for_command(
                        frame, command=cmd, allowed_players=[captain],
                        only_new=False,
                    )
                    key = f"{captain}:{cmd}"
                    if matched and key not in ready_seen:
                        ready_seen.add(key)
                        print(
                            f"[{tick:04d}]  >>> {cmd.upper()} detected from {matched} <<<"
                        )

            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\n[ready-watch] interrupted.")
    finally:
        cap.stop()


if __name__ == "__main__":
    main()
