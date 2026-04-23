"""
Webhook delivery for match-result payloads.

Uses httpx for the HTTP call and tenacity for exponential backoff.
The target URL is optional — if the match request didn't include a
``webhook_url``, delivery is a no-op.  Failures never raise into the
orchestrator; they're logged and swallowed so a flaky consumer can't
wedge the bot.
"""

from __future__ import annotations

from typing import Optional

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from barkem.api.schemas import WebhookPayload
from barkem.config import get_settings
from barkem.logging import get_logger


log = get_logger("webhook")


async def deliver(url: Optional[str], payload: WebhookPayload) -> bool:
    """POST ``payload`` to ``url`` with retries.  Returns True on 2xx."""
    if not url:
        log.info("no webhook_url — skipping delivery for match {}", payload.match_id)
        return False

    settings = get_settings()
    timeout = settings.api.webhook_timeout
    attempts = max(1, settings.api.webhook_retries)
    body = payload.model_dump(by_alias=True, mode="json")

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            retry=retry_if_exception_type((httpx.HTTPError,)),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, json=body)
                response.raise_for_status()
                log.info(
                    "webhook delivered for match {} — status={}",
                    payload.match_id,
                    response.status_code,
                )
                return True
    except (httpx.HTTPError, RetryError) as exc:
        log.error(
            "webhook delivery failed for match {} after {} attempts: {}",
            payload.match_id,
            attempts,
            exc,
        )
    return False
