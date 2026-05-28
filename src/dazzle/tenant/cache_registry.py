"""Public cache invalidation API for tenant_host: apps (#1289 slice 6).

Most projects don't need this. The framework auto-busts on
`Repository.update` of any slug field on a `tenant_host:` entity. Use
``bust(slug)`` for the edge cases:

    * raw-SQL renames
    * migration fixups that bypass Repository
    * admin CLI tools that mutate the DB out-of-band
"""

from __future__ import annotations

from collections.abc import Iterable

from dazzle.back.runtime.tenant.cache import TenantCache

_REGISTERED_CACHES: list[TenantCache] = []


def _register_cache(cache: TenantCache) -> None:
    """Called from app_factory when a TenantHostBinding is built."""
    _REGISTERED_CACHES.append(cache)


def _active_caches() -> Iterable[TenantCache]:
    return list(_REGISTERED_CACHES)


def _clear_registry() -> None:  # pragma: no cover - test hygiene only
    """Drop every registered cache. Tests use this to isolate state."""
    _REGISTERED_CACHES.clear()


def bust(slug: str) -> None:
    """Remove `slug` from every registered tenant cache."""
    for cache in _active_caches():
        cache.bust(slug)
