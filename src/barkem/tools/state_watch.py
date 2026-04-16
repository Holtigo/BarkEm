"""
Continuous game-state watcher.

Polls the screen on a fixed interval and prints the detected GameScreen
plus its template-match confidence.  Run this in one terminal while
you drive the game with another tool (e.g. keyboard_gamepad) to see
the bot's perception of the UI in real time.

Usage:
    python -m barkem.tools.state_watch                # 3s interval
    python -m barkem.tools.state_watch --interval 1   # 1s interval
    python -m barkem.tools.state_watch --once         # single sample, then exit
    python -m barkem.tools.state_watch --save-misses  # dump screenshot when UNKNOWN

Press Ctrl+C to stop.
"""

import argparse
import os
import time
from datetime import datetime

import cv2

from barkem.config import get_settings
from barkem.vision.capture import ScreenCapture
from barkem.vision.state_detector import GameScreen, GameStateDetector


def _fmt(screen: GameScreen, confidence: float, template: str | None) -> str:
    ts = datetime.now().strftime("%H:%M:%S")
    name = screen.name.ljust(22)
    conf = f"{confidence:.3f}" if confidence else " --- "
    tpl = template or "-"
    return f"[{ts}] {name}  conf={conf}  via={tpl}"


def main() -> None:
    parser = argparse.ArgumentParser(description="BarkEm — continuous state watcher")
    parser.add_argument("--interval", type=float, default=3.0,
                        help="Poll interval in seconds (default: 3)")
    parser.add_argument("--once", action="store_true",
                        help="Sample once and exit")
    parser.add_argument("--save-misses", action="store_true",
                        help="Save a screenshot when state is UNKNOWN")
    parser.add_argument("--save-dir", default="debug/screenshots",
                        help="Where to save miss screenshots")
    args = parser.parse_args()

    settings = get_settings()
    detector = GameStateDetector(threshold=settings.vision.template_threshold)

    available = detector.get_available_templates()
    missing = detector.get_missing_templates()
    print(f"Templates available: {sum(len(v) for v in available.values())}")
    if missing:
        print("Missing templates (these screens cannot be detected):")
        for screen, names in missing.items():
            print(f"  {screen.name}: {', '.join(names)}")
    print(f"Polling every {args.interval}s. Ctrl+C to stop.\n")

    if args.save_misses:
        os.makedirs(args.save_dir, exist_ok=True)

    cap = ScreenCapture(target_fps=settings.vision.capture_fps)
    cap.start()

    last_screen: GameScreen | None = None
    try:
        while True:
            frame = cap.grab()
            if frame is None:
                print(f"[{datetime.now():%H:%M:%S}] (no frame)")
            else:
                screen, match = detector.detect(frame)
                line = _fmt(
                    screen,
                    match.confidence if match else 0.0,
                    match.template_name if match else None,
                )
                changed = " *" if screen != last_screen else ""
                print(line + changed)
                last_screen = screen

                if args.save_misses and screen == GameScreen.UNKNOWN:
                    path = os.path.join(
                        args.save_dir,
                        f"unknown_{int(time.time())}.png",
                    )
                    cv2.imwrite(path, frame)

            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        cap.stop()


if __name__ == "__main__":
    main()
