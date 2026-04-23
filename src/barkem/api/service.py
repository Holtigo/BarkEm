"""
Process-wide service layer that owns the single orchestrator instance.

BarkEm's current design is one bot per process — the private-match
lobby is physically held by one XInput controller, so there can only
ever be one in-flight match.  This module enforces that: a second
``POST /match/start`` while a run is active returns 409.

Later (Phase 8 coordinator) the "one bot per process" assumption
stays — multiple bots == multiple processes, one per GeForce NOW VM.
The coordinator service fans requests out; each bot still runs one
match at a time locally.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

from barkem.bot.match_orchestrator import (
    MatchOrchestrator,
    MatchRun,
    OrchestratorPhase,
    OrchestratorRuntime,
    build_runtime,
    shutdown_runtime,
)
from barkem.config import get_settings
from barkem.logging import configure_logging, get_logger


log = get_logger("service")


class BotService:
    """Singleton wrapping runtime + orchestrator + the active run task."""

    def __init__(self) -> None:
        configure_logging()
        self._runtime: Optional[OrchestratorRuntime] = None
        self._orchestrator: Optional[MatchOrchestrator] = None
        self._background: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._started_at = time.time()

    # ── Lifecycle ──────────────────────────────────────────────────

    async def startup(self) -> None:
        """Build the input/vision stack.  Called from FastAPI startup."""
        if self._runtime is not None:
            return
        log.info("building orchestrator runtime")
        loop = asyncio.get_running_loop()
        # Construction touches the capture thread + virtual controller
        # — both are blocking.  Run off-loop so FastAPI startup stays
        # responsive.
        self._runtime = await loop.run_in_executor(None, build_runtime)
        self._orchestrator = MatchOrchestrator(self._runtime, settings=get_settings())
        log.info("runtime ready")

    async def shutdown(self) -> None:
        """Release hardware resources.  Called from FastAPI shutdown."""
        if self._background is not None and not self._background.done():
            self._background.cancel()
        if self._runtime is not None:
            log.info("shutting down runtime")
            shutdown_runtime(self._runtime)
            self._runtime = None
            self._orchestrator = None

    # ── Accessors ──────────────────────────────────────────────────

    @property
    def orchestrator(self) -> MatchOrchestrator:
        if self._orchestrator is None:
            raise RuntimeError("Service not started — orchestrator is not initialised.")
        return self._orchestrator

    @property
    def started_at(self) -> float:
        return self._started_at

    # ── Match dispatch ─────────────────────────────────────────────

    async def start_match(self, request) -> MatchRun:
        """Prepare a match synchronously (blocking on lobby creation),
        then schedule the rest of the pipeline on a background task."""
        async with self._lock:
            orch = self.orchestrator
            if orch.is_busy():
                raise BotBusyError("Bot is already running a match.")
            run = await orch.prepare_match(request)

            # Schedule the rest of the pipeline independently so we can
            # return the lobby code to the client now.
            self._background = asyncio.create_task(
                orch.run_remaining_phases(),
                name=f"match-{request.match_id}",
            )
            return run

    def cancel(self, match_id: str) -> str:
        """Request cancellation.  Returns ``cancelled``, ``not_found`` or ``already_finished``."""
        orch = self.orchestrator
        run = orch.current
        if run is None or run.match_id != match_id:
            return "not_found"
        if run.phase in (
            OrchestratorPhase.COMPLETED,
            OrchestratorPhase.CANCELLED,
            OrchestratorPhase.ERROR,
        ):
            return "already_finished"
        orch.request_cancel()
        return "cancelled"


class BotBusyError(RuntimeError):
    """Raised when a second /match/start arrives while one is active."""


# Module-level singleton.  FastAPI dependencies pull from this.
service = BotService()
