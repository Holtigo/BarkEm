"""
End-of-match scoreboard OCR.

Reads the final two-team scoreboard into a structured result.  Regions
are defined per-resolution in ``config/settings.yaml`` under
``regions.scoreboard`` — team scores, team names, and six player
slots (3 per team) each with a name + value region.

This runs after the SUMMARY screen has been skipped (by the match
monitor).  It's OCR-only — it does not drive any input.
"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from barkem.vision.ocr import TextReader
from barkem.vision.regions import ScoreboardRegions


@dataclass
class PlayerScore:
    slot: str               # "team1_player1", etc.
    ocr_name: str           # raw OCR'd name (before fuzzy match)
    matched_embark_id: Optional[str] = None  # filled in by caller if rosters known
    score: Optional[int] = None


@dataclass
class TeamScore:
    team_id: int
    team_name: str = ""
    total_score: Optional[int] = None
    players: list[PlayerScore] = field(default_factory=list)


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

    def __init__(
        self,
        ocr: TextReader,
        regions: ScoreboardRegions,
    ):
        self.ocr = ocr
        self.regions = regions

    def read(self, frame: np.ndarray) -> ScoreboardResult:
        team1 = self._read_team(frame, team_id=1)
        team2 = self._read_team(frame, team_id=2)

        winner = None
        if team1.total_score is not None and team2.total_score is not None:
            if team1.total_score > team2.total_score:
                winner = 1
            elif team2.total_score > team1.total_score:
                winner = 2
            # tie → winner stays None

        return ScoreboardResult(team1=team1, team2=team2, winner_team_id=winner)

    def _read_team(self, frame: np.ndarray, team_id: int) -> TeamScore:
        score_region = getattr(self.regions, f"team{team_id}_score")
        name_region = getattr(self.regions, f"team{team_id}_name")

        team_name = ""
        if not name_region.is_zero:
            team_name = self.ocr.read_region(frame, name_region.as_tuple(), psm=7)

        total_score: Optional[int] = None
        if not score_region.is_zero:
            total_score = self._read_score_region(frame, score_region.as_tuple())

        players: list[PlayerScore] = []
        for label, name_r, value_r in self.regions.team_player_slots(team_id):
            if name_r.is_zero and value_r.is_zero:
                continue
            p_name = (
                self.ocr.read_region(frame, name_r.as_tuple(), psm=7)
                if not name_r.is_zero else ""
            )
            p_score = (
                self._read_score_region(frame, value_r.as_tuple())
                if not value_r.is_zero else None
            )
            players.append(PlayerScore(slot=label, ocr_name=p_name, score=p_score))

        return TeamScore(
            team_id=team_id,
            team_name=team_name,
            total_score=total_score,
            players=players,
        )

    def _read_score_region(
        self, frame: np.ndarray, region: tuple[int, int, int, int]
    ) -> Optional[int]:
        x1, y1, x2, y2 = region
        roi = frame[y1:y2, x1:x2]
        return self.ocr.read_score(roi)
