"""Shared HTTP retry utilities for httpx clients.

Provides ``retrying_request`` (sync) and ``async_retrying_request`` (async)
with exponential backoff on transient errors (timeouts, connection failures,
and HTTP 502/503/504 responses).
"""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_SECONDS = (1.0, 2.0, 4.0)

# HTTP status codes that indicate a transient server error worth retrying.
_TRANSIENT_STATUS_CODES = frozenset({502, 503, 504})

# Exception types (besides TimeoutException) that warrant a retry.
_TRANSIENT_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.RemoteProtocolError,
)


def _backoff_delay(attempt: int, backoff: tuple[float, ...]) -> float:
    """Return the backoff delay for the given zero-based *attempt*."""
    return backoff[attempt] if attempt < len(backoff) else backoff[-1]


def retrying_request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    max_retries: int = MAX_RETRIES,
    backoff: tuple[float, ...] = BACKOFF_SECONDS,
    **kwargs: Any,
) -> httpx.Response:
    """Sync HTTP request with retry on transient errors.

    Retries up to *max_retries* times with exponential backoff when a request
    fails with a timeout, connection error, remote protocol error, or a
    transient HTTP status code (502, 503, 504).
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = client.request(method, url, **kwargs)

            if response.status_code not in _TRANSIENT_STATUS_CODES:
                return response

            # Transient server error — log and maybe retry
            if attempt < max_retries:
                delay = _backoff_delay(attempt, backoff)
                logger.warning(
                    "HTTP %s %s returned %d (attempt %d/%d), retrying in %.1fs",
                    method,
                    url,
                    response.status_code,
                    attempt + 1,
                    max_retries + 1,
                    delay,
                )
                time.sleep(delay)
                continue

            return response

        except _TRANSIENT_EXCEPTIONS as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = _backoff_delay(attempt, backoff)
                logger.warning(
                    "HTTP %s %s failed with %s (attempt %d/%d), retrying in %.1fs",
                    method,
                    url,
                    exc,
                    attempt + 1,
                    max_retries + 1,
                    delay,
                )
                time.sleep(delay)
                continue

            raise

    # Should not be reached, but satisfies type checkers
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("retrying_request exhausted attempts without returning")


async def async_retrying_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int = MAX_RETRIES,
    backoff: tuple[float, ...] = BACKOFF_SECONDS,
    **kwargs: Any,
) -> httpx.Response:
    """Async HTTP request with retry on transient errors.

    Same semantics as ``retrying_request`` but for async clients.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await client.request(method, url, **kwargs)

            if response.status_code not in _TRANSIENT_STATUS_CODES:
                return response

            # Transient server error — log and maybe retry
            if attempt < max_retries:
                delay = _backoff_delay(attempt, backoff)
                logger.warning(
                    "HTTP %s %s returned %d (attempt %d/%d), retrying in %.1fs",
                    method,
                    url,
                    response.status_code,
                    attempt + 1,
                    max_retries + 1,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            return response

        except _TRANSIENT_EXCEPTIONS as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = _backoff_delay(attempt, backoff)
                logger.warning(
                    "HTTP %s %s failed with %s (attempt %d/%d), retrying in %.1fs",
                    method,
                    url,
                    exc,
                    attempt + 1,
                    max_retries + 1,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            raise

    # Should not be reached, but satisfies type checkers
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("async_retrying_request exhausted attempts without returning")
