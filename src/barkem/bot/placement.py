"""
Phase 3 — Team placement orchestrator (shortcut-button flow).

With lobby shortcut buttons (LB/RB = Team 1/2, RS = Spectator, LS =
Unassigned), placement is much simpler than the old context-menu flow:

  • From the dropdown-edited state, one RIGHT press lands the cursor
    on the first unassigned slot — which is the bot, since the bot is
    the only player who was unassigned when the lobby was first opened
    and nobody has moved it since.
  • DOWN once → now on the first *real* player (row 1 of unassigned).
  • For each expected player (in the order they appear unassigned),
    press the destination shortcut.  The moved player leaves the list,
    every row below shifts up by one, and the cursor stays put — so the
    next player is now on the same slot.  No re-navigation needed.

We still OCR-snapshot once up front to:
  (a) confirm all expected players have actually joined, and
  (b) know the order they sit in the unassigned list, so the per-slot
      destination plan matches reality.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from barkem.input.navigator import LobbyNavigator
from barkem.vision.capture import ScreenCapture
from barkem.vision.lobby_reader import LobbyReader, LobbySnapshot


@dataclass
class PlacementResult:
    success: bool
    placed: list[str] = field(default_factory=list)   # embark IDs moved, in order
    missing: list[str] = field(default_factory=list)  # expected but not unassigned
    verify_mismatches: list[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.success and not self.missing and not self.verify_mismatches


class TeamPlacer:
    """
    Place expected players into Team 1 / Team 2 using lobby shortcut buttons.

    The bot is expected to still be unassigned (at the top of the list)
    and the cursor is expected to be one RIGHT away from landing on it
    — i.e. we've just come back from editing a dropdown in the left
    column.  See ``LobbyCreator.create_and_read_code`` for the setup.
    """

    def __init__(
        self,
        lobby_nav: LobbyNavigator,
        lobby_reader: LobbyReader,
        capture: ScreenCapture,
        bot_embark_id: str,
        verify_fuzzy_threshold: int = 75,
        step_wait: float = 0.3,
        snapshot_settle: float = 0.4,
        verbose: bool = False,
    ):
        self.nav = lobby_nav
        self.reader = lobby_reader
        self.capture = capture
        self.bot_embark_id = bot_embark_id
        self.verify_threshold = verify_fuzzy_threshold
        self.step_wait = step_wait
        self.snapshot_settle = snapshot_settle
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    # ── Public API ──────────────────────────────────────────────────────

    def place_teams(
        self,
        team1_ids: list[str],
        team2_ids: list[str],
        verify_after: bool = True,
        spectate_bot: bool = True,
    ) -> PlacementResult:
        """
        Place every listed ID onto the correct team.

        Only players that actually match a listed team ID get moved.
        Unassigned players that aren't listed (and aren't the bot) are
        left untouched — useful for partial-roster testing with just
        one or two real accounts.

        When ``spectate_bot`` is True, the bot is sent to spectator at
        the very end (after all placements + verification).
        """
        self._log("\n=== [placement] Snapshot unassigned list ===")
        snap = self._snapshot()
        if snap is None:
            return PlacementResult(success=False, error="Could not capture lobby frame.")
        self._log(f"    unassigned = {snap.unassigned}")

        expected = set(self._norm(p) for p in (team1_ids + team2_ids))
        missing = [
            pid for pid in (team1_ids + team2_ids)
            if not self._is_bot(pid) and snap.index_of(pid, self.verify_threshold) is None
        ]
        if missing:
            return PlacementResult(
                success=False,
                missing=missing,
                error=f"Expected players not found unassigned: {missing}",
            )

        # Walk the unassigned list top-down.  For each slot, either move
        # it (to team1/team2) or skip it (leave it unassigned) by
        # pressing DOWN.  The bot itself is always skipped with DOWN.
        plan: list[tuple[str, str]] = []   # (name, "team1"|"team2"|"skip")
        for name in snap.unassigned:
            if self._fuzzy_in(name, self.bot_embark_id):
                plan.append((name, "skip"))
                continue
            dest = self._destination_for(name, team1_ids, team2_ids)
            plan.append((name, dest))

        self._log("    plan (top-down):")
        for name, dest in plan:
            self._log(f"      {name!r} → {dest}")

        # Move cursor from "just edited a dropdown" → first unassigned.
        # RIGHT lands on the first unassigned slot (which is row 0).
        self._log("\n=== [placement] Positioning cursor (RIGHT) ===")
        self.nav.ctrl.press("right")
        time.sleep(self.step_wait)

        # Top-down walk.  When we MOVE a player, the list shifts up and
        # the cursor stays on the same screen slot → next player is now
        # there, no navigation needed.  When we SKIP, the cursor has to
        # step DOWN to reach the next row.
        placed: list[str] = []
        for name, dest in plan:
            if dest == "skip":
                self._log(f"    skip {name!r} (DOWN)")
                self.nav.ctrl.press("down")
                time.sleep(self.step_wait)
            else:
                self._log(f"    move {name!r} → {dest}")
                self.nav.move_highlighted(dest)
                placed.append(name)

        mismatches: list[str] = []
        if verify_after:
            self._log("\n=== [placement] Verifying team composition ===")
            mismatches = self._verify_teams(team1_ids, team2_ids)
            if mismatches:
                self._log(f"    mismatches = {mismatches}")

        if spectate_bot:
            self._log("\n=== [placement] Sending bot to spectator ===")
            # Anchor → cursor lands on the first unassigned slot, which
            # is the bot (it's the only unassigned player left).
            self.nav.anchor()
            time.sleep(self.step_wait)
            self.nav.move_highlighted("spectator")

        return PlacementResult(
            success=True,
            placed=placed,
            verify_mismatches=mismatches,
        )

    def snapshot(self) -> Optional[LobbySnapshot]:
        """Public passthrough for debug tools."""
        return self._snapshot()

    # ── Internals ───────────────────────────────────────────────────────

    def _destination_for(
        self,
        name: str,
        team1_ids: list[str],
        team2_ids: list[str],
    ) -> str:
        for pid in team1_ids:
            if self._fuzzy_in(name, pid):
                return "team1"
        for pid in team2_ids:
            if self._fuzzy_in(name, pid):
                return "team2"
        return "spectator"

    def _snapshot(self) -> Optional[LobbySnapshot]:
        time.sleep(self.snapshot_settle)
        frame = self.capture.grab()
        if frame is None:
            return None
        return self.reader.read_snapshot(frame)

    def _verify_teams(
        self,
        team1_ids: list[str],
        team2_ids: list[str],
    ) -> list[str]:
        snap = self._snapshot()
        if snap is None:
            return ["<frame grab failed during verify>"]

        mismatches: list[str] = []
        for i, pid in enumerate(team1_ids):
            if self._is_bot(pid):
                continue
            seen = snap.team1[i] if i < len(snap.team1) else None
            if not seen or not self._fuzzy_in(seen, pid):
                mismatches.append(f"team1[{i}] expected={pid!r} saw={seen!r}")
        for i, pid in enumerate(team2_ids):
            if self._is_bot(pid):
                continue
            seen = snap.team2[i] if i < len(snap.team2) else None
            if not seen or not self._fuzzy_in(seen, pid):
                mismatches.append(f"team2[{i}] expected={pid!r} saw={seen!r}")
        return mismatches

    def _is_bot(self, embark_id: str) -> bool:
        return self._norm(embark_id) == self._norm(self.bot_embark_id)

    @staticmethod
    def _norm(s: str) -> str:
        return s.lower().strip()

    def _fuzzy_in(self, seen: str, expected: str) -> bool:
        from rapidfuzz import fuzz
        s = self._norm(seen)
        e = self._norm(expected)
        if not s:
            return False
        if s in e or e in s:
            return True
        return fuzz.ratio(s, e) >= self.verify_threshold
