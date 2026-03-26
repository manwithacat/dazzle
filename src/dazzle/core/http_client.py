"""Shared HTTP retry utilities for httpx clients.

Provides ``retrying_request`` (sync) and ``async_retrying_request`` (async)
with exponential backoff on timeout errors.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_SECONDS = (1.0, 2.0, 4.0)


def retrying_request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_retries: int = MAX_RETRIES,
    backoff: tuple[float, ...] = BACKOFF_SECONDS,
    **kwargs: Any,
) -> httpx.Response:
    """Sync HTTP request with retry on timeout.

    Retries up to *max_retries* times with exponential backoff when a request
    times out. Non-timeout errors are raised immediately.
    """
    last_exc: httpx.TimeoutException | None = None
    for attempt in range(max_retries + 1):
        try:
            return client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = backoff[attempt] if attempt < len(backoff) else backoff[-1]
                logger.debug(
                    "Timeout on %s %s (attempt %d/%d), retrying in %.1fs",
                    method,
                    url,
                    attempt + 1,
                    max_retries + 1,
                    delay,
                )
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


async def async_retrying_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int = MAX_RETRIES,
    backoff: tuple[float, ...] = BACKOFF_SECONDS,
    **kwargs: Any,
) -> httpx.Response:
    """Async HTTP request with retry on timeout.

    Same semantics as ``retrying_request`` but for async clients.
    """
    last_exc: httpx.TimeoutException | None = None
    for attempt in range(max_retries + 1):
        try:
            return await client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = backoff[attempt] if attempt < len(backoff) else backoff[-1]
                logger.debug(
                    "Timeout on %s %s (attempt %d/%d), retrying in %.1fs",
                    method,
                    url,
                    attempt + 1,
                    max_retries + 1,
                    delay,
                )
                await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]
