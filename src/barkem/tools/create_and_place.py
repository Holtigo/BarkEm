"""
Phase 2 + Phase 3 end-to-end test tool.

Creates a private-match lobby, prints the lobby code, WAITS for you to
press Enter (so the other player has time to actually join), then runs
team placement.

Because ``LobbyCreator.create_and_read_code`` ends with the cursor on
the Arena (map) dropdown in the left column, the first RIGHT press in
``TeamPlacer.place_teams`` lands on the bot's row in the unassigned
column — no cursor priming needed here.

Usage:
    python -m barkem.tools.create_and_place \\
        --mode final_round --map monaco \\
        --team1 RockhardStick88

    # Any combination of --team1 / --team2 lists works; unlisted
    # unassigned players are left alone (good for partial-roster tests).
"""

import argparse
import time

from barkem.bot.lobby import LobbyCreator
from barkem.bot.placement import TeamPlacer
from barkem.config import get_settings
from barkem.input.controller import GamepadController, GamepadConfig
from barkem.input.navigator import (
    LobbyGrid,
    LobbyNavigator,
    MenuNavigator,
    MenuSequences,
)
from barkem.input.window import WindowManager
from barkem.vision.capture import ScreenCapture
from barkem.vision.lobby_reader import LobbyReader
from barkem.vision.ocr import TextReader
from barkem.vision.regions import load_regions_from_dict
from barkem.vision.state_detector import GameStateDetector
from barkem.vision.templates import TemplateMatcher


def _build(settings, debug: bool, slow: float):
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

    matcher = TemplateMatcher(threshold=settings.vision.template_threshold)
    detector = GameStateDetector(threshold=settings.vision.template_threshold)
    reader = TextReader(
        upscale_factor=settings.vision.ocr_upscale_factor,
        tesseract_cmd=settings.vision.tesseract_cmd,
    )
    regions = load_regions_from_dict(settings.regions)

    seq = settings.sequences
    menu_nav = MenuNavigator(
        controller=pad,
        capture=cap,
        matcher=matcher,
        sequences=MenuSequences(
            mode_down_to_private=seq.mode_down_to_private,
            private_to_create=seq.private_to_create,
        ),
        transition_wait=cfg.transition_wait * slow,
    )

    grid = settings.grid
    lobby_nav = LobbyNavigator(
        controller=pad,
        grid=LobbyGrid(
            team1_rows=grid.team1_rows,
            team2_rows=grid.team2_rows,
            gap_between_teams=grid.gap_between_teams,
            context_move_self=grid.context_move_self,
            context_move_other=grid.context_move_other,
            dropdown_anchor_up=grid.dropdown_anchor_up,
        ),
        step_wait=cfg.step_wait * slow,
    )

    window = WindowManager(window_title=settings.game.window_title)
    creator = LobbyCreator(
        menu_nav=menu_nav,
        lobby_nav=lobby_nav,
        capture=cap,
        text_reader=reader,
        regions=regions,
        state_detector=detector,
        mode_indices=settings.mode_map.modes,
        map_indices=settings.mode_map.maps,
        window_manager=window,
        focus_settle=0.5 * slow,
        verbose=debug,
    )

    lobby_reader = LobbyReader(
        ocr=reader,
        lobby=regions.lobby,
        context_menu=regions.context_menu,
    )
    placer = TeamPlacer(
        lobby_nav=lobby_nav,
        lobby_reader=lobby_reader,
        capture=cap,
        bot_embark_id=settings.game.bot_embark_id,
        step_wait=cfg.step_wait * slow,
        verbose=debug,
    )
    return creator, placer, pad, cap


def _countdown(seconds: int) -> None:
    for i in range(seconds, 0, -1):
        print(f"  Starting in {i}...")
        time.sleep(1)


def main() -> None:
    p = argparse.ArgumentParser(
        description="BarkEm — Create lobby → wait for players → place teams"
    )
    p.add_argument("--mode", default="final_round", help="Game mode key")
    p.add_argument("--map", dest="map_name", default="monaco", help="Map key")
    p.add_argument("--team1", nargs="*", default=[],
                   help="Team 1 Embark IDs (first = captain)")
    p.add_argument("--team2", nargs="*", default=[],
                   help="Team 2 Embark IDs (first = captain)")
    p.add_argument("--delay", type=int, default=3,
                   help="Pre-flight countdown (focus the game window)")
    p.add_argument("--post-enter-delay", type=float, default=2.0,
                   help="Seconds to wait after Enter before placement starts "
                        "(gives you time to alt-tab back to the game window).")
    p.add_argument("--no-verify", action="store_true",
                   help="Skip the post-placement team OCR verification.")
    p.add_argument("--no-spectate", action="store_true",
                   help="Skip the final 'move bot to spectator' step.")
    p.add_argument("--debug", action="store_true",
                   help="Verbose output: print every step and button press")
    p.add_argument("--slow", type=float, default=1.0,
                   help="Multiply all timing delays by this factor")
    p.add_argument("--skip-create", action="store_true",
                   help="Don't create a lobby — assume one already exists "
                        "and jump straight to the Enter-to-place prompt. "
                        "Useful for iterating on placement without recreating.")
    args = p.parse_args()

    if not args.team1 and not args.team2:
        p.error("provide at least one of --team1 / --team2")

    settings = get_settings()
    creator, placer, pad, cap = _build(settings, args.debug, args.slow)

    try:
        print("Pre-flight — focus the game window now.")
        _countdown(args.delay)

        if args.skip_create:
            print("\n[1/3] Skipping lobby creation (--skip-create)")
        else:
            print(f"\n[1/3] Creating lobby  mode={args.mode!r}  map={args.map_name!r}")
            result = creator.create_and_read_code(mode=args.mode, map_name=args.map_name)
            if not result.success:
                print(f"  FAILED — {result.error}")
                if result.lobby_code:
                    print(f"  (partial OCR: {result.lobby_code!r})")
                return
            print(f"  Lobby code: {result.lobby_code}")

        print("\n[2/3] Share the code with your test account and wait for them to join.")
        print("      The Manage Lobby (Y) flow is cursor-state-independent —")
        print("      feel free to alt-tab; you don't have to preserve focus.")
        try:
            input("      Press Enter when everyone is in the unassigned list... ")
        except (EOFError, KeyboardInterrupt):
            print("  Aborted by user.")
            return

        if args.post_enter_delay > 0:
            print(f"      Alt-tab back to the game — starting in "
                  f"{args.post_enter_delay:.1f}s...")
            time.sleep(args.post_enter_delay)

        print(f"\n[3/3] Placing teams  team1={args.team1}  team2={args.team2}")
        placement = placer.place_teams(
            team1_ids=args.team1,
            team2_ids=args.team2,
            verify_after=not args.no_verify,
            spectate_bot=not args.no_spectate,
        )
        print()
        print(f"  success     = {placement.success}")
        print(f"  placed      = {placement.placed}")
        print(f"  missing     = {placement.missing}")
        print(f"  mismatches  = {placement.verify_mismatches}")
        if placement.error:
            print(f"  error       = {placement.error}")
    finally:
        pad.disconnect()
        cap.stop()


if __name__ == "__main__":
    main()
