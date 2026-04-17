"""
Phase 3 test tool — Read the lobby, then place 6 players into teams.

Usage:

    # Just OCR-snapshot the current lobby (no input sent)
    python -m barkem.tools.place_teams --snapshot

    # Dry-run placement — prints the plan, doesn't press any buttons
    python -m barkem.tools.place_teams --dry-run \\
        --team1 A#0001 B#0002 C#0003 \\
        --team2 D#0004 E#0005 F#0006

    # Full run — expects you already in a lobby with those 6 players
    # unassigned (bot should already be a spectator by this point).
    python -m barkem.tools.place_teams \\
        --team1 A#0001 B#0002 C#0003 \\
        --team2 D#0004 E#0005 F#0006

Pre-flight:
    - You are already in a private-match lobby.
    - The bot is still unassigned (row 0 of the player list).
    - All expected players have joined and sit in the unassigned list.
    - Lobby OCR regions are calibrated in settings.yaml.
    - Cursor state doesn't matter — the Manage Lobby (Y) flow re-anchors
      every iteration.
"""

import argparse
import time

from barkem.bot.placement import TeamPlacer
from barkem.config import get_settings
from barkem.input.controller import GamepadController, GamepadConfig
from barkem.input.navigator import LobbyGrid, LobbyNavigator
from barkem.vision.capture import ScreenCapture
from barkem.vision.lobby_reader import LobbyReader
from barkem.vision.ocr import TextReader
from barkem.vision.regions import load_regions_from_dict


def _build(
    settings, debug: bool = False, slow: float = 1.0,
) -> tuple[TeamPlacer, GamepadController, ScreenCapture]:
    cfg = settings.input

    pad = GamepadController(
        config=GamepadConfig(
            button_delay=cfg.button_delay * slow,
            hold_duration=cfg.hold_duration * slow,
            anchor_presses=cfg.anchor_presses,
            anchor_settle=cfg.anchor_settle * slow,
            verbose=debug,
        )
    )
    pad.connect()

    cap = ScreenCapture(target_fps=settings.vision.capture_fps)
    cap.start()

    reader = TextReader(
        upscale_factor=settings.vision.ocr_upscale_factor,
        tesseract_cmd=settings.vision.tesseract_cmd,
    )
    regions = load_regions_from_dict(settings.regions)

    grid = settings.grid
    nav = LobbyNavigator(
        controller=pad,
        grid=LobbyGrid(
            team1_rows=grid.team1_rows,
            team2_rows=grid.team2_rows,
            gap_between_teams=grid.gap_between_teams,
            context_move_self=grid.context_move_self,
            context_move_other=grid.context_move_other,
            dropdown_anchor_up=grid.dropdown_anchor_up,
        ),
        step_wait=cfg.step_wait,
    )

    lobby_reader = LobbyReader(
        ocr=reader,
        lobby=regions.lobby,
        context_menu=regions.context_menu,
    )

    placer = TeamPlacer(
        lobby_nav=nav,
        lobby_reader=lobby_reader,
        capture=cap,
        bot_embark_id=settings.game.bot_embark_id,
        step_wait=cfg.step_wait * slow,
        verbose=debug,
    )
    return placer, pad, cap


def _countdown(seconds: int) -> None:
    for i in range(seconds, 0, -1):
        print(f"  Starting in {i}...")
        time.sleep(1)


def _print_snapshot(snap) -> None:
    print("  Unassigned:")
    for i, name in enumerate(snap.unassigned):
        print(f"    [{i}] {name!r}")
    print(f"  (total rows incl. empty: {snap.unassigned_total_rows})")
    print(f"  Spectators: {snap.spectators}")
    print(f"  Team 1:  {snap.team1}")
    print(f"  Team 2:  {snap.team2}")


def main() -> None:
    p = argparse.ArgumentParser(description="BarkEm Phase 3 — Team placement")
    p.add_argument("--team1", nargs="*", default=[],
                   help="Team 1 Embark IDs (first = captain)")
    p.add_argument("--team2", nargs="*", default=[],
                   help="Team 2 Embark IDs (first = captain)")
    p.add_argument("--snapshot", action="store_true",
                   help="Just OCR the lobby and print what was seen — no input.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print the resolved placement plan, no presses.")
    p.add_argument("--no-verify", action="store_true",
                   help="Skip the post-placement team OCR verification.")
    p.add_argument("--no-spectate", action="store_true",
                   help="Skip the final 'move bot to spectator' step.")
    p.add_argument("--delay", type=int, default=3,
                   help="Pre-flight countdown (focus the game window)")
    p.add_argument("--debug", action="store_true",
                   help="Verbose output: print every step and button press")
    p.add_argument("--slow", type=float, default=1.0,
                   help="Multiply all timing delays by this factor")
    args = p.parse_args()

    settings = get_settings()
    placer, pad, cap = _build(settings, debug=args.debug, slow=args.slow)

    try:
        if args.snapshot:
            print("Reading lobby snapshot...")
            snap = placer.snapshot()
            if snap is None:
                print("  FAILED — could not grab frame")
                return
            _print_snapshot(snap)
            return

        if not args.team1 and not args.team2:
            p.error("provide at least one of --team1 / --team2 (or use --snapshot)")

        print("Pre-flight — make sure the lobby is on-screen, bot is spectating.")
        _countdown(args.delay)

        if args.dry_run:
            snap = placer.snapshot()
            if snap is None:
                print("  FAILED — could not grab frame")
                return
            _print_snapshot(snap)
            print()
            print("Plan (expected → unassigned row):")
            for team_ids, team_num in [(args.team1, 1), (args.team2, 2)]:
                for slot, pid in enumerate(team_ids):
                    row = snap.index_of(pid)
                    print(f"  team{team_num}[{slot}] {pid!r} → row {row}")
            return

        print(f"Placing team1={args.team1}  team2={args.team2}")
        result = placer.place_teams(
            team1_ids=args.team1,
            team2_ids=args.team2,
            verify_after=not args.no_verify,
            spectate_bot=not args.no_spectate,
        )
        print()
        print(f"  success     = {result.success}")
        print(f"  placed      = {result.placed}")
        print(f"  missing     = {result.missing}")
        print(f"  mismatches  = {result.verify_mismatches}")
        if result.error:
            print(f"  error       = {result.error}")
    finally:
        pad.disconnect()
        cap.stop()


if __name__ == "__main__":
    main()
