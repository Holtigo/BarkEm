"""
API module — FastAPI REST endpoints and webhook delivery.

The FastAPI application is exposed as ``barkem.api:app`` so operators
can run either ``python -m barkem.api`` (launches uvicorn with the
host/port from settings.yaml) or ``uvicorn barkem.api.app:app``.
"""

from barkem.api.app import app, create_app

__all__ = ["app", "create_app"]
