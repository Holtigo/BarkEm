"""
Phase 6 test tool — OCR the current scoreboard and print results.

Standalone wrapper around ScoreboardReader.  Useful for calibrating
the scoreboard rows + columns:

    python -m barkem.tools.scoreboard_read

    # Dump the raw OCR for every cell (class/name/stat per player):
    python -m barkem.tools.scoreboard_read --raw

    # Draw every configured cell on a screenshot for visual check:
    python -m barkem.tools.scoreboard_read --draw

This tool does NOT press any buttons — it just grabs a frame and
OCRs the regions defined in settings.yaml under ``regions.scoreboard``.
"""

import argparse
import time

from barkem.bot.scoreboard_reader import ScoreboardReader
from barkem.config import get_settings
from barkem.vision.capture import ScreenCapture
from barkem.vision.debug import draw_scoreboard_regions, save_debug_screenshot
from barkem.vision.ocr import TextReader
from barkem.vision.regions import (
    SCOREBOARD_STAT_COLUMNS,
    load_regions_from_dict,
)


COLUMN_ORDER: tuple[str, ...] = ("class", "name", *SCOREBOARD_STAT_COLUMNS)


def _dump_raw(frame, reader: TextReader, sb_regions) -> None:
    """
    Dump raw OCR per scoreboard cell.

    Uses the same V-channel preprocessing path the real reader uses
    (scoreboard cells are white text on coloured team tiles), so the
    dump reflects what ScoreboardReader actually sees.
    """
    print("──── Raw OCR per cell (V-channel preprocessing) ────")

    def _raw(region, psm=7):
        return reader.read_region(
            frame, region.as_tuple(), psm=psm, use_v_channel=True,
        )

    if not sb_regions.team1_score.is_zero:
        print(f"  team1_score                  {_raw(sb_regions.team1_score)!r}")
    if not sb_regions.team2_score.is_zero:
        print(f"  team2_score                  {_raw(sb_regions.team2_score)!r}")

    for team_id in (1, 2):
        for row_idx in range(3):
            slot = f"team{team_id}_player{row_idx + 1}"
            if sb_regions.row(team_id, row_idx).is_zero:
                print(f"  {slot}  <row not configured>")
                continue
            for col in COLUMN_ORDER:
                cell = sb_regions.cell(team_id, row_idx, col)
                if cell.is_zero:
                    print(f"  {slot:20}  {col:10}  <col not configured>")
                    continue
                psm = 10 if col == "class" else 7
                print(f"  {slot:20}  {col:10}  {_raw(cell, psm=psm)!r}")
    print()


def _print_parsed(result) -> None:
    print("──── Parsed Scoreboard ────")
    if result.error:
        print(f"  NOTE: {result.error}")
    for team in (result.team1, result.team2):
        flag = " ← winner" if result.winner_team_id == team.team_id else ""
        print(f"  Team {team.team_id}  total={team.total_score}{flag}")
        for p in team.players:
            print(
                f"    {p.slot:18}  [{p.class_ or '?'}]  name={p.ocr_name!r:28}  "
                f"E/A/D={p.elims}/{p.assists}/{p.deaths}  rev={p.revives}  "
                f"dmg={p.damage} sup={p.support} obj={p.objective}"
            )


def main() -> None:
    p = argparse.ArgumentParser(description="BarkEm — read the scoreboard")
    p.add_argument("--delay", type=int, default=3,
                   help="Pre-flight delay (seconds).  Default 3.")
    p.add_argument("--raw", action="store_true",
                   help="Print raw OCR for every configured cell.")
    p.add_argument("--draw", action="store_true",
                   help="Draw every configured cell on a screenshot "
                        "(saved to debug/screenshots/).  Good for "
                        "visually verifying row/column alignment.")
    args = p.parse_args()

    settings = get_settings()
    regions = load_regions_from_dict(settings.regions)
    reader = TextReader(
        upscale_factor=settings.vision.ocr_upscale_factor,
        tesseract_cmd=settings.vision.tesseract_cmd,
    )
    sb_reader = ScoreboardReader(ocr=reader, regions=regions.scoreboard)

    cap = ScreenCapture(target_fps=settings.vision.capture_fps)
    cap.start()

    try:
        for i in range(args.delay, 0, -1):
            print(f"Warming up in {i}...")
            time.sleep(1)

        frame = cap.grab()
        if frame is None:
            print("No frame available.")
            return

        if args.draw:
            annotated = draw_scoreboard_regions(
                frame.copy(), regions.scoreboard, skip_zero=True,
            )
            path = save_debug_screenshot(annotated, "scoreboard_regions")
            print(f"Scoreboard region overlay saved: {path}")

        if args.raw:
            _dump_raw(frame, reader, regions.scoreboard)

        _print_parsed(sb_reader.read(frame))
    finally:
        cap.stop()


if __name__ == "__main__":
    main()
