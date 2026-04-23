"""
Allow running the API server as: ``python -m barkem.api``

Uses host/port from ``settings.api`` (YAML / env-var overrides work
as everywhere else).  The log-level reuses ``settings.logging.level``
so a single switch controls both loguru and uvicorn verbosity.
"""

import uvicorn

from barkem.config import get_settings
from barkem.logging import configure_logging


def main() -> None:
    configure_logging()
    settings = get_settings()
    uvicorn.run(
        "barkem.api.app:app",
        host=settings.api.host,
        port=settings.api.port,
        log_level=settings.logging.level.lower(),
        access_log=False,
    )


if __name__ == "__main__":
    main()
