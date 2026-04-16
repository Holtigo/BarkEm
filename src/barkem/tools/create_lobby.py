"""
Phase 2 test tool — Create a private match lobby end-to-end.

Usage:
    # Full flow (Main Menu → Create Game → OCR lobby code)
    python -m barkem.tools.create_lobby

    # With explicit mode/map selection after lobby is up
    python -m barkem.tools.create_lobby --mode final_round --map monaco

    # Just OCR the lobby code (assumes you're already in the lobby)
    python -m barkem.tools.create_lobby --read-code-only

    # Just verify the menu navigation step (no dropdowns, no OCR)
    python -m barkem.tools.create_lobby --nav-only

    # Tweak the 3-second pre-flight delay (gives you time to focus the game window)
    python -m barkem.tools.create_lobby --delay 5

Pre-flight checklist:
    - The Finals running, focused, in Borderless Windowed mode.
    - templates/change_game_mode_selected.png exists.
    - config/settings.yaml has lobby_code OCR region calibrated.
    - For Linux: virtual gamepad permissions (uinput) configured.
"""

import argparse
import time

from barkem.bot.lobby import LobbyCreator
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
from barkem.vision.ocr import TextReader
from barkem.vision.regions import load_regions_from_dict
from barkem.vision.state_detector import GameStateDetector
from barkem.vision.templates import TemplateMatcher


def _build_creator(settings) -> tuple[LobbyCreator, GamepadController, ScreenCapture]:
    cfg = settings.input

    pad = GamepadController(
        config=GamepadConfig(
            button_delay=cfg.button_delay,
            hold_duration=cfg.hold_duration,
            anchor_presses=cfg.anchor_presses,
            anchor_settle=cfg.anchor_settle,
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
            mode_anchor_up=seq.mode_anchor_up,
            mode_down_to_private=seq.mode_down_to_private,
            private_to_create=seq.private_to_create,
        ),
        transition_wait=cfg.transition_wait,
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
        step_wait=cfg.step_wait,
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
    )
    return creator, pad, cap


def _countdown(seconds: int) -> None:
    for i in range(seconds, 0, -1):
        print(f"  Starting in {i}...")
        time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="BarkEm Phase 2 — Create lobby end-to-end")
    parser.add_argument("--mode", help="Game mode key (e.g. final_round)")
    parser.add_argument("--map", dest="map_name", help="Map key (e.g. monaco)")
    parser.add_argument("--read-code-only", action="store_true",
                        help="Skip nav, just OCR the lobby code")
    parser.add_argument("--nav-only", action="store_true",
                        help="Run menu nav only, skip OCR + dropdowns")
    parser.add_argument("--delay", type=int, default=3,
                        help="Pre-flight countdown (focus the game window)")
    parser.add_argument("--focus-only", action="store_true",
                        help="Just find + focus the game window, then exit")
    args = parser.parse_args()

    settings = get_settings()
    creator, pad, cap = _build_creator(settings)

    try:
        if args.focus_only:
            wm = WindowManager(window_title=settings.game.window_title)
            title = wm.find_window_title()
            if not title:
                print(f"  No window matching {settings.game.window_title!r}")
                return
            print(f"  Matched window: {title!r}")
            ok = wm.focus()
            print(f"  Focused: {ok}")
            return

        if args.read_code_only:
            print("Reading lobby code from current screen...")
            code = creator.read_lobby_code()
            print(f"  Lobby code: {code!r}")
            return

        print("Pre-flight — focus the game window now.")
        _countdown(args.delay)

        if args.nav_only:
            print("Navigating to Create Game (no OCR, no dropdowns)...")
            ok = creator.menu.go_to_create_game()
            print(f"  go_to_create_game: {'OK' if ok else 'FAILED'}")
            return

        print(f"Creating lobby (mode={args.mode}, map={args.map_name})...")
        result = creator.create_and_read_code(mode=args.mode, map_name=args.map_name)
        if result.success:
            print(f"  SUCCESS — lobby code: {result.lobby_code}")
        else:
            print(f"  FAILED — {result.error}")
            if result.lobby_code:
                print(f"  (partial OCR result: {result.lobby_code!r})")
    finally:
        pad.disconnect()
        cap.stop()


if __name__ == "__main__":
    main()
