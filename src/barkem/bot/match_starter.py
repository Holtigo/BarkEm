"""
Phase 4 — Ready-command monitoring + match start.

MatchStarter polls in-game chat for ``-em ready`` commands from team
captains.  When enough captains have ready'd up (``min_ready_captains``
— 2 in production, 1 for solo testing), it presses X to start the
match from the private match lobby screen.

Why X (not Start):
  The game's private match lobby accepts **X** as a direct "start match"
  shortcut from anywhere in the lobby — no need to navigate to the Start
  button.  This is the same UX the human-facing UI advertises at the
  bottom of the screen ("X to start").

Chat fades:
  The Finals' chat messages fade out after a few seconds, so we poll
  fast (``chat_poll_interval``, default 1s) and track *which captains
  have ready'd* rather than trying to diff an unbounded message log.
  A captain who said "-em ready" once stays ready for the rest of the
  WAITING_FOR_READY phase.

Loading time:
  Once X is pressed, the game takes 5-15 seconds to transition into the
  match (server-dependent).  We do NOT do a blocking countdown here —
  it would just eat wall-clock before the game's own loading screen.
  If a user-facing countdown is wanted later, wire it into the API
  layer's webhook notifications (the bot-side countdown was in the v2.4
  report but is deliberately skipped here — see README Phase 4).
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from barkem.input.controller import GamepadController
from barkem.vision.capture import ScreenCapture
from barkem.vision.chat import ChatReader


@dataclass
class ReadyStatus:
    """Which captains have ready'd up so far."""

    team1: bool = False
    team2: bool = False
    # Raw Embark IDs whose ready was detected (for logging / webhooks).
    seen_from: list[str] = field(default_factory=list)

    @property
    def ready_count(self) -> int:
        return int(self.team1) + int(self.team2)


@dataclass
class StartResult:
    """Outcome of a MatchStarter.wait_and_start call."""

    success: bool
    started: bool = False                 # True iff X was actually pressed
    ready_status: ReadyStatus = field(default_factory=ReadyStatus)
    timed_out: bool = False
    error: Optional[str] = None


class MatchStarter:
    """
    Monitor chat for ``-em ready`` and press X to start the match.

    Expected state at entry: bot is in the private match lobby, after
    team placement.  The cursor state doesn't matter — X works as a
    match-start shortcut from anywhere inside the lobby view.

    Usage:
        starter = MatchStarter(
            gamepad=pad, capture=cap, chat_reader=chat,
            captain1="Alice#1234", captain2="Bob#5678",
            min_ready_captains=2,          # 1 for single-captain tests
        )
        result = starter.wait_and_start(timeout_s=300)
    """

    # Command the bot is listening for (ChatReader prepends "-em ").
    READY_COMMAND = "ready"

    def __init__(
        self,
        gamepad: GamepadController,
        capture: ScreenCapture,
        chat_reader: ChatReader,
        captain1: str,
        captain2: Optional[str] = None,
        min_ready_captains: int = 2,
        poll_interval: float = 1.0,
        start_settle: float = 1.0,
        fuzzy_threshold: int = 80,
        verbose: bool = False,
    ):
        """
        Args:
            gamepad: Virtual controller — used for the X press.
            capture: DXcam screen capture for chat OCR.
            chat_reader: ChatReader instance (sees chat_region).
            captain1: Team 1 captain Embark ID.
            captain2: Team 2 captain Embark ID.  Optional in testing
                when ``min_ready_captains=1`` and you only have 1 real
                account; can be left as the bot's own ID or ``None``.
            min_ready_captains: How many distinct captains must ready
                up before X is pressed.  Default 2 (production).  Set
                to 1 for solo testing.
            poll_interval: Seconds between chat OCR polls.  Chat fades
                quickly in The Finals, so keep this small.
            start_settle: Seconds to wait after pressing X before
                returning — lets the loading screen replace the lobby
                UI so downstream state detection doesn't race.
            fuzzy_threshold: Minimum fuzzy score for matching an OCR'd
                name to a captain Embark ID.
            verbose: Print every chat poll / detection.
        """
        if min_ready_captains not in (1, 2):
            raise ValueError(
                f"min_ready_captains must be 1 or 2, got {min_ready_captains}"
            )
        self.pad = gamepad
        self.cap = capture
        self.chat = chat_reader
        self.captain1 = captain1
        self.captain2 = captain2 or ""
        self.min_ready = min_ready_captains
        self.poll_interval = poll_interval
        self.start_settle = start_settle
        self.fuzzy_threshold = fuzzy_threshold
        self.verbose = verbose

        self._status = ReadyStatus()

    # ── Logging ─────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def status(self) -> ReadyStatus:
        return self._status

    def reset(self) -> None:
        self._status = ReadyStatus()

    def wait_and_start(
        self,
        timeout_s: float = 300.0,
        dry_run: bool = False,
    ) -> StartResult:
        """
        Poll chat until enough captains have ready'd up, then press X.

        Args:
            timeout_s: Abort after this many seconds with timed_out=True.
            dry_run: If True, return on threshold without pressing X
                (useful for solo chat-reading tests).

        Returns StartResult.  Note that ``started=True`` only means the
        X press was issued; downstream (match-loading detection) is
        handled by the match-monitor loop, not here.
        """
        deadline = time.monotonic() + timeout_s
        c2 = self.captain2 or "-"
        self._log(
            f"[match-starter] waiting for {self.min_ready} captain(s) "
            f"to say '-em {self.READY_COMMAND}' "
            f"(captain1={self.captain1!r}, captain2={c2!r})"
        )

        while time.monotonic() < deadline:
            self._poll_once()

            if self._status.ready_count >= self.min_ready:
                self._log(
                    f"[match-starter] threshold met "
                    f"({self._status.ready_count}/{self.min_ready}); "
                    f"team1={self._status.team1}, team2={self._status.team2}"
                )
                if dry_run:
                    return StartResult(
                        success=True, started=False,
                        ready_status=self._status,
                    )
                return self._press_start()

            time.sleep(self.poll_interval)

        self._log(
            f"[match-starter] TIMEOUT after {timeout_s:.0f}s  "
            f"(ready={self._status.ready_count}/{self.min_ready})"
        )
        return StartResult(
            success=False,
            started=False,
            ready_status=self._status,
            timed_out=True,
            error=(
                f"Only {self._status.ready_count}/{self.min_ready} captain(s) "
                f"ready within {timeout_s:.0f}s"
            ),
        )

    def force_start(self) -> StartResult:
        """Press X immediately without waiting for chat.  For --skip-ready tests."""
        self._log("[match-starter] force_start — pressing X without ready check")
        return self._press_start()

    # ── Internals ──────────────────────────────────────────────────────

    def _poll_once(self) -> None:
        """Grab one frame, OCR chat, mark any captain's ready status."""
        frame = self.cap.grab()
        if frame is None:
            return

        # check_for_command walks the current chat messages and returns
        # the first captain whose message matched.  We call it twice —
        # once per allowed captain — so a match for team1 doesn't mask
        # a simultaneous team2 match in the same poll.
        if not self._status.team1:
            if self._match(frame, [self.captain1]):
                self._status.team1 = True
                self._status.seen_from.append(self.captain1)
                self._log(f"    ready ✓ team1 = {self.captain1}")

        if not self._status.team2 and self.captain2:
            if self._match(frame, [self.captain2]):
                self._status.team2 = True
                self._status.seen_from.append(self.captain2)
                self._log(f"    ready ✓ team2 = {self.captain2}")

        # Solo-captain test mode: captain2 may be empty — count team1 alone.
        if self.min_ready == 1 and self._status.team1 and not self._status.team2:
            # Nothing to do; threshold check in wait_and_start handles it.
            pass

    def _match(self, frame, captains: list[str]) -> Optional[str]:
        return self.chat.check_for_command(
            frame,
            command=self.READY_COMMAND,
            allowed_players=captains,
            fuzzy_threshold=self.fuzzy_threshold,
        )

    def _press_start(self) -> StartResult:
        """Issue the X press and return."""
        try:
            self.pad.press("x")
        except Exception as e:
            return StartResult(
                success=False,
                started=False,
                ready_status=self._status,
                error=f"Gamepad X press failed: {e}",
            )
        time.sleep(self.start_settle)
        return StartResult(
            success=True,
            started=True,
            ready_status=self._status,
        )
