"""
Structured logging setup for the Phase 7 API + orchestrator.

Uses loguru with two sinks:
  * stdout (colourised, human-readable, matches the tool output shape)
  * rotating file at ``settings.logging.file``

``configure_logging()`` is idempotent — calling it twice (e.g. once
from the API startup hook and once from a re-imported orchestrator)
won't register duplicate sinks.

Only Phase 7 code (the API layer and the match orchestrator) routes
through this logger.  The existing bot classes (MatchMonitor,
MatchStarter, PauseHandler, TeamPlacer, LobbyCreator) keep their
``print(..., flush=True)`` + ``verbose=True`` pattern untouched — that
change is out of Phase 7's scope.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from barkem.config import get_settings


_CONFIGURED = False


def configure_logging() -> None:
    """Initialise loguru sinks from ``settings.logging``.  Safe to call twice."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    log_cfg = settings.logging

    logger.remove()
    logger.add(
        sys.stdout,
        level=log_cfg.level,
        format=(
            "<green>{time:HH:mm:ss}</green> "
            "<level>{level:<7}</level> "
            "<cyan>{extra[component]}</cyan> "
            "{message}"
        ),
        colorize=True,
        enqueue=False,
    )

    log_path = Path(log_cfg.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_path),
        level=log_cfg.level,
        rotation=log_cfg.rotation,
        retention=log_cfg.retention,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} {level:<7} "
            "{extra[component]} {message}"
        ),
        enqueue=True,
    )

    logger.configure(extra={"component": "barkem"})
    _CONFIGURED = True


def get_logger(component: str):
    """Return a loguru logger bound to ``component`` (e.g. ``"api"``, ``"orchestrator"``)."""
    if not _CONFIGURED:
        configure_logging()
    return logger.bind(component=component)
