"""
Phase 5 test tool — OCR the current scoreboard and print results.

Standalone wrapper around ScoreboardReader.  Useful for calibrating
the scoreboard regions:

    python -m barkem.tools.scoreboard_read

    # Dump the raw OCR for every configured region (louder):
    python -m barkem.tools.scoreboard_read --raw

This tool does NOT press any buttons — it just grabs a frame and
OCRs the regions defined in settings.yaml under ``regions.scoreboard``.
"""

import argparse
import time

from barkem.bot.scoreboard_reader import ScoreboardReader
from barkem.config import get_settings
from barkem.vision.capture import ScreenCapture
from barkem.vision.ocr import TextReader
from barkem.vision.regions import load_regions_from_dict


def main() -> None:
    p = argparse.ArgumentParser(description="BarkEm — read the scoreboard")
    p.add_argument("--delay", type=int, default=3,
                   help="Pre-flight delay (seconds).  Default 3.")
    p.add_argument("--raw", action="store_true",
                   help="Print raw OCR for every configured region.")
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

        if args.raw:
            # Iterate every scoreboard region and dump raw OCR
            sb = regions.scoreboard
            print("──── Raw OCR per region ────")
            fields = [
                "team1_name", "team1_score",
                "team2_name", "team2_score",
                "team1_player1_score_name", "team1_player1_score_value",
                "team1_player2_score_name", "team1_player2_score_value",
                "team1_player3_score_name", "team1_player3_score_value",
                "team2_player1_score_name", "team2_player1_score_value",
                "team2_player2_score_name", "team2_player2_score_value",
                "team2_player3_score_name", "team2_player3_score_value",
            ]
            for name in fields:
                r = getattr(sb, name)
                if r.is_zero:
                    print(f"  {name:36}  <not configured>")
                    continue
                raw = reader.read_region(frame, r.as_tuple(), psm=7)
                print(f"  {name:36}  {raw!r}")
            print()

        result = sb_reader.read(frame)
        print("──── Parsed Scoreboard ────")
        if result.error:
            print(f"  NOTE: {result.error}")
        for team in (result.team1, result.team2):
            flag = " ← winner" if result.winner_team_id == team.team_id else ""
            print(
                f"  Team {team.team_id}  name={team.team_name!r}  "
                f"total={team.total_score}{flag}"
            )
            for pl in team.players:
                print(
                    f"    {pl.slot:20}  name={pl.ocr_name!r:30}  score={pl.score}"
                )
    finally:
        cap.stop()


if __name__ == "__main__":
    main()
