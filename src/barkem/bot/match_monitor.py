"""
In-match monitoring loop.

Drives the match from "X pressed" until the final scoreboard is OCR'd:

    1. MATCH_LOADING  → just wait (sparse template polling)
    2. MATCH_IN_PROGRESS → periodic chat polling for "-em pause"
         - On pause request: hand off to PauseHandler for one cycle,
           then resume monitoring
    3. MATCH_SUMMARY detected → press A to skip immediately
    4. Scoreboard visible → hand frame to ScoreboardReader, return results

The in-match chat region differs from the lobby chat region, so the
caller must swap the ChatReader region to ``regions.chat.in_match_chat_area``
before passing the reader in.  (This module does not swap regions
itself; it trusts the reader it's given.)
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from barkem.bot.pause_handler import PauseHandler, PauseOutcome
from barkem.bot.scoreboard_reader import ScoreboardReader, ScoreboardResult
from barkem.input.controller import GamepadController
from barkem.vision.capture import ScreenCapture
from barkem.vision.chat import ChatReader
from barkem.vision.state_detector import GameScreen, GameStateDetector


@dataclass
class MatchMonitorConfig:
    """Polling / timing for the in-match loop."""

    # How often to hold-Menu and OCR chat for pause commands.
    pause_poll_interval: float = 5.0

    # Sparse match-end polling — interval grows/shrinks with elapsed time.
    early_poll_interval: float = 60.0
    mid_poll_interval: float = 30.0
    late_poll_interval: float = 10.0
    late_threshold_s: float = 600.0   # after 10 min, use late interval

    # Menu-hold + settle for opening in-match chat.
    menu_hold_duration: float = 0.8
    chat_open_settle: float = 0.4

    # Seconds between SUMMARY-detected and A-press.
    summary_skip_delay: float = 1.0
    # How long after A-press to wait for scoreboard before giving up.
    summary_to_scoreboard_timeout: float = 10.0

    # Abort the whole match after this many seconds no matter what.
    max_match_duration_s: float = 1800.0


@dataclass
class MatchMonitorResult:
    """Outcome of the full match-monitor run."""

    success: bool
    scoreboard: Optional[ScoreboardResult] = None
    pause_outcomes: list[PauseOutcome] = field(default_factory=list)
    duration_s: float = 0.0
    timed_out: bool = False
    error: Optional[str] = None


class MatchMonitor:
    """
    Monitor a live match until scoreboard OCR completes.

    Wiring:
        monitor = MatchMonitor(
            gamepad=pad,
            capture=cap,
            state_detector=detector,
            chat_reader=chat_reader_on_in_match_region,
            pause_handler=pause_handler,
            scoreboard_reader=sb_reader,
            captains={"team1": cap1, "team2": cap2},
            config=cfg,
        )
        result = monitor.run()
    """

    PAUSE_COMMAND = "pause"

    def __init__(
        self,
        gamepad: GamepadController,
        capture: ScreenCapture,
        state_detector: GameStateDetector,
        chat_reader: ChatReader,
        pause_handler: PauseHandler,
        scoreboard_reader: ScoreboardReader,
        captains: dict[str, str],          # {"team1": id1, "team2": id2}
        config: Optional[MatchMonitorConfig] = None,
        verbose: bool = False,
    ):
        self.pad = gamepad
        self.cap = capture
        self.detector = state_detector
        self.chat = chat_reader
        self.pause_handler = pause_handler
        self.sb_reader = scoreboard_reader
        self.captains = {k: v for k, v in captains.items() if v}
        self.cfg = config or MatchMonitorConfig()
        self.verbose = verbose

        self._started_at: float = 0.0
        self._aborted: bool = False

        # After firing a pause, record a snapshot of the last few chat
        # lines.  The next poll only fires if the *bottom* of the chat
        # has demonstrably moved on — a new line appeared, or the
        # existing bottom changed.  This sidesteps OCR flicker on
        # faded older messages (The Finals de-emphasises old chat and
        # tesseract hallucinates from the low-contrast glyphs).
        self._bottom_snapshot: list[str] = []

    # ── Public API ──────────────────────────────────────────────────

    def abort(self) -> None:
        """External kill-switch; the loop will unwind at the next check."""
        self._aborted = True

    def run(self) -> MatchMonitorResult:
        self._started_at = time.time()
        outcomes: list[PauseOutcome] = []

        try:
            # Phase 5a: wait through loading until the match actually starts
            # We don't strictly need the loading template — any non-menu
            # screen that eventually transitions to in-match is fine.
            self._log("[monitor] match loop started — waiting for in-match state")

            last_match_poll = 0.0
            last_chat_poll = 0.0

            while True:
                if self._aborted:
                    return self._abort_result("aborted externally", outcomes)

                elapsed = time.time() - self._started_at
                if elapsed > self.cfg.max_match_duration_s:
                    self._log(f"[monitor] max_match_duration reached ({elapsed:.0f}s)")
                    return MatchMonitorResult(
                        success=False,
                        pause_outcomes=outcomes,
                        duration_s=elapsed,
                        timed_out=True,
                        error="match exceeded max_match_duration_s",
                    )

                now = time.time()

                # 1. Sparse match-state poll
                poll_int = self._match_poll_interval(elapsed)
                if (now - last_match_poll) >= poll_int:
                    last_match_poll = now
                    frame = self.cap.grab()
                    if frame is not None:
                        screen, _ = self.detector.detect(
                            frame,
                            candidates=[
                                GameScreen.MATCH_SUMMARY,
                                GameScreen.SCOREBOARD,
                                GameScreen.MATCH_COMPLETE,
                            ],
                        )
                        if screen == GameScreen.MATCH_SUMMARY:
                            self._log("[monitor] SUMMARY detected — skipping with A")
                            time.sleep(self.cfg.summary_skip_delay)
                            self.pad.press("a")
                            sb = self._wait_and_read_scoreboard()
                            return MatchMonitorResult(
                                success=sb.ok if sb else False,
                                scoreboard=sb,
                                pause_outcomes=outcomes,
                                duration_s=time.time() - self._started_at,
                                error=(sb.error if sb else "no scoreboard frame"),
                            )

                        if screen in (GameScreen.SCOREBOARD, GameScreen.MATCH_COMPLETE):
                            # Missed the SUMMARY — scoreboard is already up
                            self._log(f"[monitor] {screen.name} detected — reading scoreboard")
                            sb = self.sb_reader.read(frame)
                            return MatchMonitorResult(
                                success=sb.ok,
                                scoreboard=sb,
                                pause_outcomes=outcomes,
                                duration_s=time.time() - self._started_at,
                            )

                # 2. Pause-command polling (slower than match poll — involves
                #    driving hold-Menu + OCR + B-close)
                if (
                    self.captains
                    and (now - last_chat_poll) >= self.cfg.pause_poll_interval
                ):
                    last_chat_poll = now
                    outcome = self._poll_for_pause()
                    if outcome is not None:
                        outcomes.append(outcome)

                # Sleep briefly — real pacing is enforced by the two timers above
                time.sleep(0.5)

        except KeyboardInterrupt:
            return self._abort_result("KeyboardInterrupt", outcomes)

    # ── Internals ───────────────────────────────────────────────────

    def _match_poll_interval(self, elapsed_s: float) -> float:
        if elapsed_s < 240:
            return self.cfg.early_poll_interval
        if elapsed_s < self.cfg.late_threshold_s:
            return self.cfg.mid_poll_interval
        return self.cfg.late_poll_interval

    # Look at this many of the newest chat lines for pause commands.
    # Older lines fade in The Finals' UI and OCR on them is unreliable,
    # producing phantom `-em pause` hits from faded countdown messages.
    PAUSE_SCAN_DEPTH = 2

    def _poll_for_pause(self) -> Optional[PauseOutcome]:
        """Open chat, look for -em pause from a captain, act on it.

        Fires only when a pause command appears in the most-recent
        ``PAUSE_SCAN_DEPTH`` chat lines AND the bottom of chat has
        moved since the last pause we acted on.  Limiting the scan
        window sidesteps OCR flicker on faded older messages, which
        was driving false re-fires from the bot's own countdown text.
        """
        # Open chat
        self.pad.press_hold("start", self.cfg.menu_hold_duration)
        time.sleep(self.cfg.chat_open_settle)

        frame = self.cap.grab()
        if frame is None:
            self.pad.press("b")
            return None

        messages = self.chat.read_chat(frame)
        tail = messages[-self.PAUSE_SCAN_DEPTH:]
        bottom_cores = [self._line_core(m) for m in tail]

        if self.verbose:
            self._log(
                f"[monitor] pause-poll: scanning bottom {len(tail)} of "
                f"{len(messages)} lines.  snapshot={self._bottom_snapshot}"
            )
            for m in messages:
                self._log(f"[monitor]   chat: {m.player_name!r}: {m.message!r}")

        # Bottom of chat unchanged → nothing new, skip.
        if bottom_cores and bottom_cores == self._bottom_snapshot:
            self.pad.press("b")
            return None

        hit: Optional[tuple[str, str, object]] = None  # (team, captain, msg)
        for msg in tail:
            for team, captain in self.captains.items():
                if not self.chat._names_match(
                    msg.player_name, captain, threshold=55
                ):
                    continue
                if self.chat._command_matches(msg.message, self.PAUSE_COMMAND):
                    hit = (team, captain, msg)
                    break
            if hit:
                break

        # Close chat before running the pause cycle — PauseHandler opens
        # chat itself for each announcement.
        self.pad.press("b")

        if hit is None:
            # Bottom moved but no command there — update snapshot so we
            # don't keep re-scanning the same non-command tail.
            self._bottom_snapshot = bottom_cores
            return None

        team, captain, _matched_msg = hit

        outcome = self.pause_handler.handle_pause(team=team, captain=captain)

        # Refresh snapshot to post-cycle bottom so we don't re-fire on
        # the lines the handler itself added (countdowns, confirmations).
        self._refresh_bottom_snapshot()

        return outcome

    @staticmethod
    def _line_core(msg) -> str:
        """Normalized identity of a chat line for change-detection."""
        name = "".join(c for c in msg.player_name.lower() if c.isalnum())
        body = "".join(c for c in msg.message.lower() if c.isalnum())
        return f"{name}|{body}"

    def _refresh_bottom_snapshot(self) -> None:
        """Re-open chat and snapshot the bottom N lines."""
        self.pad.press_hold("start", self.cfg.menu_hold_duration)
        time.sleep(self.cfg.chat_open_settle)
        frame = self.cap.grab()
        self.pad.press("b")
        if frame is None:
            return
        messages = self.chat.read_chat(frame)
        tail = messages[-self.PAUSE_SCAN_DEPTH:]
        self._bottom_snapshot = [self._line_core(m) for m in tail]

    def _wait_and_read_scoreboard(self) -> Optional[ScoreboardResult]:
        """After pressing A on SUMMARY, poll briefly for the scoreboard."""
        deadline = time.time() + self.cfg.summary_to_scoreboard_timeout
        last_frame: Optional[np.ndarray] = None
        while time.time() < deadline:
            frame = self.cap.grab()
            if frame is None:
                time.sleep(0.3)
                continue
            last_frame = frame
            screen, _ = self.detector.detect(
                frame,
                candidates=[GameScreen.SCOREBOARD, GameScreen.MATCH_COMPLETE],
            )
            if screen in (GameScreen.SCOREBOARD, GameScreen.MATCH_COMPLETE):
                return self.sb_reader.read(frame)
            time.sleep(0.5)

        # Fallback — OCR whatever is on screen now.  The scoreboard
        # regions may still be legible even without a template confirm.
        if last_frame is not None:
            result = self.sb_reader.read(last_frame)
            result.error = (
                result.error
                or "scoreboard template not matched — OCR'd best-effort"
            )
            return result
        return None

    def _abort_result(self, reason: str, outcomes: list[PauseOutcome]) -> MatchMonitorResult:
        return MatchMonitorResult(
            success=False,
            pause_outcomes=outcomes,
            duration_s=time.time() - self._started_at,
            error=reason,
        )

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)
