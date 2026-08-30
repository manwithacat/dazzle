"""Cheap in-process tenancy counters (ADR-0055 observability).

Named after the CONOPS Prometheus labels. Tests read the dicts; a later
exporter can scrape the same functions. No tokens, cookies, or TXT secrets.
"""

from __future__ import annotations

from threading import Lock

_lock = Lock()

# dazzle_tenant_resolve_total{topology,result}
_RESOLVE_COUNTS: dict[object, int] = {}
# dazzle_rls_unbound_total (optional path label for /sign/*)
_UNBOUND_COUNTS: dict[object, int] = {}
# dazzle_cross_tenant_guard_total{reason}
_GUARD_COUNTS: dict[object, int] = {}
# dazzle_alias_verify_total{result}
_ALIAS_VERIFY_COUNTS: dict[object, int] = {}


def _bump(store: dict[object, int], key: object) -> None:
    with _lock:
        store[key] = store.get(key, 0) + 1


def note_tenant_resolve(topology: str, result: str) -> None:
    """``hit`` / ``canonical`` / ``bad_host`` / ``404`` / ``301`` / ``410``."""
    _bump(_RESOLVE_COUNTS, (topology or "", result))


def note_rls_unbound(path: str = "") -> None:
    """Fence unset on a tenant-scoped path (host GUC set, ``dazzle.tenant_id`` not)."""
    _bump(_UNBOUND_COUNTS, path)


def note_cross_tenant_guard(reason: str) -> None:
    """``pass`` / ``cross_tenant`` / ``host_cookie_on_apex`` / ``apex_not_superadmin``."""
    _bump(_GUARD_COUNTS, reason)


def note_alias_verify(result: str) -> None:
    """Alias attach step: ``txt_ok`` / ``txt_not_found`` / ``cname_ok`` / …"""
    _bump(_ALIAS_VERIFY_COUNTS, result)


def resolve_counts() -> dict[tuple[str, str], int]:
    with _lock:
        out: dict[tuple[str, str], int] = {}
        for k, v in _RESOLVE_COUNTS.items():
            if isinstance(k, tuple) and len(k) == 2:
                out[(str(k[0]), str(k[1]))] = v
        return out


def unbound_counts() -> dict[str, int]:
    with _lock:
        return {str(k): v for k, v in _UNBOUND_COUNTS.items()}


def guard_counts() -> dict[str, int]:
    with _lock:
        return {str(k): v for k, v in _GUARD_COUNTS.items()}


def alias_verify_counts() -> dict[str, int]:
    with _lock:
        return {str(k): v for k, v in _ALIAS_VERIFY_COUNTS.items()}


def reset_tenancy_metrics() -> None:
    """Test hygiene — drop every counter."""
    with _lock:
        _RESOLVE_COUNTS.clear()
        _UNBOUND_COUNTS.clear()
        _GUARD_COUNTS.clear()
        _ALIAS_VERIFY_COUNTS.clear()
