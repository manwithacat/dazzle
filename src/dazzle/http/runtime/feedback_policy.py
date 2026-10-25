"""Server-side policy for ``POST`` / ``GET /feedbackreports`` (#1854).

The feedback widget's create route is the generated one; this module is the
per-entity :class:`~dazzle.http.runtime.route_support.CreateInterceptor`
and :data:`~dazzle.http.runtime.route_support.ListFilterHook` that
``RouteGenerator`` threads into it for ``FeedbackReport`` when
``feedback_widget: enabled``:

* identity is stamped by the server (``reported_by`` = session email,
  ``persona`` = normalised first role); payload values are ignored;
* caps: ``description`` ≤ 4 000 chars; ``anchor`` + ``context`` +
  ``page_snapshot`` + ``console_errors`` ≤ 32 KB; ``screenshot_data`` ≤ 1.5 MB
  → 422 with a message;
* idempotency per draft-ietf-httpapi-idempotency-key-header: the key from the
  ``Idempotency-Key`` header (fallback: the ``idempotency_key`` body field) is
  stored; a replay returns the stored row with 200 and
  ``Idempotent-Replayed: true``; a unique-violation race is caught and
  answered the same way; a different payload under the same key → 422;
* a per-user rate limit, 30/min and 300/day in process memory → 429 with
  ``Retry-After`` (independent of the slowapi profile).

``GET /feedbackreports`` additionally accepts ``status`` as a comma list,
``since`` (ISO 8601 → ``created_at >=``); ``page_url`` / ``surface`` /
``review_session`` ride the generated bare-parameter filters.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from dazzle.core.strings import normalize_role

logger = logging.getLogger(__name__)

IDEMPOTENCY_HEADER = "Idempotency-Key"
#: Legacy header the create route has read since #693.
LEGACY_IDEMPOTENCY_HEADER = "X-Idempotency-Key"
REPLAYED_HEADER = "Idempotent-Replayed"

DESCRIPTION_MAX_CHARS = 4_000
CONTEXT_MAX_BYTES = 32 * 1024
SCREENSHOT_MAX_BYTES = int(1.5 * 1024 * 1024)
CONTEXT_FIELDS: tuple[str, ...] = ("anchor", "context", "page_snapshot", "console_errors")

#: Fields the server stamps from the session; payload values are ignored.
STAMPED_FIELDS: tuple[str, ...] = ("reported_by", "persona")

#: The user-authored fields that must match on a replay.
FINGERPRINT_FIELDS: tuple[str, ...] = (
    "description",
    "category",
    "severity",
    "page_url",
    "surface",
    "anchor",
)

RATE_PER_MINUTE = 30
RATE_PER_DAY = 300


def _encoded_size(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _canon(value: Any) -> str:
    """One comparable string for a scalar or a JSON value (dict / list / str)."""
    if value is None:
        return ""
    if isinstance(value, str):
        stripped = value.strip()
        # A stored json column may come back as a string; compare structurally.
        if stripped[:1] in ("{", "["):
            try:
                return json.dumps(json.loads(stripped), sort_keys=True, separators=(",", ":"))
            except ValueError:
                return stripped
        return stripped
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return str(value)


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    dump = getattr(row, "model_dump", None)
    if callable(dump):
        out = dump(mode="json")
        return dict(out) if isinstance(out, dict) else {}
    return {}


def _unprocessable(message: str, *, field_name: str | None = None) -> HTTPException:
    detail: dict[str, Any] = {"error": "feedback_report_rejected", "reason": message}
    if field_name:
        detail["field"] = field_name
    return HTTPException(status_code=422, detail=detail)


@dataclass
class FeedbackRateLimiter:
    """Per-key sliding windows, in process memory (#1854).

    ``check(key)`` returns ``None`` when the request may proceed (and records
    it), or the number of seconds to wait. Independent of the slowapi
    profile, so the limit holds on the ``basic`` profile too. One process,
    one limiter; multi-worker deployments get ``workers × limit``, which is
    the documented, accepted bound for a feedback endpoint.
    """

    per_minute: int = RATE_PER_MINUTE
    per_day: int = RATE_PER_DAY
    clock: Callable[[], float] = time.time
    _hits: dict[str, deque[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check(self, key: str) -> int | None:
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= 86_400:
                hits.popleft()
            if len(hits) >= self.per_day:
                return max(1, int(86_400 - (now - hits[0])) + 1)
            minute = [t for t in hits if now - t < 60]
            if len(minute) >= self.per_minute:
                return max(1, int(60 - (now - minute[0])) + 1)
            hits.append(now)
            # Keep the map from growing with one-off keys.
            if len(self._hits) > 10_000:
                for stale in [k for k, v in self._hits.items() if not v or now - v[-1] >= 86_400]:
                    del self._hits[stale]
            return None


_SHARED_LIMITER = FeedbackRateLimiter()


class FeedbackCreateInterceptor:
    """The ``POST /feedbackreports`` policy (see the module docstring).

    ``limiter`` defaults to the process-wide limiter so every mount of the
    route shares one budget per user.
    """

    def __init__(self, *, limiter: FeedbackRateLimiter | None = None) -> None:
        self.limiter = limiter or _SHARED_LIMITER

    # -- CreateInterceptor ---------------------------------------------------

    async def before_create(
        self,
        body: dict[str, Any],
        request: Request,
        *,
        service: Any,
        input_schema: Any,
        user_id: str | None,
        user_email: str | None,
        user_roles: list[str],
    ) -> JSONResponse | None:
        declared = set(getattr(input_schema, "model_fields", {}) or {})

        key = resolve_idempotency_key(request, body)
        if "idempotency_key" in declared:
            if key:
                body["idempotency_key"] = key
            else:
                body.pop("idempotency_key", None)

        stamp_identity(body, declared, user_email=user_email, user_roles=user_roles)
        enforce_caps(body)

        limit_key = (user_email or user_id or "").strip()
        if limit_key:
            wait = self.limiter.check(limit_key)
            if wait is not None:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "feedback_rate_limited",
                        "reason": f"Too many feedback reports; retry in {wait} s",
                    },
                    headers={"Retry-After": str(wait)},
                )

        if key and "idempotency_key" in declared:
            stored = await find_by_idempotency_key(service, key)
            if stored is not None:
                return replay_response(stored, body)
        return None

    async def on_constraint_violation(
        self,
        exc: Any,
        body: dict[str, Any],
        request: Request,
        *,
        service: Any,
    ) -> JSONResponse | None:
        key = body.get("idempotency_key")
        if not key or getattr(exc, "constraint_type", "") != "unique":
            return None
        field_name = getattr(exc, "field", None)
        if field_name not in (None, "idempotency_key"):
            return None
        stored = await find_by_idempotency_key(service, str(key))
        if stored is None:
            return None
        return replay_response(stored, body)


def resolve_idempotency_key(request: Request, body: dict[str, Any]) -> str | None:
    """The ``Idempotency-Key`` header, else the legacy header, else the body field."""
    headers = getattr(request, "headers", None) or {}
    for name in (IDEMPOTENCY_HEADER, LEGACY_IDEMPOTENCY_HEADER):
        value = headers.get(name) if hasattr(headers, "get") else None
        if value and str(value).strip():
            return str(value).strip()[:36]
    raw = body.get("idempotency_key")
    if raw is None:
        return None
    value = str(raw).strip()
    return value[:36] or None


def stamp_identity(
    body: dict[str, Any],
    declared: Iterable[str],
    *,
    user_email: str | None,
    user_roles: list[str] | None,
) -> None:
    """Overwrite ``reported_by`` / ``persona`` from the session (payload ignored)."""
    declared_set = set(declared)
    roles = [str(r) for r in (user_roles or []) if r]
    persona = normalize_role(roles[0]) if roles else None
    if "reported_by" in declared_set:
        body["reported_by"] = (user_email or "").strip() or None
    if "persona" in declared_set:
        body["persona"] = persona


def enforce_caps(body: dict[str, Any]) -> None:
    """422 when a text or context field exceeds its cap."""
    description = body.get("description")
    if isinstance(description, str) and len(description) > DESCRIPTION_MAX_CHARS:
        raise _unprocessable(
            f"description is {len(description)} characters; the limit is {DESCRIPTION_MAX_CHARS}",
            field_name="description",
        )
    context_size = sum(_encoded_size(body.get(name)) for name in CONTEXT_FIELDS)
    if context_size > CONTEXT_MAX_BYTES:
        raise _unprocessable(
            f"anchor, context, page_snapshot and console_errors total {context_size} bytes; "
            f"the limit is {CONTEXT_MAX_BYTES}",
            field_name="context",
        )
    shot = body.get("screenshot_data")
    if shot is not None and _encoded_size(shot) > SCREENSHOT_MAX_BYTES:
        raise _unprocessable(
            f"screenshot_data is {_encoded_size(shot)} bytes; the limit is {SCREENSHOT_MAX_BYTES}",
            field_name="screenshot_data",
        )


async def find_by_idempotency_key(service: Any, key: str) -> dict[str, Any] | None:
    """The stored row for ``key``, through the service's list operation."""
    try:
        page = await service.execute(
            operation="list", page=1, page_size=1, filters={"idempotency_key": key}
        )
    except Exception:  # the lookup must never turn a create into a 500
        logger.warning("feedback idempotency lookup failed for key %s", key, exc_info=True)
        return None
    items = page.get("items") if isinstance(page, dict) else None
    if not items:
        return None
    row = _row_dict(items[0])
    return row if str(row.get("idempotency_key") or "") == key else None


def replay_response(stored: dict[str, Any], body: dict[str, Any]) -> JSONResponse:
    """200 + ``Idempotent-Replayed: true`` for the same payload; 422 otherwise."""
    mismatched = [
        name
        for name in (*FINGERPRINT_FIELDS, *STAMPED_FIELDS)
        if name in body
        and body[name] is not None
        and _canon(body[name]) != _canon(stored.get(name))
    ]
    if mismatched:
        raise _unprocessable(
            "Idempotency-Key was already used with a different payload "
            f"(differs in {', '.join(mismatched)})",
            field_name="idempotency_key",
        )
    return JSONResponse(
        status_code=200,
        content=jsonable_encoder(stored),
        headers={REPLAYED_HEADER: "true"},
    )


# -- GET /feedbackreports -----------------------------------------------------

FEEDBACK_STATUSES: tuple[str, ...] = (
    "new",
    "triaged",
    "in_progress",
    "resolved",
    "verified",
    "wont_fix",
    "duplicate",
)


def parse_since(raw: str) -> datetime:
    """ISO 8601 (a trailing ``Z`` allowed); naive values are taken as UTC."""
    text = raw.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        value = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_since",
                "reason": f"since must be an ISO 8601 date or datetime; got {raw!r}",
            },
        ) from exc
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


def feedback_list_filters(query_params: Any, filters: dict[str, Any]) -> dict[str, Any]:
    """Add ``status`` (comma list) and ``since`` to the generated filters."""
    out = dict(filters)
    getter = getattr(query_params, "get", None)
    if getter is None:
        return out
    raw_status = getter("status")
    if raw_status and "," in str(raw_status):
        wanted = [s.strip() for s in str(raw_status).split(",") if s.strip()]
        valid = [s for s in wanted if s in FEEDBACK_STATUSES]
        out.pop("status", None)
        if valid:
            out["status__in"] = valid
    raw_since = getter("since")
    if raw_since and str(raw_since).strip():
        out["created_at__gte"] = parse_since(str(raw_since))
    return out
