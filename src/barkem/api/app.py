"""
FastAPI app wiring the Phase 7 REST surface onto ``BotService``.

Endpoints (§6 of the design report):

  POST /api/v1/match/start              → start a match, block until lobby code
  GET  /api/v1/match/{match_id}/status  → live phase + roster progress
  POST /api/v1/match/{match_id}/cancel  → request cancellation
  GET  /api/v1/status                   → bot + uptime

WebSocket / state-stream (§6.3) is deferred — the status endpoint
already exposes everything the coordinator (Phase 8) needs to poll.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, status

from barkem.api.schemas import (
    BotSlot,
    BotStatusResponse,
    Captains,
    CancelResponse,
    MatchStatusResponse,
    StartMatchRequest,
    StartMatchResponse,
)
from barkem.api.service import BotBusyError, service
from barkem.bot.match_orchestrator import OrchestratorPhase
from barkem.logging import configure_logging, get_logger


log = get_logger("api")


def create_app() -> FastAPI:
    app = FastAPI(
        title="BarkEm",
        description="Private-match automation for The Finals.",
        version="0.1.0",
    )

    @app.on_event("startup")
    async def _on_startup() -> None:
        configure_logging()
        log.info("starting up")
        await service.startup()

    @app.on_event("shutdown")
    async def _on_shutdown() -> None:
        log.info("shutting down")
        await service.shutdown()

    @app.post(
        "/api/v1/match/start",
        response_model=StartMatchResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_match(request: StartMatchRequest) -> StartMatchResponse:
        log.info("POST /match/start  match_id={}", request.match_id)
        try:
            run = await service.start_match(request)
        except BotBusyError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

        if not run.lobby_code:
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Lobby was created but code OCR failed.",
            )

        captains_by_id = {t.team_id: t.captain.embark_id for t in run.teams}
        return StartMatchResponse(
            match_id=run.match_id,
            lobby_code=run.lobby_code,
            captains=Captains(team1=captains_by_id[1], team2=captains_by_id[2]),
            cancel_timeout_seconds=int(run.cancel_timeout_s),
        )

    @app.get(
        "/api/v1/match/{match_id}/status",
        response_model=MatchStatusResponse,
    )
    async def get_status(match_id: str) -> MatchStatusResponse:
        run = service.orchestrator.current
        if run is None or run.match_id != match_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No match with that id.")

        return MatchStatusResponse(
            match_id=run.match_id,
            status=_external_status(run.phase),
            current_state=run.phase.value,
            lobby_code=run.lobby_code,
            players_joined=run.players_joined,
            players_expected=run.players_expected,
            started_at=_iso(run.started_at),
            completed_at=_iso(run.completed_at),
            error=run.error,
        )

    @app.post(
        "/api/v1/match/{match_id}/cancel",
        response_model=CancelResponse,
    )
    async def cancel_match(match_id: str) -> CancelResponse:
        log.info("POST /match/{}/cancel", match_id)
        result = service.cancel(match_id)
        return CancelResponse(match_id=match_id, status=result)  # type: ignore[arg-type]

    @app.get("/api/v1/status", response_model=BotStatusResponse)
    async def bot_status() -> BotStatusResponse:
        run = service.orchestrator.current
        slot = BotSlot(status="idle", current_match=None, state=None)
        if run is not None and service.orchestrator.is_busy():
            slot = BotSlot(
                status="busy",
                current_match=run.match_id,
                state=run.phase.value,
            )
        uptime = int(time.time() - service.started_at)
        return BotStatusResponse(
            orchestrator=slot,
            uptime_seconds=uptime,
            version=app.version,
        )

    return app


# Module-level for ``uvicorn barkem.api.app:app``
app = create_app()


# ── Helpers ─────────────────────────────────────────────────────────


def _iso(t: float | None) -> str | None:
    if t is None:
        return None
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat().replace("+00:00", "Z")


_EXTERNAL_STATUS = {
    OrchestratorPhase.IDLE: "pending",
    OrchestratorPhase.FOCUSING_WINDOW: "pending",
    OrchestratorPhase.CREATING_LOBBY: "pending",
    OrchestratorPhase.WAITING_FOR_PLAYERS: "waiting_for_players",
    OrchestratorPhase.PLACING_TEAMS: "placing_teams",
    OrchestratorPhase.WAITING_FOR_READY: "waiting_for_ready",
    OrchestratorPhase.MONITORING_MATCH: "in_progress",
    OrchestratorPhase.CAPTURING_SCORE: "in_progress",
    OrchestratorPhase.DELIVERING_RESULTS: "in_progress",
    OrchestratorPhase.COMPLETED: "completed",
    OrchestratorPhase.CANCELLED: "cancelled",
    OrchestratorPhase.ERROR: "error",
}


def _external_status(phase: OrchestratorPhase) -> str:
    return _EXTERNAL_STATUS.get(phase, "pending")
