"""
Phase 7 — Replace the "press Enter when everyone has joined" manual
gate from ``create_and_place`` / ``start_match --full`` with an
automatic poll.

``RosterWaiter.wait()`` snapshots the lobby at a fixed interval via
``LobbyReader.read_snapshot`` and returns once every expected Embark
ID shows up in the unassigned list (fuzzy-matched against OCR noise),
or times out.

OCR on the unassigned list is cheap and the lobby is a static screen,
so polling every ~2s is fine — the expected gap between the first
player joining and the last one is measured in minutes (players copy
the code into the game), so we don't need sub-second polling here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from barkem.vision.capture import ScreenCapture
from barkem.vision.lobby_reader import LobbyReader, LobbySnapshot


@dataclass
class RosterWaitResult:
    ready: bool
    snapshot: Optional[LobbySnapshot] = None
    matched: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    elapsed_s: float = 0.0
    timed_out: bool = False
    error: Optional[str] = None


class RosterWaiter:
    """Poll the lobby until every expected Embark ID is unassigned."""

    def __init__(
        self,
        lobby_reader: LobbyReader,
        capture: ScreenCapture,
        poll_interval_s: float = 2.0,
        fuzzy_threshold: int = 75,
    ):
        self.reader = lobby_reader
        self.cap = capture
        self.poll_interval_s = poll_interval_s
        self.fuzzy_threshold = fuzzy_threshold

    def wait(
        self,
        expected_embark_ids: list[str],
        timeout_s: float,
        on_progress=None,
    ) -> RosterWaitResult:
        """Block until every expected player is unassigned, or timeout.

        Args:
            expected_embark_ids: All 6 player IDs (bot excluded — it's
                in the unassigned list too, but we only match real
                players against expected IDs).
            timeout_s: Hard upper bound (maps to ``cancel_timeout_seconds``).
            on_progress: Optional callable (matched: list[str], missing:
                list[str]) invoked once per poll for live logging.
        """
        start = time.monotonic()
        deadline = start + timeout_s
        last_snapshot: Optional[LobbySnapshot] = None

        while True:
            snapshot = self._snapshot()
            if snapshot is not None:
                last_snapshot = snapshot
                matched, missing = self._classify(snapshot, expected_embark_ids)
                if on_progress is not None:
                    on_progress(matched, missing)
                if not missing:
                    return RosterWaitResult(
                        ready=True,
                        snapshot=snapshot,
                        matched=matched,
                        missing=[],
                        elapsed_s=time.monotonic() - start,
                    )

            if time.monotonic() >= deadline:
                matched, missing = (
                    self._classify(last_snapshot, expected_embark_ids)
                    if last_snapshot is not None
                    else ([], list(expected_embark_ids))
                )
                return RosterWaitResult(
                    ready=False,
                    snapshot=last_snapshot,
                    matched=matched,
                    missing=missing,
                    elapsed_s=time.monotonic() - start,
                    timed_out=True,
                    error=(
                        f"Only {len(matched)}/{len(expected_embark_ids)} "
                        f"expected players joined within {timeout_s:.0f}s"
                    ),
                )

            time.sleep(self.poll_interval_s)

    # ── Internals ───────────────────────────────────────────────────

    def _snapshot(self) -> Optional[LobbySnapshot]:
        frame = self.cap.grab()
        if frame is None:
            return None
        return self.reader.read_snapshot(frame)

    def _classify(
        self,
        snapshot: LobbySnapshot,
        expected: list[str],
    ) -> tuple[list[str], list[str]]:
        matched: list[str] = []
        missing: list[str] = []
        for pid in expected:
            idx = snapshot.index_of(pid, self.fuzzy_threshold)
            if idx is not None:
                matched.append(pid)
            else:
                missing.append(pid)
        return matched, missing
