"""
Live highlight watcher — prints which lobby slot the cursor is on.

Usage:
    # Print the top candidate once per second (default)
    python -m barkem.tools.highlight_watch

    # Show scores for every slot, not just the winner
    python -m barkem.tools.highlight_watch --all

    # Tune the HSV range on the fly if blue glow isn't matching
    python -m barkem.tools.highlight_watch --hsv-lower 90 120 180 \\
                                           --hsv-upper 130 255 255

    # Save a masked screenshot (blue-glow pixels white, everything else
    # black) so you can eyeball whether the HSV range is right
    python -m barkem.tools.highlight_watch --dump-mask debug/mask.png

Pre-flight:
    - You're in a private-match lobby on-screen.
    - Lobby slot OCR regions are calibrated in settings.yaml.
    - Move the D-pad around while this runs; the top candidate should
      track your selection.
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from barkem.config import get_settings
from barkem.vision.capture import ScreenCapture
from barkem.vision.highlight import HighlightDetector
from barkem.vision.regions import load_regions_from_dict


def _parse_hsv(v: list[int]) -> tuple[int, int, int]:
    if len(v) != 3:
        raise SystemExit("HSV args must be 3 numbers: H S V")
    return (v[0], v[1], v[2])


def _dump_mask(frame: np.ndarray, det: HighlightDetector, path: Path) -> None:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, det.lower, det.upper)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), mask)
    print(f"  mask saved → {path}")


def main() -> None:
    p = argparse.ArgumentParser(description="Live lobby highlight watcher")
    p.add_argument("--interval", type=float, default=1.0,
                   help="Seconds between prints (default 1.0)")
    p.add_argument("--all", action="store_true",
                   help="Print score for every candidate, not just the winner")
    p.add_argument("--top", type=int, default=3,
                   help="With --all, how many top candidates to print (default 3)")
    p.add_argument("--min-pixels", type=int, default=50,
                   help="Minimum matching-pixel count to call a slot selected")
    p.add_argument("--border-margin", type=int, default=8,
                   help="Pixel padding around each slot region when scoring")
    p.add_argument("--hsv-lower", type=int, nargs=3, default=[90, 120, 180],
                   help="HSV lower bound (H S V)")
    p.add_argument("--hsv-upper", type=int, nargs=3, default=[130, 255, 255],
                   help="HSV upper bound (H S V)")
    p.add_argument("--dump-mask", type=Path,
                   help="Save one blue-glow mask screenshot and exit")
    args = p.parse_args()

    settings = get_settings()
    regions = load_regions_from_dict(settings.regions)
    candidates = regions.lobby.all_player_slots()
    if not candidates:
        print("No lobby slot regions defined in settings.yaml — nothing to watch.")
        return

    det = HighlightDetector(
        hsv_lower=_parse_hsv(args.hsv_lower),
        hsv_upper=_parse_hsv(args.hsv_upper),
        min_pixels=args.min_pixels,
        border_margin=args.border_margin,
    )

    cap = ScreenCapture(target_fps=settings.vision.capture_fps)
    cap.start()
    try:
        if args.dump_mask:
            for _ in range(10):
                frame = cap.grab()
                if frame is not None:
                    break
                time.sleep(0.05)
            if frame is None:
                print("  failed to grab frame")
                return
            _dump_mask(frame, det, args.dump_mask)
            return

        print(f"Watching {len(candidates)} slots.  Move the D-pad around in-game.")
        print(f"HSV range: {args.hsv_lower} → {args.hsv_upper}   "
              f"min_pixels={args.min_pixels}   margin={args.border_margin}")
        print("Press Ctrl+C to stop.\n")

        while True:
            frame = cap.grab()
            if frame is None:
                time.sleep(args.interval)
                continue

            if args.all:
                scores = det.score_all(frame, candidates)[:args.top]
                line = "  ".join(f"{s.name}={s.score}" for s in scores)
                print(line)
            else:
                best = det.detect(frame, candidates)
                if best is None:
                    print("  (no slot selected — nothing above min_pixels)")
                else:
                    print(f"  selected: {best.name}  score={best.score}")

            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        cap.stop()


if __name__ == "__main__":
    main()
