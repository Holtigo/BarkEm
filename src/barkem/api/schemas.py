"""
Pydantic request/response models for the Phase 7 REST API.

Mirrors §6 of the design report.  Only the match-policy knobs are
per-request — input timing (button delays, keyboard warmup, etc.)
stays in ``settings.yaml`` because it's a property of the bot VM's
local latency, not the match.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ── Request models ────────────────────────────────────────────────────


class Player(BaseModel):
    """One player in a team roster."""

    embark_id: str = Field(..., description="Embark ID including ``#NNNN`` tag.")
    discord_id: Optional[str] = None
    display_name: Optional[str] = None


class Team(BaseModel):
    """Team roster.  First player is the captain."""

    team_id: int = Field(..., ge=1, le=2)
    name: Optional[str] = None
    players: list[Player] = Field(..., min_length=1, max_length=3)

    @property
    def captain(self) -> Player:
        return self.players[0]


class MatchModeConfig(BaseModel):
    """Mode / map / variant selection for the lobby."""

    mode: str = Field(..., description="Mode key from settings.mode_map.modes")
    map: str = Field(..., description="Map key from settings.mode_map.maps")
    variant: str = "default"
    best_of: int = Field(1, ge=1, le=7)


class PauseOverrides(BaseModel):
    """Per-match pause limits.  Any unset field falls back to ``settings.pause``."""

    max_duration_s: Optional[float] = Field(None, gt=0)
    max_pauses_per_team: Optional[int] = Field(None, ge=0)
    cooldown_s: Optional[float] = Field(None, ge=0)


class StartMatchRequest(BaseModel):
    """``POST /api/v1/match/start`` body."""

    match_id: str = Field(..., min_length=1, max_length=128)
    config: MatchModeConfig
    teams: list[Team] = Field(..., min_length=2, max_length=2)
    webhook_url: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Match-policy knobs (all optional, fall through to ``settings`` defaults)
    cancel_timeout_seconds: Optional[int] = Field(None, ge=30)
    ready_timeout_seconds: Optional[int] = Field(None, ge=30)
    min_ready_captains: Optional[Literal[1, 2]] = None
    max_match_duration_s: Optional[float] = Field(None, gt=0)
    pause: Optional[PauseOverrides] = None

    @field_validator("teams")
    @classmethod
    def _distinct_team_ids(cls, v: list[Team]) -> list[Team]:
        ids = {t.team_id for t in v}
        if ids != {1, 2}:
            raise ValueError("teams must have team_id 1 and team_id 2 exactly once each")
        return v


# ── Response models ───────────────────────────────────────────────────


class Captains(BaseModel):
    team1: str
    team2: str


class StartMatchResponse(BaseModel):
    """Returned once the lobby exists and its code has been OCR'd."""

    status: Literal["accepted"] = "accepted"
    match_id: str
    lobby_code: str
    captains: Captains
    cancel_timeout_seconds: int


class MatchStatusResponse(BaseModel):
    """``GET /api/v1/match/{match_id}/status`` body."""

    match_id: str
    status: str
    current_state: str
    lobby_code: Optional[str] = None
    players_joined: int = 0
    players_expected: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class BotSlot(BaseModel):
    status: Literal["idle", "busy"]
    current_match: Optional[str] = None
    state: Optional[str] = None


class BotStatusResponse(BaseModel):
    """``GET /api/v1/status`` body."""

    orchestrator: BotSlot
    uptime_seconds: int
    version: str


class CancelResponse(BaseModel):
    match_id: str
    status: Literal["cancelled", "not_found", "already_finished"]


# ── Webhook payload (sent TO ``webhook_url``) ────────────────────────


class WebhookPlayerStats(BaseModel):
    """Per-player statline dispatched to the webhook.

    Field set matches ``barkem.bot.scoreboard_reader.PlayerStats`` 1:1 —
    every stat the Phase 6 reader produces is passed through.  There is
    no derived ``score`` field; consumers compute whatever weighted
    total they want from the raw stats.
    """

    embark_id: Optional[str] = None
    ocr_name: str = ""
    display_name: Optional[str] = None
    matched: bool
    class_: Optional[str] = Field(None, alias="class")
    elims: Optional[int] = None
    assists: Optional[int] = None
    deaths: Optional[int] = None
    revives: Optional[int] = None
    damage: Optional[int] = None
    support: Optional[int] = None
    objective: Optional[int] = None
    slot: str

    model_config = {"populate_by_name": True}


class WebhookTeamResult(BaseModel):
    team_id: int
    name: Optional[str] = None
    placement: int
    total_score: Optional[int] = None
    players: list[WebhookPlayerStats]


class WebhookWinner(BaseModel):
    team_id: int
    name: Optional[str] = None


class WebhookPauseEvent(BaseModel):
    team: Optional[str] = None
    captain: Optional[str] = None
    duration_s: float
    timed_out: bool = False
    reason: Optional[str] = None


class WebhookResults(BaseModel):
    winner: Optional[WebhookWinner] = None
    teams: list[WebhookTeamResult]


class WebhookPayload(BaseModel):
    match_id: str
    status: Literal["completed", "cancelled", "error"]
    completed_at: str
    duration_seconds: float
    config: MatchModeConfig
    results: Optional[WebhookResults] = None
    pauses: list[WebhookPauseEvent] = Field(default_factory=list)
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
