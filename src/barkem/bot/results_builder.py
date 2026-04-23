"""
Phase 7 — Map a Phase 6 ``ScoreboardResult`` + the original match
request into a webhook payload.

Fuzzy-matches OCR'd player names against the expected roster so the
webhook consumer gets both the canonical Embark ID and the raw OCR
text (auditable when a mismatch flagged by ``matched=False`` shows
up in telemetry).

Placement and ``winner`` are derived purely from ``total_score`` —
two teams, higher total wins, tie means no winner.  This matches the
existing ``MatchMonitor`` / ``ScoreboardReader`` pipeline — nothing
else needs to know about The Finals' win condition.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from rapidfuzz import fuzz

from barkem.api.schemas import (
    MatchModeConfig,
    Player,
    Team,
    WebhookPauseEvent,
    WebhookPayload,
    WebhookPlayerStats,
    WebhookResults,
    WebhookTeamResult,
    WebhookWinner,
)
from barkem.bot.pause_handler import PauseOutcome
from barkem.bot.scoreboard_reader import PlayerStats, ScoreboardResult, TeamScore


FUZZY_THRESHOLD = 70


def build_completed_payload(
    match_id: str,
    config: MatchModeConfig,
    teams: list[Team],
    scoreboard: ScoreboardResult,
    pauses: list[PauseOutcome],
    duration_seconds: float,
    metadata: dict,
) -> WebhookPayload:
    """Build the webhook body for a normally-completed match."""
    team1_req = _team_by_id(teams, 1)
    team2_req = _team_by_id(teams, 2)

    team1_result = _build_team_result(team1_req, scoreboard.team1)
    team2_result = _build_team_result(team2_req, scoreboard.team2)

    # Placement / winner from total_score (both required to decide).
    t1 = scoreboard.team1.total_score
    t2 = scoreboard.team2.total_score
    if t1 is not None and t2 is not None and t1 != t2:
        winner_team = team1_req if t1 > t2 else team2_req
        team1_result.placement = 1 if t1 > t2 else 2
        team2_result.placement = 2 if t1 > t2 else 1
        winner = WebhookWinner(team_id=winner_team.team_id, name=winner_team.name)
    else:
        team1_result.placement = 1
        team2_result.placement = 1
        winner = None

    return WebhookPayload(
        match_id=match_id,
        status="completed",
        completed_at=_now_iso(),
        duration_seconds=duration_seconds,
        config=config,
        results=WebhookResults(winner=winner, teams=[team1_result, team2_result]),
        pauses=[_map_pause(p) for p in pauses],
        metadata=metadata,
    )


def build_error_payload(
    match_id: str,
    config: MatchModeConfig,
    duration_seconds: float,
    error: str,
    status: str,
    metadata: dict,
    pauses: Optional[list[PauseOutcome]] = None,
) -> WebhookPayload:
    """Build the webhook body for a cancelled or errored match."""
    return WebhookPayload(
        match_id=match_id,
        status=status,  # type: ignore[arg-type]
        completed_at=_now_iso(),
        duration_seconds=duration_seconds,
        config=config,
        results=None,
        pauses=[_map_pause(p) for p in (pauses or [])],
        error=error,
        metadata=metadata,
    )


# ── Internals ────────────────────────────────────────────────────────


def _team_by_id(teams: list[Team], team_id: int) -> Team:
    for t in teams:
        if t.team_id == team_id:
            return t
    raise ValueError(f"No team with team_id={team_id}")


def _build_team_result(team_req: Team, team_score: TeamScore) -> WebhookTeamResult:
    players = [_match_player(team_req, ps) for ps in team_score.players]
    return WebhookTeamResult(
        team_id=team_req.team_id,
        name=team_req.name,
        placement=0,  # filled in by caller once winner is decided
        total_score=team_score.total_score,
        players=players,
    )


def _match_player(team_req: Team, stats: PlayerStats) -> WebhookPlayerStats:
    """Attach expected roster info by fuzzy-matching the OCR'd name."""
    matched_player = _fuzzy_find(team_req.players, stats.ocr_name)
    # ``class_`` is the field name; ``class`` is the alias used on the wire.
    return WebhookPlayerStats.model_validate({
        "embark_id": matched_player.embark_id if matched_player else None,
        "ocr_name": stats.ocr_name,
        "display_name": matched_player.display_name if matched_player else None,
        "matched": matched_player is not None,
        "class": stats.class_,
        "elims": stats.elims,
        "assists": stats.assists,
        "deaths": stats.deaths,
        "revives": stats.revives,
        "damage": stats.damage,
        "support": stats.support,
        "objective": stats.objective,
        "slot": stats.slot,
    })


def _fuzzy_find(roster: list[Player], ocr_name: str) -> Optional[Player]:
    if not ocr_name:
        return None
    target = _norm(ocr_name)
    best, best_score = None, 0
    for p in roster:
        candidate = _norm(p.embark_id)
        if not candidate:
            continue
        if target in candidate or candidate in target:
            return p
        score = fuzz.ratio(target, candidate)
        if score > best_score:
            best, best_score = p, score
    return best if best_score >= FUZZY_THRESHOLD else None


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def _map_pause(outcome: PauseOutcome) -> WebhookPauseEvent:
    return WebhookPauseEvent(
        team=outcome.team,
        captain=outcome.captain,
        duration_s=outcome.duration_s,
        timed_out=outcome.timed_out,
        reason=outcome.reason,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
