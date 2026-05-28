"""Tenant lookup chain (#1289 slice 2).

`Resolver.lookup(slug)` walks the configured `tenant_host` entities in
lexical (or explicit `order:`) sequence and returns the first match. If
no entity matches and a `history_entity` is configured, the resolver
falls back to the history table to produce a 301 (active) or 410
(expired) signal.

The actual DB calls are delegated via `lookup_fn` and
`history_lookup_fn` callables so this module stays a pure-logic unit
testable without database fixtures.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ResolvedTenant:
    kind: str
    id: UUID
    slug: str
    name: str | None = None


@dataclass(frozen=True)
class HistoryHit:
    old_slug: str
    new_slug: str


@dataclass(frozen=True)
class ExpiredHistoryHit:
    old_slug: str
    new_slug: str


@dataclass(frozen=True)
class EntityProbe:
    """One step of the resolution chain — `(entity_name, slug_field)`."""

    entity_name: str
    slug_field: str


@dataclass(frozen=True)
class HistoryProbe:
    """Optional history-table probe — `(entity_name, old/new/expires fields)`."""

    entity_name: str
    old_slug_field: str = "old_slug"
    new_slug_field: str = "new_slug"
    expires_field: str = "expires_at"


LookupFn = Callable[[str, str], dict[str, Any] | None | Awaitable[dict[str, Any] | None]]
"""Signature: lookup_fn(entity_name, slug) -> row dict or None.

Accepts sync or async callables; the resolver awaits coroutines."""


HistoryLookupFn = Callable[[str, str], dict[str, Any] | None | Awaitable[dict[str, Any] | None]]
"""Signature: history_lookup_fn(entity_name, old_slug) -> row dict or None."""


class Resolver:
    """Stateless lookup chain over configured entity probes."""

    def __init__(
        self,
        probes: list[EntityProbe],
        history_probe: HistoryProbe | None,
        lookup_fn: LookupFn,
        history_lookup_fn: HistoryLookupFn | None = None,
        *,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._probes = probes
        self._history = history_probe
        self._lookup = lookup_fn
        self._history_lookup = history_lookup_fn
        self._now = now_fn

    async def lookup(self, slug: str) -> ResolvedTenant | HistoryHit | ExpiredHistoryHit | None:
        for probe in self._probes:
            row = await _maybe_await(self._lookup(probe.entity_name, slug))
            if row is None:
                continue
            return ResolvedTenant(
                kind=probe.entity_name,
                id=row["id"],
                slug=row[probe.slug_field],
                name=row.get("name"),
            )

        if self._history is None or self._history_lookup is None:
            return None

        h = await _maybe_await(self._history_lookup(self._history.entity_name, slug))
        if h is None:
            return None

        new_slug = h[self._history.new_slug_field]
        expires = h[self._history.expires_field]
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires)
        if expires > self._now():
            return HistoryHit(old_slug=slug, new_slug=new_slug)
        return ExpiredHistoryHit(old_slug=slug, new_slug=new_slug)


async def _maybe_await(value: Any) -> Any:
    """Await *value* iff it's a coroutine; return as-is otherwise."""
    if inspect.iscoroutine(value):
        return await value
    return value
