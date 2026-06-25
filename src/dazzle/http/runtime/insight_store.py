"""Stored-narrative provider seam for display: insight_summary (#1470 Slice 2a).

The region render reads a pre-computed narrative through this seam. The default
provider returns None (so the region falls back to the deterministic Slice-1
narrative). Slice 2b registers a real provider (a scheduled process that calls
the LLM over the grounded buckets and writes a store). Tests + the catalogue
inject a stub.

The registry is a dict mutated in place (not a reassigned module global) to
stay clear of the #1445 mutable-globals ratchet.
"""

from collections.abc import Callable

from dazzle.render.fragment.insight import StoredInsight

_Provider = Callable[[str], "StoredInsight | None"]


def _default_provider(_region_name: str) -> "StoredInsight | None":
    return None


_REGISTRY: dict[str, _Provider] = {"provider": _default_provider}


def set_insight_provider(fn: _Provider) -> None:
    """Register the stored-narrative provider (keyed by region name)."""
    _REGISTRY["provider"] = fn


def reset_insight_provider() -> None:
    """Restore the default (None-returning) provider."""
    _REGISTRY["provider"] = _default_provider


def get_stored_insight(region_name: str) -> "StoredInsight | None":
    """Return the stored narrative for ``region_name``, or None (→ deterministic fallback)."""
    return _REGISTRY["provider"](region_name)
