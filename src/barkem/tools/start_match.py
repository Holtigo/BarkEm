"""
Phase 4 test tool — wait for captain ready, then start the match.

Two modes:

  (A)  Standalone — you already have a lobby set up with players in
       their teams.  Run this and it starts monitoring chat.

           python -m barkem.tools.start_match \\
               --captain1 Alice#1234 --captain2 Bob#5678

  (B)  End-to-end (--full) — creates a fresh lobby, waits for a manual
       Enter so humans can join, places teams, then monitors chat.

           python -m barkem.tools.start_match --full \\
               --mode final_round --map monaco \\
               --team1 Alice#1234 --team2 Bob#5678

Solo-captain testing:
    When you only have one real account to test with, pass
    ``--min-ready 1`` and only ``--captain1``.  The bot will press X
    as soon as that single captain types "-em ready".

Skip ready entirely:
    ``--skip-ready`` just presses X immediately.  Useful for testing
    the X press against the lobby without running the chat loop at
    all.
"""

import argparse
import time
from typing import Optional

from barkem.bot.lobby import LobbyCreator
from barkem.bot.match_starter import MatchStarter
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
from barkem.vision.chat import ChatReader
from barkem.vision.lobby_reader import LobbyReader
from barkem.vision.ocr import TextReader
from barkem.vision.regions import load_regions_from_dict
from barkem.vision.state_detector import GameStateDetector
from barkem.vision.templates import TemplateMatcher


def _build(settings, debug: bool, slow: float):
    """Construct the full stack. Returns (creator, placer, starter_factory, pad, cap)."""
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

    chat_region = regions.chat.chat_area
    chat_reader = ChatReader(
        chat_region=chat_region.as_tuple(),
        text_reader=reader,
    )

    return creator, placer, chat_reader, pad, cap, regions


def _countdown(seconds: int, prefix: str = "Starting") -> None:
    for i in range(seconds, 0, -1):
        print(f"  {prefix} in {i}...")
        time.sleep(1)


def _make_starter(
    pad: GamepadController,
    cap: ScreenCapture,
    chat: ChatReader,
    captain1: str,
    captain2: Optional[str],
    min_ready: int,
    poll: float,
    debug: bool,
) -> MatchStarter:
    return MatchStarter(
        gamepad=pad,
        capture=cap,
        chat_reader=chat,
        captain1=captain1,
        captain2=captain2,
        min_ready_captains=min_ready,
        poll_interval=poll,
        verbose=debug,
    )


def main() -> None:
    p = argparse.ArgumentParser(
        description="BarkEm Phase 4 — Wait for captain ready, then start match (press X)."
    )
    # Mode selection
    p.add_argument("--full", action="store_true",
                   help="End-to-end: create lobby → wait for players → "
                        "place teams → wait for ready → start.")
    p.add_argument("--skip-ready", action="store_true",
                   help="Press X immediately without waiting for chat.")

    # Lobby creation (only used with --full)
    p.add_argument("--mode", default="final_round", help="Game mode key")
    p.add_argument("--map", dest="map_name", default="monaco", help="Map key")
    p.add_argument("--skip-create", action="store_true",
                   help="With --full: don't create a new lobby, reuse the "
                        "current one. Useful for iterating on Phase 4 "
                        "without recreating lobbies.")

    # Teams (captains are derived from the first entry of each list)
    p.add_argument("--team1", nargs="*", default=[],
                   help="Team 1 Embark IDs (first = captain1)")
    p.add_argument("--team2", nargs="*", default=[],
                   help="Team 2 Embark IDs (first = captain2)")
    p.add_argument("--captain1", default=None,
                   help="Override for team 1 captain (default: first of --team1)")
    p.add_argument("--captain2", default=None,
                   help="Override for team 2 captain (default: first of --team2)")

    # Ready-monitoring tuning (defaults come from settings.monitoring)
    p.add_argument("--min-ready", type=int, default=None, choices=[1, 2],
                   help="How many captains must say '-em ready' before X. "
                        "Default from settings.monitoring.min_ready_captains. "
                        "Use 1 for solo testing, 2 for production.")
    p.add_argument("--poll", type=float, default=None,
                   help="Chat poll interval in seconds. Default from "
                        "settings.monitoring.chat_poll_interval. Chat fades "
                        "after ~8s so 1-2s is safe.")
    p.add_argument("--timeout", type=float, default=None,
                   help="Abort if no ready within this many seconds. "
                        "Default from settings.monitoring.ready_timeout_seconds.")

    # Misc
    p.add_argument("--delay", type=int, default=3,
                   help="Pre-flight countdown (focus the game window)")
    p.add_argument("--post-enter-delay", type=float, default=2.0,
                   help="With --full: seconds between 'Enter pressed' and "
                        "placement starting (re-focus the game).")
    p.add_argument("--debug", action="store_true",
                   help="Verbose output.")
    p.add_argument("--slow", type=float, default=1.0,
                   help="Multiply all timing delays by this factor.")
    args = p.parse_args()

    # Resolve captains
    captain1 = args.captain1 or (args.team1[0] if args.team1 else None)
    captain2 = args.captain2 or (args.team2[0] if args.team2 else None)
    if not captain1 and not args.skip_ready:
        p.error(
            "need --captain1 or --team1 to know which captain is saying ready. "
            "(Use --skip-ready to bypass the chat watcher entirely.)"
        )

    settings = get_settings()
    creator, placer, chat, pad, cap, regions = _build(settings, args.debug, args.slow)

    # Apply settings defaults for any unset ready flags
    if args.min_ready is None:
        args.min_ready = settings.monitoring.min_ready_captains
    if args.poll is None:
        args.poll = settings.monitoring.chat_poll_interval
    if args.timeout is None:
        args.timeout = float(settings.monitoring.ready_timeout_seconds)

    if regions.chat.chat_area.is_zero and not args.skip_ready:
        print(
            "WARNING: regions.chat.chat_area is [0,0,0,0] — chat OCR will "
            "return nothing.  Run `python -m barkem.tools.calibrate` to map it."
        )

    try:
        print("Pre-flight — focus the game window now.")
        _countdown(args.delay)

        # ── --full pipeline: create + wait for join + place ────────────
        if args.full:
            if args.skip_create:
                print("\n[1/3] Skipping lobby creation (--skip-create)")
            else:
                print(
                    f"\n[1/3] Creating lobby  mode={args.mode!r}  "
                    f"map={args.map_name!r}"
                )
                res = creator.create_and_read_code(
                    mode=args.mode, map_name=args.map_name,
                )
                if not res.success:
                    print(f"  FAILED — {res.error}")
                    return
                print(f"  Lobby code: {res.lobby_code}")

            print("\n[2/3] Share the code and wait for players to join.")
            try:
                input("      Press Enter when they're in the unassigned list... ")
            except (EOFError, KeyboardInterrupt):
                print("  Aborted.")
                return
            if args.post_enter_delay > 0:
                print(
                    f"      Alt-tab back to the game — "
                    f"starting in {args.post_enter_delay:.1f}s..."
                )
                time.sleep(args.post_enter_delay)

            if args.team1 or args.team2:
                print(
                    f"\n[3/3] Placing teams  "
                    f"team1={args.team1}  team2={args.team2}"
                )
                placement = placer.place_teams(
                    team1_ids=args.team1,
                    team2_ids=args.team2,
                    verify_after=True,
                    spectate_bot=True,
                )
                print(f"    placed     = {placement.placed}")
                print(f"    missing    = {placement.missing}")
                print(f"    mismatches = {placement.verify_mismatches}")
                if not placement.success:
                    print(f"    error      = {placement.error}")
                    return
            else:
                print("\n[3/3] No teams given — skipping placement.")

        # ── Ready-then-start ───────────────────────────────────────────
        starter = _make_starter(
            pad=pad, cap=cap, chat=chat,
            captain1=captain1 or "",
            captain2=captain2,
            min_ready=args.min_ready,
            poll=args.poll,
            debug=args.debug or True,  # starter output is the main signal
        )

        if args.skip_ready:
            print("\n[start] --skip-ready — pressing X immediately.")
            result = starter.force_start()
        else:
            print(
                f"\n[start] Waiting for {args.min_ready} captain(s) "
                f"to type '-em ready' (timeout {args.timeout:.0f}s)..."
            )
            print(f"        captain1 = {captain1!r}")
            print(f"        captain2 = {captain2!r}")
            print(
                "        The match will be seen as 'starting' automatically "
                "via the loading screen (5-15s of server wait is normal)."
            )
            result = starter.wait_and_start(timeout_s=args.timeout)

        print()
        print(f"  success   = {result.success}")
        print(f"  started   = {result.started}")
        print(f"  timed_out = {result.timed_out}")
        print(f"  ready     = team1={result.ready_status.team1} "
              f"team2={result.ready_status.team2}")
        if result.error:
            print(f"  error     = {result.error}")
    finally:
        pad.disconnect()
        cap.stop()


if __name__ == "__main__":
    main()
