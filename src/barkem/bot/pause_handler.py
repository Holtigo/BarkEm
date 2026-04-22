"""
In-match pause / unpause orchestration.

Responsibilities:
  • Drive the pause countdown (bot types "Pausing in N..." to chat)
  • Toggle pause via D-pad Left
  • Wait for either the originating captain to say "-em unpause" (or
    "-em continue") OR the configured max_duration to elapse
  • Drive the unpause countdown and toggle pause off

Chat-typing flow — in-match chat auto-closes after Enter, so every
message requires:
    hold Menu → wait chat_open_settle → type+enter → (chat closes)

Pause button:
    D-pad Left toggles pause on/off in a private match.  Pressing it
    again (from the paused state) unpauses.

Dedup guard (important):
    When the bot reads chat by hold-Menu-then-OCR, the captain's
    original "-em pause" line may still be visible in the window on
    subsequent polls.  The pause handler exposes a
    ``mark_command_consumed(msg)`` method the monitor calls after
    accepting the command, and the next poll ignores any command
    whose (name, message) fingerprint matches a consumed one unless
    a strictly-newer message appears below it.
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from barkem.input.controller import GamepadController
from barkem.input.keyboard import KeyboardController
from barkem.vision.capture import ScreenCapture
from barkem.vision.chat import ChatMessage, ChatReader


@dataclass
class PauseLimits:
    """Per-match pause limits (API-overridable)."""

    max_duration_s: float = 300.0
    max_pauses_per_team: int = 2
    cooldown_s: float = 30.0


@dataclass
class PauseAccounting:
    """Running per-team counters across the match."""

    used_team1: int = 0
    used_team2: int = 0
    last_pause_at_team1: float = 0.0
    last_pause_at_team2: float = 0.0

    def used_for(self, team: str) -> int:
        return self.used_team1 if team == "team1" else self.used_team2

    def last_for(self, team: str) -> float:
        return (
            self.last_pause_at_team1 if team == "team1" else self.last_pause_at_team2
        )

    def record(self, team: str, now: float) -> None:
        if team == "team1":
            self.used_team1 += 1
            self.last_pause_at_team1 = now
        else:
            self.used_team2 += 1
            self.last_pause_at_team2 = now


@dataclass
class PauseOutcome:
    """Result of a single pause->unpause cycle."""

    accepted: bool
    team: Optional[str] = None            # "team1" / "team2" / None if rejected
    captain: Optional[str] = None
    duration_s: float = 0.0
    timed_out: bool = False               # True if max_duration triggered unpause
    reason: Optional[str] = None


class PauseHandler:
    """
    Executes a single pause cycle (announce → pause → wait → unpause).

    The match monitor is responsible for detecting the initial
    ``-em pause`` command and invoking handle_pause().
    """

    PAUSE_BUTTON = "left"   # D-pad Left toggles pause/unpause

    def __init__(
        self,
        gamepad: GamepadController,
        keyboard: KeyboardController,
        capture: ScreenCapture,
        chat_reader: ChatReader,
        limits: PauseLimits,
        menu_hold_duration: float = 0.8,
        chat_open_settle: float = 0.4,
        keyboard_warmup: float = 0.6,
        gamepad_recovery: float = 0.4,
        pause_countdown: int = 3,
        unpause_countdown: int = 5,
        poll_interval: float = 5.0,
        verbose: bool = False,
    ):
        self.pad = gamepad
        self.kb = keyboard
        self.cap = capture
        self.chat = chat_reader
        self.limits = limits
        self.menu_hold = menu_hold_duration
        self.settle = chat_open_settle
        # Time between first-keystroke-primer and real message — lets
        # the game finish handing focus to the keyboard after chat open.
        self.kb_warmup = keyboard_warmup
        # Time after typing + Enter before the gamepad can be trusted
        # again — GeForce NOW has to swap input modes back.
        self.pad_recovery = gamepad_recovery
        self.pause_countdown = pause_countdown
        self.unpause_countdown = unpause_countdown
        self.poll_interval = poll_interval
        self.verbose = verbose

        self.accounting = PauseAccounting()

        # Fingerprints of chat messages whose command has already been
        # acted on.  The monitor and handler share this so a stale
        # "-em pause" or "-em unpause" line doesn't refire.
        #
        # Fingerprint uses alphanumeric-only cores so OCR variance
        # ("em pause" vs "-em pause" vs "-em pause.") on the same
        # underlying message still hashes the same.
        self._consumed: set[tuple[str, str]] = set()

    @staticmethod
    def _fingerprint(msg: ChatMessage) -> tuple[str, str]:
        name_core = "".join(c for c in msg.player_name.lower() if c.isalnum())
        msg_core = "".join(c for c in msg.message.lower() if c.isalnum())
        return name_core, msg_core

    # ── Public API ──────────────────────────────────────────────────

    def is_consumed(self, msg: ChatMessage) -> bool:
        return self._fingerprint(msg) in self._consumed

    def mark_consumed(self, msg: ChatMessage) -> None:
        self._consumed.add(self._fingerprint(msg))

    def can_pause(self, team: str, now: float) -> tuple[bool, Optional[str]]:
        """
        Check whether ``team`` is allowed to pause right now.

        Returns (allowed, reason_if_denied).  ``reason_if_denied`` is
        a short human string the caller can echo to chat.
        """
        used = self.accounting.used_for(team)
        if used >= self.limits.max_pauses_per_team:
            return False, f"{team} has no pauses left ({used}/{self.limits.max_pauses_per_team})"
        last = self.accounting.last_for(team)
        if last > 0 and (now - last) < self.limits.cooldown_s:
            wait = self.limits.cooldown_s - (now - last)
            return False, f"{team} pause cooldown: {wait:.0f}s"
        return True, None

    def handle_pause(
        self,
        team: str,
        captain: str,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> PauseOutcome:
        """
        Execute a full pause → wait → unpause cycle.

        Args:
            team: "team1" or "team2" — the team that requested the pause.
            captain: Embark ID of the requesting captain.  Only this
                captain can end the pause early via "-em unpause" /
                "-em continue".
            should_stop: Optional external abort signal (e.g. user
                hit Ctrl-C, or match ended externally).

        Returns PauseOutcome.  Does NOT mutate accounting unless the
        pause is actually applied (accepted=True).
        """
        now = time.time()
        allowed, reason = self.can_pause(team, now)
        if not allowed:
            self._log(f"[pause] denied — {reason}")
            self._announce(f"pause denied: {reason}")
            return PauseOutcome(accepted=False, team=team, captain=captain, reason=reason)

        self._log(f"[pause] {captain} ({team}) requested pause")

        # Snapshot every chat line currently visible from this captain.
        # The wait loop will treat *only lines not in this snapshot* as
        # valid new unpause commands — so stale pre-existing
        # ``-em unpause`` lines can't abort the cycle, but a fresh
        # command with the same text (typed minutes later) will still
        # fire because the chat block as a whole has shifted.
        baseline = self._snapshot_captain_lines(captain)

        # 1. Announce + countdown — collapsed into a single chat line
        # instead of one per second.  Each chat-open cycle costs ~1.2s
        # (menu hold + settle), so 4 separate messages would blow the
        # whole countdown window.  One line keeps the game's wall-clock
        # and the typed countdown roughly in sync.
        announce_started = time.time()
        self._announce(
            f"pausing in {self.pause_countdown}... "
            + " ".join(f"{n}..." for n in range(self.pause_countdown - 1, 0, -1))
        )
        # Sleep *from the announce start* so the pause lands N seconds
        # after the message began — not N seconds after typing finished
        # (typing itself takes ~2s, which would make the actual pause
        # happen well past the stated countdown).
        self._sleep_until(announce_started + float(self.pause_countdown))
        # Give GeForce NOW time to swap back from keyboard to gamepad
        # input mode before we press D-pad Left.
        time.sleep(self.pad_recovery)

        # 2. Toggle pause
        self.pad.press(self.PAUSE_BUTTON)
        pause_started = time.time()
        self.accounting.record(team, pause_started)
        self._log(
            f"[pause] PAUSE applied  (team={team} "
            f"used={self.accounting.used_for(team)}/"
            f"{self.limits.max_pauses_per_team})"
        )
        self._announce(
            f"paused {self.accounting.used_for(team)}/"
            f"{self.limits.max_pauses_per_team}. "
            f"max {int(self.limits.max_duration_s)}s."
        )

        # 3. Wait for unpause command OR max_duration
        timed_out = False
        unpause_deadline = pause_started + self.limits.max_duration_s
        while True:
            if should_stop and should_stop():
                self._log("[pause] external abort — unpausing now")
                break
            if time.time() >= unpause_deadline:
                timed_out = True
                self._log("[pause] max_duration reached — auto-unpause")
                self._announce("pause time up - unpausing.")
                break

            # Open chat to read the unpause command
            self._open_chat()
            frame = self.cap.grab()
            if frame is None:
                self._close_chat()
                time.sleep(self.poll_interval)
                continue

            matched = self._find_new_unpause(frame, captain, baseline)
            self._close_chat()

            if matched is not None:
                self._log(f"[pause] unpause from {captain} — starting countdown")
                break

            time.sleep(self.poll_interval)

        # 4. Unpause countdown — single collapsed message (same reason as
        # the pause countdown: each chat-open cycle costs ~1.2s, so per-
        # second messages would overshoot the countdown window).
        unpause_announce_started = time.time()
        self._announce(
            f"unpausing in {self.unpause_countdown}... "
            + " ".join(f"{n}..." for n in range(self.unpause_countdown - 1, 0, -1))
        )
        self._sleep_until(
            unpause_announce_started + float(self.unpause_countdown)
        )
        time.sleep(self.pad_recovery)

        # 5. Toggle pause off
        self.pad.press(self.PAUSE_BUTTON)
        duration = time.time() - pause_started
        self._log(f"[pause] UNPAUSED after {duration:.1f}s  timed_out={timed_out}")

        return PauseOutcome(
            accepted=True,
            team=team,
            captain=captain,
            duration_s=duration,
            timed_out=timed_out,
        )

    # ── Chat helpers ────────────────────────────────────────────────

    def _open_chat(self) -> None:
        """Hold Menu to open in-match chat, then wait for it to render."""
        self.pad.press_hold("start", self.menu_hold)
        time.sleep(self.settle)

    def _close_chat(self) -> None:
        """Close in-match chat with B."""
        self.pad.press("b")

    def _announce(self, text: str) -> None:
        """Open chat, type text, press Enter (chat auto-closes on Enter)."""
        self._open_chat()
        # ``warmup_delay`` gives the game time to finish focusing the
        # chat input after the gamepad→keyboard handoff.  Without it,
        # the first several characters get eaten on GeForce NOW.
        self.kb.send_message(text, warmup_delay=self.kb_warmup)
        # Chat auto-closes on send; no B needed.  But some UI races can
        # leave it open, so a short settle gives the frame a moment.
        time.sleep(self.settle)

    @staticmethod
    def _sleep_until(deadline: float) -> None:
        """Sleep until absolute wall time ``deadline``; no-op if already past."""
        remaining = deadline - time.time()
        if remaining > 0:
            time.sleep(remaining)

    # Lower name-match threshold for in-pause unpause detection.  The
    # pause is already active and the captain is known; we care more
    # about not missing a legitimate unpause than filtering imposters.
    # (The command-match is strict-two-tokens, so a non-captain line
    # containing a command-like string still has to look like a real
    # command — and any real `-em unpause` in chat during a pause is
    # almost certainly from the captain regardless.)
    PAUSE_NAME_THRESHOLD = 55

    def _snapshot_captain_lines(self, captain: str) -> list[str]:
        """
        OCR the chat window once and return normalized bodies for every
        line whose player-name plausibly matches ``captain``.

        Intentionally over-broad — we'd rather keep too many baseline
        entries (worst case: miss one legitimate new command and catch
        it on the next poll) than too few (fire on stale chat).
        """
        self._open_chat()
        frame = self.cap.grab()
        self._close_chat()
        if frame is None:
            return []
        messages = self.chat.read_chat(frame)
        cores: list[str] = []
        for msg in messages:
            if self.chat._names_match(
                msg.player_name, captain, threshold=self.PAUSE_NAME_THRESHOLD
            ):
                cores.append(self._msg_core(msg.message))
        if self.verbose:
            self._log(
                f"[pause] baseline for {captain!r}: {cores!r} "
                f"(from {len(messages)} visible lines)"
            )
            for msg in messages:
                self._log(
                    f"[pause]   chat: {msg.player_name!r}: {msg.message!r}"
                )
        return cores

    @staticmethod
    def _msg_core(text: str) -> str:
        return "".join(c for c in text.lower() if c.isalnum())

    def _find_new_unpause(
        self, frame, captain: str, baseline: list[str]
    ) -> Optional[tuple]:
        """
        Return the first unpause/continue line whose normalized body is
        NOT already covered by ``baseline``.

        Uses PAUSE_NAME_THRESHOLD for name matching — OCR of Embark IDs
        fluctuates between polls and a tight threshold silently drops
        legitimate unpauses.  The command-match is already strict
        (exactly two tokens, ``em`` + command) so a non-captain line
        can't forge a match by accident.
        """
        baseline_counts: dict[str, int] = {}
        for core in baseline:
            baseline_counts[core] = baseline_counts.get(core, 0) + 1

        messages = self.chat.read_chat(frame)
        seen_counts: dict[str, int] = {}
        for msg in messages:
            if not self.chat._names_match(
                msg.player_name, captain, threshold=self.PAUSE_NAME_THRESHOLD
            ):
                continue
            core = self._msg_core(msg.message)
            seen_counts[core] = seen_counts.get(core, 0) + 1
            is_stale = seen_counts[core] <= baseline_counts.get(core, 0)
            if is_stale:
                continue
            for cmd in ("unpause", "continue"):
                if self.chat._command_matches(msg.message, cmd):
                    if self.verbose:
                        self._log(
                            f"[pause] NEW {cmd!r} detected — "
                            f"{msg.player_name!r}: {msg.message!r}"
                        )
                    return (msg, cmd)
        if self.verbose:
            self._log(
                f"[pause] poll: no new unpause "
                f"(baseline={len(baseline)} lines, chat={len(messages)} lines)"
            )
            for msg in messages:
                self._log(
                    f"[pause]   chat: {msg.player_name!r}: {msg.message!r}"
                )
        return None

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)
