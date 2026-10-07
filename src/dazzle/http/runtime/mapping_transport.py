"""Application send hook for an integration marked ``transport: app`` (#1769).

The executor renders the request and calls this hook instead of ``httpx``.
The application adds per-request headers, picks the host, and attaches the
caller token. The executor still owns the cache, the response mapping, and
``on_error``.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

logger = logging.getLogger(__name__)

# Same transient statuses as ``dazzle.core.http_client``. A retryable mapping
# calls the hook again only for these, and for an exception the hook raises.
_TRANSIENT_STATUS_CODES = frozenset({502, 503, 504})

_HOOK_MODULE = "pipeline.serve.app_init"
_HOOK_NAME = "integration_transport"


@dataclass(frozen=True)
class AppTransportRequest:
    """The rendered request handed to the application hook.

    ``headers`` are the static headers the mapping declared. Authorization
    and Content-Type are not added: the application attaches those.
    ``path`` is the interpolated URL template, not joined to ``base_url``.
    """

    method: str
    path: str
    base_url: str
    headers: dict[str, str]
    body: dict[str, Any]
    integration: str
    mapping: str


class HookResponse:
    """The slice of an HTTP response the executor reads after a hook call."""

    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body
        if isinstance(body, str):
            self.text = body
        else:
            try:
                self.text = json.dumps(body)
            except TypeError:
                self.text = str(body)

    def json(self) -> Any:
        if isinstance(self._body, (dict, list)):
            return self._body
        raise ValueError("app transport body is not JSON")


def load_project_transport() -> Callable[..., Any] | None:
    """Return ``pipeline.serve.app_init.integration_transport``, or None.

    A missing module or a missing callable is a None. The caller turns that
    into an error at send time and does not open a socket.
    """
    import importlib

    try:
        module = importlib.import_module(_HOOK_MODULE)
    except ModuleNotFoundError:
        return None
    hook = getattr(module, _HOOK_NAME, None)
    if hook is None:
        return None
    if not callable(hook):
        logger.warning("%s.%s is not callable", _HOOK_MODULE, _HOOK_NAME)
        return None
    return cast(Callable[..., Any], hook)


async def invoke_app_transport(
    hook: Callable[..., Any],
    request: AppTransportRequest,
    *,
    max_attempts: int,
    backoff: tuple[float, ...],
    on_attempt: Callable[..., Awaitable[None]] | None = None,
) -> HookResponse:
    """Call ``hook`` until it returns a final status or the attempts run out.

    ``on_error: retry`` is ``max_attempts`` greater than 1. A transient status
    or a raised exception calls the hook again after ``backoff``. A bad return
    shape is a ``TypeError`` and is not retried.
    """
    for attempt in range(max_attempts):
        try:
            outcome = hook(request)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            status, payload = _unpack(outcome)
        except TypeError:
            raise
        except Exception as exc:
            if attempt < max_attempts - 1:
                delay = _delay(backoff, attempt)
                await _notify(on_attempt, attempt + 1, max_attempts, None, str(exc), delay)
                await asyncio.sleep(delay)
                continue
            await _notify(on_attempt, attempt + 1, max_attempts, None, str(exc), None)
            raise

        if status not in _TRANSIENT_STATUS_CODES or attempt == max_attempts - 1:
            await _notify(on_attempt, attempt + 1, max_attempts, status, None, None)
            return HookResponse(status, payload)

        delay = _delay(backoff, attempt)
        await _notify(on_attempt, attempt + 1, max_attempts, status, None, delay)
        await asyncio.sleep(delay)

    raise RuntimeError("app transport exhausted attempts without returning")


def _unpack(outcome: Any) -> tuple[int, Any]:
    if (
        not isinstance(outcome, tuple)
        or len(outcome) != 2
        or isinstance(outcome[0], bool)
        or not isinstance(outcome[0], int)
    ):
        raise TypeError(
            f"integration_transport must return (status: int, body), got {type(outcome).__name__}"
        )
    return outcome


def _delay(backoff: tuple[float, ...], attempt: int) -> float:
    if not backoff:
        return 0.0
    if attempt < len(backoff):
        return backoff[attempt]
    return backoff[-1]


async def _notify(
    callback: Callable[..., Awaitable[None]] | None,
    attempt: int,
    max_attempts: int,
    status_code: int | None,
    error: str | None,
    next_backoff: float | None,
) -> None:
    if callback is None:
        return
    try:
        await callback(attempt, max_attempts, status_code, error, next_backoff)
    except Exception:
        logger.warning("app transport on_attempt failed", exc_info=True)
