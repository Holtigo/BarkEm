"""
End-of-match scoreboard OCR.

Reads the final two-team scoreboard into a structured result.  Layout
is defined per-resolution in ``config/settings.yaml`` under
``regions.scoreboard`` as:

  * team1_score / team2_score — team money totals (existing)
  * team1_rows / team2_rows — 3 y-spans per team for the player rows
  * columns — shared x-spans for the class, name, and 7 stat columns

The reader crosses each row with each column to produce a cell
region, OCRs it, and assembles a :class:`PlayerStats` per player.

A leading ``[CLAN]`` tag on the OCR'd name is stripped so the caller
sees just ``Embark ID#0000``.

This runs after the SUMMARY screen has been skipped by the match
monitor — it's OCR-only and drives no input.
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from barkem.vision.ocr import TextReader
from barkem.vision.regions import (
    SCOREBOARD_STAT_COLUMNS,
    Region,
    ScoreboardRegions,
)


@dataclass
class PlayerStats:
    """Per-player statline read from the final scoreboard."""

    slot: str                                # "team1_player1", etc.
    ocr_name: str = ""                       # raw OCR (with discriminator)
    matched_embark_id: Optional[str] = None  # filled by caller if roster known
    class_: Optional[str] = None             # "L" | "M" | "H"
    elims: Optional[int] = None
    assists: Optional[int] = None
    deaths: Optional[int] = None
    revives: Optional[int] = None
    damage: Optional[int] = None
    support: Optional[int] = None
    objective: Optional[int] = None


@dataclass
class TeamScore:
    team_id: int
    total_score: Optional[int] = None
    players: list[PlayerStats] = field(default_factory=list)


@dataclass
class ScoreboardResult:
    team1: TeamScore
    team2: TeamScore
    winner_team_id: Optional[int] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


class ScoreboardReader:
    """
    OCR the end-of-match scoreboard into a ScoreboardResult.

    Usage:
        reader = ScoreboardReader(ocr=text_reader, regions=regions.scoreboard)
        result = reader.read(frame)
    """

    def __init__(self, ocr: TextReader, regions: ScoreboardRegions):
        self.ocr = ocr
        self.regions = regions

    def read(self, frame: np.ndarray) -> ScoreboardResult:
        team1 = self._read_team(frame, team_id=1)
        team2 = self._read_team(frame, team_id=2)
        return ScoreboardResult(
            team1=team1,
            team2=team2,
            winner_team_id=_winner(team1.total_score, team2.total_score),
        )

    # ── Team-level ────────────────────────────────────────────────────
    def _read_team(self, frame: np.ndarray, team_id: int) -> TeamScore:
        score_region: Region = getattr(self.regions, f"team{team_id}_score")
        total = self._read_total(frame, score_region)
        players = [
            self._read_player(frame, team_id, row_idx)
            for row_idx in range(3)
        ]
        return TeamScore(team_id=team_id, total_score=total, players=players)

    def _read_total(self, frame: np.ndarray, region: Region) -> Optional[int]:
        if region.is_zero:
            return None
        return self.ocr.read_score(_roi(frame, region))

    # ── Player-level ──────────────────────────────────────────────────
    def _read_player(
        self,
        frame: np.ndarray,
        team_id: int,
        row_idx: int,
    ) -> PlayerStats:
        slot = f"team{team_id}_player{row_idx + 1}"
        stats = PlayerStats(slot=slot)

        if self.regions.row(team_id, row_idx).is_zero:
            return stats

        stats.class_ = self._read_class(frame, team_id, row_idx)
        stats.ocr_name = self._read_name(frame, team_id, row_idx)
        for col in SCOREBOARD_STAT_COLUMNS:
            setattr(stats, col, self._read_stat(frame, team_id, row_idx, col))
        return stats

    def _read_class(self, frame: np.ndarray, team_id: int, row_idx: int) -> Optional[str]:
        cell = self.regions.cell(team_id, row_idx, "class")
        if cell.is_zero:
            return None
        return self.ocr.read_class_glyph(_roi(frame, cell))

    def _read_name(self, frame: np.ndarray, team_id: int, row_idx: int) -> str:
        cell = self.regions.cell(team_id, row_idx, "name")
        if cell.is_zero:
            return ""
        raw = self.ocr.read_player_name_on_tile(_roi(frame, cell))
        return _strip_leading_tag(raw)

    def _read_stat(
        self,
        frame: np.ndarray,
        team_id: int,
        row_idx: int,
        col_name: str,
    ) -> Optional[int]:
        cell = self.regions.cell(team_id, row_idx, col_name)
        if cell.is_zero:
            return None
        return self.ocr.read_int(_roi(frame, cell))


# ── Module helpers ────────────────────────────────────────────────────

def _roi(frame: np.ndarray, region: Region) -> np.ndarray:
    return frame[region.y1:region.y2, region.x1:region.x2]


def _winner(t1: Optional[int], t2: Optional[int]) -> Optional[int]:
    if t1 is None or t2 is None:
        return None
    if t1 > t2:
        return 1
    if t2 > t1:
        return 2
    return None


_TAG_BRACKETS = {"[": "]", "(": ")", "<": ">", "{": "}"}


def _strip_leading_tag(name: str) -> str:
    """
    Strip a leading ``[CLAN]`` / ``(CLAN)`` / ``<CLAN>`` tag from an
    OCR'd scoreboard name so the caller sees just the Embark ID.

    The Finals' scoreboard renders players with their optional clan
    tag before the name: ``[CLAN] playername#0000``.  This is the
    same pattern the chat reader handles — kept here as a local
    helper rather than cross-importing, since the rule is tiny.
    """
    stripped = name.lstrip()
    if not stripped:
        return name
    opener = stripped[0]
    closer = _TAG_BRACKETS.get(opener)
    if closer is None:
        return stripped
    end = stripped.find(closer)
    if 0 < end < 40:   # sanity cap — a real tag is short
        return stripped[end + 1:].lstrip()
    return stripped
