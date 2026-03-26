"""Shared HTTP utilities for dazzle_back runtime.

Provides retry-with-backoff helpers for outbound HTTP calls via httpx.
"""

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Transient status codes that warrant a retry
_TRANSIENT_STATUS_CODES = {502, 503, 504}


async def http_call_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    **kwargs: Any,
) -> httpx.Response:
    """Make an HTTP request with exponential backoff retry on transient errors.

    Retries on connection errors and transient HTTP status codes (502, 503, 504).
    Does **not** retry on 4xx client errors.

    Args:
        client: An open ``httpx.AsyncClient`` to use for the request.
        method: HTTP method string (e.g. ``"GET"``, ``"POST"``).
        url: Full request URL.
        max_attempts: Maximum number of attempts (default 3).
        backoff_base: Base delay in seconds for exponential backoff (default 1.0).
            Delay for attempt *n* (0-indexed) is ``backoff_base * 2**n``.
        **kwargs: Additional keyword arguments forwarded to ``client.request()``.

    Returns:
        The final ``httpx.Response``.  Callers are responsible for checking the
        status code — this function does not raise on non-2xx responses.

    Raises:
        httpx.HTTPError: If all attempts are exhausted due to connection errors.
    """
    last_exc: Exception | None = None

    for attempt in range(max_attempts):
        try:
            response = await client.request(method, url, **kwargs)

            if response.status_code not in _TRANSIENT_STATUS_CODES:
                return response

            # Transient server error — log and maybe retry
            if attempt < max_attempts - 1:
                delay = backoff_base * (2**attempt)
                logger.warning(
                    "HTTP %s %s returned %d (attempt %d/%d), retrying in %.1fs",
                    method,
                    url,
                    response.status_code,
                    attempt + 1,
                    max_attempts,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            return response

        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = backoff_base * (2**attempt)
                logger.warning(
                    "HTTP %s %s failed with %s (attempt %d/%d), retrying in %.1fs",
                    method,
                    url,
                    exc,
                    attempt + 1,
                    max_attempts,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            raise

    # Should not be reached, but satisfies type checkers
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("http_call_with_retry exhausted attempts without returning")
