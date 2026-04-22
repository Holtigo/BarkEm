"""
Phase 5 test tool — run the in-match monitor loop against a live game.

Assumes the match has already started (X was already pressed and the
game is past the loading screen).  The tool sets up the full stack
(gamepad, keyboard, capture, chat reader pointed at the *in-match*
chat region, pause handler, scoreboard reader, state detector) and
hands off to MatchMonitor.run().

Usage — pause/resume cycle with a single captain:

    python -m barkem.tools.match_watch \\
        --captain1 Alice#1234 \\
        --max-pause 120 --max-pauses-per-team 1 \\
        --pause-poll 3

Usage — just OCR the scoreboard from whatever's on screen now:

    python -m barkem.tools.match_watch --read-scoreboard

Usage — skip an in-flight SUMMARY screen + OCR:

    python -m barkem.tools.match_watch --skip-summary

Notes:
  • The bot holds Menu to open in-match chat, so the spectator should
    NOT also press buttons during the pause polling — it'll fight the
    controller.
  • Templates ``match_summary.png`` and ``match_loading_screen.png``
    must exist in templates/ for state detection to work.  If absent,
    you'll see a warning and the monitor won't detect the end of match.
"""

import argparse
import time
from typing import Optional

from barkem.bot.match_monitor import MatchMonitor, MatchMonitorConfig
from barkem.bot.pause_handler import PauseHandler, PauseLimits
from barkem.bot.scoreboard_reader import ScoreboardReader
from barkem.config import get_settings
from barkem.input.controller import GamepadConfig, GamepadController
from barkem.input.keyboard import KeyboardConfig, KeyboardController
from barkem.vision.capture import ScreenCapture
from barkem.vision.chat import ChatReader
from barkem.vision.ocr import TextReader
from barkem.vision.regions import load_regions_from_dict
from barkem.vision.state_detector import GameScreen, GameStateDetector


def _build(settings, debug: bool, chat_debug_dir: Optional[str] = None):
    cfg = settings.input
    pad = GamepadController(
        config=GamepadConfig(
            button_delay=cfg.button_delay,
            hold_duration=cfg.hold_duration,
            anchor_presses=cfg.anchor_presses,
            anchor_settle=cfg.anchor_settle,
            verbose=debug,
        )
    )
    pad.connect()

    kb = KeyboardController(config=KeyboardConfig(verbose=debug))
    kb.connect()

    cap = ScreenCapture(target_fps=settings.vision.capture_fps)
    cap.start()

    detector = GameStateDetector(threshold=settings.vision.template_threshold)
    reader = TextReader(
        upscale_factor=settings.vision.ocr_upscale_factor,
        tesseract_cmd=settings.vision.tesseract_cmd,
    )
    regions = load_regions_from_dict(settings.regions)

    chat_region = regions.chat.in_match_chat_area
    if chat_region.is_zero:
        print(
            "WARNING: regions.chat.in_match_chat_area is [0,0,0,0] — "
            "in-match chat OCR will be blind.  Falling back to lobby "
            "chat_area."
        )
        chat_region = regions.chat.chat_area

    chat = ChatReader(
        chat_region=chat_region.as_tuple(),
        text_reader=reader,
        debug_dump_dir=chat_debug_dir,
    )
    sb_reader = ScoreboardReader(ocr=reader, regions=regions.scoreboard)

    return pad, kb, cap, detector, chat, sb_reader, regions


def _warn_missing_templates(detector: GameStateDetector) -> None:
    missing = detector.get_missing_templates()
    relevant = {
        s: templates for s, templates in missing.items()
        if s in (
            GameScreen.MATCH_LOADING,
            GameScreen.MATCH_IN_PROGRESS,
            GameScreen.MATCH_SUMMARY,
            GameScreen.SCOREBOARD,
        )
    }
    if relevant:
        print("WARNING: missing templates:")
        for screen, names in relevant.items():
            print(f"  {screen.name}: {names}")


def main() -> None:
    p = argparse.ArgumentParser(
        description="BarkEm Phase 5 — in-match monitor (pause + end detection)"
    )
    # Mode switches
    p.add_argument("--read-scoreboard", action="store_true",
                   help="Just OCR the scoreboard from whatever's on screen now and exit.")
    p.add_argument("--skip-summary", action="store_true",
                   help="Look for SUMMARY, press A to skip it, then OCR the scoreboard.")

    # Captains
    p.add_argument("--captain1", default=None, help="Team 1 captain Embark ID")
    p.add_argument("--captain2", default=None, help="Team 2 captain Embark ID")

    # Pause limits (API-style overrides)
    p.add_argument("--max-pause", type=float, default=None,
                   help="Max pause duration in seconds. Default from settings.pause.max_duration_s.")
    p.add_argument("--max-pauses-per-team", type=int, default=None,
                   help="Per-team pause cap. Default from settings.pause.max_pauses_per_team.")
    p.add_argument("--pause-cooldown", type=float, default=None,
                   help="Min seconds between a team's pauses. Default from settings.pause.cooldown_s.")

    # Polling
    p.add_argument("--pause-poll", type=float, default=None,
                   help="Seconds between chat polls (bot opens chat each time). "
                        "Default from settings.monitoring.pause_poll_interval.")
    p.add_argument("--kb-warmup", type=float, default=None,
                   help="Seconds between the priming keystroke and the real chat "
                        "message.  Increase if chat messages have mangled prefixes.  "
                        "Default from settings.monitoring.keyboard_warmup.")
    p.add_argument("--pad-recovery", type=float, default=None,
                   help="Seconds between finishing a typed chat message and the "
                        "next D-pad press.  Increase if pause toggle isn't "
                        "registering.  Default from settings.monitoring.gamepad_recovery.")
    p.add_argument("--max-duration", type=float, default=None,
                   help="Abort the whole match after this many seconds. "
                        "Default from settings.timing.match_max_duration.")

    p.add_argument("--delay", type=int, default=3,
                   help="Pre-flight countdown (focus the game window)")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--dump-chat", nargs="?", const="./debug/chat", default=None,
                   help="Dump the raw chat ROI, the preprocessed image given "
                        "to tesseract, and the raw OCR text for every chat "
                        "poll.  Pass a path or leave blank for ./debug/chat.")
    args = p.parse_args()

    settings = get_settings()

    # Resolve defaults
    max_pause = args.max_pause if args.max_pause is not None else settings.pause.max_duration_s
    max_per_team = (
        args.max_pauses_per_team
        if args.max_pauses_per_team is not None
        else settings.pause.max_pauses_per_team
    )
    pause_cd = args.pause_cooldown if args.pause_cooldown is not None else settings.pause.cooldown_s
    pause_poll = args.pause_poll if args.pause_poll is not None else settings.monitoring.pause_poll_interval
    max_dur = args.max_duration if args.max_duration is not None else float(settings.timing.match_max_duration)

    pad, kb, cap, detector, chat, sb_reader, regions = _build(
        settings, args.debug, chat_debug_dir=args.dump_chat,
    )
    if args.dump_chat:
        print(f"[match-watch] dumping chat OCR debug artifacts to {args.dump_chat}/")
    _warn_missing_templates(detector)

    try:
        for i in range(args.delay, 0, -1):
            print(f"Warming up in {i}...")
            time.sleep(1)

        # ── Mode: just OCR scoreboard and quit ──
        if args.read_scoreboard:
            frame = cap.grab()
            if frame is None:
                print("No frame available.")
                return
            result = sb_reader.read(frame)
            _print_scoreboard(result)
            return

        # ── Mode: wait for SUMMARY, press A, OCR ──
        if args.skip_summary:
            print("[match-watch] polling for SUMMARY screen... (Ctrl-C to stop)")
            try:
                while True:
                    frame = cap.grab()
                    if frame is None:
                        time.sleep(1)
                        continue
                    screen, _ = detector.detect(
                        frame, candidates=[GameScreen.MATCH_SUMMARY, GameScreen.SCOREBOARD],
                    )
                    if screen == GameScreen.MATCH_SUMMARY:
                        print("  SUMMARY detected — pressing A")
                        time.sleep(settings.monitoring.summary_skip_delay)
                        pad.press("a")
                        break
                    if screen == GameScreen.SCOREBOARD:
                        print("  SCOREBOARD already visible")
                        break
                    time.sleep(2)

                # Small wait + OCR
                time.sleep(1.5)
                frame = cap.grab()
                if frame is not None:
                    result = sb_reader.read(frame)
                    _print_scoreboard(result)
            except KeyboardInterrupt:
                print("  aborted.")
            return

        # ── Default: full monitor loop ──
        captains = {}
        if args.captain1:
            captains["team1"] = args.captain1
        if args.captain2:
            captains["team2"] = args.captain2

        if not captains:
            print(
                "No captains provided — pause polling will be skipped. "
                "The loop will still detect match end."
            )

        limits = PauseLimits(
            max_duration_s=max_pause,
            max_pauses_per_team=max_per_team,
            cooldown_s=pause_cd,
        )
        pause_handler = PauseHandler(
            gamepad=pad,
            keyboard=kb,
            capture=cap,
            chat_reader=chat,
            limits=limits,
            menu_hold_duration=settings.monitoring.menu_hold_duration,
            chat_open_settle=settings.monitoring.chat_open_settle,
            keyboard_warmup=args.kb_warmup if args.kb_warmup is not None
                else settings.monitoring.keyboard_warmup,
            gamepad_recovery=args.pad_recovery if args.pad_recovery is not None
                else settings.monitoring.gamepad_recovery,
            pause_countdown=settings.monitoring.pause_countdown_seconds,
            unpause_countdown=settings.monitoring.unpause_countdown_seconds,
            poll_interval=pause_poll,
            verbose=True,
        )

        monitor_cfg = MatchMonitorConfig(
            pause_poll_interval=pause_poll,
            early_poll_interval=float(settings.monitoring.initial_poll_interval),
            mid_poll_interval=float(settings.monitoring.mid_poll_interval),
            late_poll_interval=float(settings.monitoring.late_poll_interval),
            late_threshold_s=float(settings.monitoring.late_threshold_seconds),
            menu_hold_duration=settings.monitoring.menu_hold_duration,
            chat_open_settle=settings.monitoring.chat_open_settle,
            summary_skip_delay=settings.monitoring.summary_skip_delay,
            summary_to_scoreboard_timeout=settings.monitoring.summary_to_scoreboard_timeout,
            max_match_duration_s=max_dur,
        )
        monitor = MatchMonitor(
            gamepad=pad,
            capture=cap,
            state_detector=detector,
            chat_reader=chat,
            pause_handler=pause_handler,
            scoreboard_reader=sb_reader,
            captains=captains,
            config=monitor_cfg,
            verbose=True,
        )

        print(
            f"[match-watch] monitor starting — "
            f"pause_poll={pause_poll}s  max_pause={max_pause}s  "
            f"max_pauses/team={max_per_team}  match_max={max_dur}s"
        )
        result = monitor.run()

        print()
        print(f"  success     = {result.success}")
        print(f"  timed_out   = {result.timed_out}")
        print(f"  duration    = {result.duration_s:.1f}s")
        print(f"  pauses      = {len(result.pause_outcomes)}")
        for o in result.pause_outcomes:
            print(f"    - {o.team} {o.captain} {o.duration_s:.1f}s timed_out={o.timed_out}")
        if result.scoreboard:
            print()
            _print_scoreboard(result.scoreboard)
        if result.error:
            print(f"  error       = {result.error}")

    finally:
        pad.disconnect()
        kb.disconnect()
        cap.stop()


def _print_scoreboard(result) -> None:
    print("──── Scoreboard ────")
    if result.error:
        print(f"  NOTE: {result.error}")
    for team in (result.team1, result.team2):
        flag = " ← winner" if result.winner_team_id == team.team_id else ""
        print(f"  Team {team.team_id}  name={team.team_name!r}  total={team.total_score}{flag}")
        for p in team.players:
            print(f"    {p.slot:20}  {p.ocr_name!r:30}  {p.score}")


if __name__ == "__main__":
    main()
