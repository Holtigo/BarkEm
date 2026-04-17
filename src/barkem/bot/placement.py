"""
Phase 3 — Team placement orchestrator (Manage Lobby flow).

The lobby's one-press shortcut buttons (LB/RB/RS) only work on the
local client — pressing them while another player is highlighted just
moves the bot itself.  To move someone else we have to:

  1. Press Y → open Manage Lobby overlay (starts on bot, row 0).
  2. Press DOWN once to "activate" input (game swallows the first one;
     cursor stays on bot).
  3. Press DOWN N more times to reach the target player's row.
     Manage Lobby lists everyone in one column: all unassigned (in join
     order) first, then all assigned (team players) in order.
  4. Press A → context menu opens on that player.
  5. Press DOWN ×4 → land on "Move in Lobby".
     (Context menu order: block, report, promote, kick, move in lobby.
     Not swallowed; first DOWN works normally.  The offset is
     configurable via LobbyGrid.context_move_other.)
  6. Press A → exits Manage Lobby, returns to the normal lobby view
     with the target player "armed" for the next destination button.
  7. Press LB (team1) / RB (team2) / RS (spectator) → actual move.

That's one full Y-cycle per player.  After each cycle the Manage Lobby
list has the moved player at a new position (under the team they were
sent to), but the remaining unassigned players keep their relative
order — bot stays row 0, every remaining unassigned is still contiguous
starting at row 1.

Bot → spectator at the end is a single RS press (self-shortcut; no
navigation needed).
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

        # Build the move list in join order.  We don't store absolute
        # rows because every time a player is moved into a team, the
        # remaining unassigned list compacts up by one — so the next
        # player to move is always at row 1 (bot still at row 0).
        #
        # If the plan contains a "skip" (unlisted unassigned player that
        # should stay unassigned), that player does NOT compact — it
        # stays in the list.  We track how many such skipped players
        # sit above the current target via ``skip_offset``.
        # Row 0 is always the bot — nothing we read there needs to match
        # ``bot_embark_id``.  Everyone else is a real player to classify.
        moves: list[tuple[str, str]] = []   # (name, destination)
        skipped_before: list[int] = []      # skip_offset per move
        running_skips = 0
        for name in snap.unassigned[1:]:
            dest = self._destination_for(name, team1_ids, team2_ids)
            if dest == "spectator":
                # Unlisted player — leave them unassigned.  They stay
                # in the list and push every later move down one row.
                running_skips += 1
                continue
            moves.append((name, dest))
            skipped_before.append(running_skips)

        self._log("    move plan (target row = 1 + skip_offset):")
        for (name, dest), skip in zip(moves, skipped_before):
            self._log(f"      {name!r} → {dest}  (skip_offset={skip})")

        # Execute one Manage Lobby cycle per move.
        placed: list[str] = []
        for (name, dest), skip in zip(moves, skipped_before):
            row = 1 + skip
            self._log(f"\n--- moving {name!r} (row {row}) → {dest} ---")
            self._manage_lobby_move(row, dest)
            placed.append(name)

        mismatches: list[str] = []
        if verify_after:
            self._log("\n=== [placement] Verifying team composition ===")
            mismatches = self._verify_teams(team1_ids, team2_ids)
            if mismatches:
                self._log(f"    mismatches = {mismatches}")

        if spectate_bot:
            # The bot's own shortcut works from any focus state — just
            # press RS and the bot moves itself to spectator.  No need
            # to open Manage Lobby.
            self._log("\n=== [placement] Sending bot to spectator (RS) ===")
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

    def _manage_lobby_move(self, row: int, destination: str) -> None:
        """
        One full Y-cycle: open Manage Lobby, walk to *row*, pick "Move
        in Lobby" from the context menu, then press the destination
        shortcut.

        *row* is 0-based into the Manage Lobby list, which starts with
        the bot at row 0.  So for the first real player *row* = 1, etc.

        After the LB/RB/RS press the game returns to the normal lobby
        view and we're back to square one — next move needs another Y.
        """
        # 1. Open Manage Lobby (Y).  Starts on bot (row 0), input idle.
        self.nav.ctrl.press("y")
        time.sleep(self.step_wait)

        # 2. Press DOWN once to activate input.  Cursor stays on row 0.
        self.nav.ctrl.press("down")
        time.sleep(self.step_wait)

        # 3. Walk to the target row — subsequent DOWNs advance normally.
        if row > 0:
            self.nav.ctrl.press("down", row)
            time.sleep(self.step_wait)

        # 4. Open context menu.
        self.nav.ctrl.confirm()
        time.sleep(self.step_wait)

        # 5. Walk to "Move in Lobby" and confirm.  Game returns to
        #    normal lobby view with the player armed for the next btn.
        self.nav.ctrl.press("down", self.nav.grid.context_move_other)
        time.sleep(self.step_wait)
        self.nav.ctrl.confirm()
        time.sleep(self.step_wait)

        # 6. Fire the destination shortcut — this completes the move.
        self.nav.move_highlighted(destination)

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
        """
        Match on the username portion only (before ``#``).  The
        discriminator tag is easy to OCR wrong (#0746 → 2 etc.) and the
        username alone is unique enough inside a single lobby.
        """
        return self._username(embark_id) == self._username(self.bot_embark_id)

    @staticmethod
    def _username(s: str) -> str:
        # Strip the "#NNNN" tag if present, lowercase, remove anything
        # that isn't a-z/0-9 — robust against OCR noise around '#'.
        base = s.split("#", 1)[0].lower().strip()
        return "".join(c for c in base if c.isalnum())

    @staticmethod
    def _norm(s: str) -> str:
        # Lowercase + strip all non-alphanumerics so OCR noise like
        # missing '#' or trailing digits doesn't break substring match.
        return "".join(c for c in s.lower() if c.isalnum())

    def _fuzzy_in(self, seen: str, expected: str) -> bool:
        from rapidfuzz import fuzz
        s = self._norm(seen)
        e = self._norm(expected)
        if not s:
            return False
        if s in e or e in s:
            return True
        return fuzz.ratio(s, e) >= self.verify_threshold
