"""Public cache invalidation API for tenant_host: apps (#1289 slice 6).

Most projects don't need this — the framework auto-busts on
``Repository.update`` of any slug field on a ``tenant_host:`` entity
(wired via `_register_slug_field` from app_factory; consulted from
`Repository.update` via `slug_field_for(table_name)`).

Use ``bust(slug)`` directly for the edge cases that bypass Repository:

    * raw-SQL renames
    * Alembic / migration fixups
    * admin CLI tools that mutate the DB out-of-band
"""

from __future__ import annotations

from collections.abc import Iterable

from dazzle.http.runtime.tenant.cache import TenantCache

_REGISTERED_CACHES: list[TenantCache] = []
_TENANT_HOST_SLUG_FIELDS: dict[str, str] = {}


def _register_cache(cache: TenantCache) -> None:
    """Called from app_factory when a TenantHostBinding is built."""
    _REGISTERED_CACHES.append(cache)


def _register_slug_field(table_name: str, slug_field: str) -> None:
    """Map a `tenant_host:` entity's table name to its slug field so
    `Repository.update` can auto-bust both old and new slug values when
    the slug column changes. Called from app_factory at mount time.
    """
    _TENANT_HOST_SLUG_FIELDS[table_name] = slug_field


def slug_field_for(table_name: str) -> str | None:
    """Return the slug field name for `table_name`, or None if the
    entity has no `tenant_host:` block."""
    return _TENANT_HOST_SLUG_FIELDS.get(table_name)


def _active_caches() -> Iterable[TenantCache]:
    return list(_REGISTERED_CACHES)


def _clear_registry() -> None:  # pragma: no cover - test hygiene only
    """Drop every registered cache + slug-field mapping. Tests use this
    to isolate state."""
    _REGISTERED_CACHES.clear()
    _TENANT_HOST_SLUG_FIELDS.clear()


def bust(slug: str) -> None:
    """Remove `slug` from every registered tenant cache."""
    for cache in _active_caches():
        cache.bust(slug)
