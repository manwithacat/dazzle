"""Per-tenant config coercion (#957 cycle 7).

`tenancy: per_tenant_config:` in the DSL declares a schema like::

    per_tenant_config:
      locale: str
      theme: str
      feature_billing: bool
      max_users: int

The raw values stored on `public.tenants.config` (JSONB) come from
external sources — admin UI, CSV import, REST API — and may be
strings, numbers, or booleans regardless of the declared type. This
module coerces them once on read so the rest of the runtime can rely
on consistent types via ``request.state.tenant_config`` (cycle 8).

The coercion is intentionally conservative:

  * Unknown keys are dropped (forward-compat: an old binary reading
    a config written by a newer one shouldn't crash).
  * Type errors fall back to the declared-type's "zero" value
    (empty string, 0, False) — never raise from inside the request
    path. Misconfigured values surface in admin UI / validators
    instead.
  * Missing keys default to the declared-type's zero, so callers can
    always do ``cfg["locale"]`` without a `KeyError`.

Supported declared types: ``str``, ``int``, ``bool``, ``locale``.
``locale`` is treated as ``str`` for storage but is reserved for
future locale-aware coercion (e.g. normalising ``"en-US"`` ↔
``"en_US"`` per BCP 47).
"""

from __future__ import annotations

from typing import Any

# Maps declared-type strings (as written in the DSL) to a Python
# coercer callable + zero value. Unknown types are treated as `str`.
_COERCERS: dict[str, tuple[Any, Any]] = {
    "str": (str, ""),
    "int": (int, 0),
    "bool": (bool, False),
    # `locale` shares storage with str for now; cycle 8+ may add BCP-47
    # normalisation.
    "locale": (str, ""),
}


def _coerce_bool(value: Any) -> bool:
    """Tolerant bool coercion: accepts the strings 'true'/'false'.

    JSONB always round-trips proper booleans, but admin UIs may submit
    them as form-encoded strings. Using `bool(value)` directly would
    treat the string ``"false"`` as truthy; this function returns
    False for the canonical false-y string forms.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _coerce_one(value: Any, declared_type: str) -> Any:
    """Coerce a single value to its declared type, falling back to zero."""
    coercer, zero = _COERCERS.get(declared_type, _COERCERS["str"])
    if value is None:
        return zero
    if declared_type == "bool":
        return _coerce_bool(value)
    try:
        # `int(True)` is 1 — guard so a typo'd schema doesn't silently
        # turn a bool into 1/0 numbers.
        if declared_type == "int" and isinstance(value, bool):
            return zero
        return coercer(value)
    except (TypeError, ValueError):
        return zero


def coerce_config(
    raw: dict[str, Any] | None,
    schema: dict[str, str] | None,
) -> dict[str, Any]:
    """Coerce a raw config dict against a per_tenant_config schema.

    Returns a fresh dict with one entry per schema key (using the
    type's zero value for missing keys), and silently drops any keys
    in ``raw`` that aren't declared in ``schema``.

    Args:
        raw: The JSONB-decoded value from `public.tenants.config`. May
            be None for tenants created before cycle 7.
        schema: ``TenancySpec.per_tenant_config`` from the AppSpec —
            keys are config names, values are declared-type strings
            (``str``, ``int``, ``bool``, ``locale``). May be None for
            apps without per-tenant config.
    """
    if not schema:
        return {}
    raw = raw or {}
    return {key: _coerce_one(raw.get(key), declared_type) for key, declared_type in schema.items()}
