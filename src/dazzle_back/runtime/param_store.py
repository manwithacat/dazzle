"""Runtime parameter store: validation, resolution with scope cascade."""

import time
from typing import Any

from dazzle.core.ir.params import ParamConstraints, ParamRef, ParamSpec

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_TYPE_CHECKERS: dict[str, Any] = {
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
    "str": lambda v: isinstance(v, str),
    "list[float]": lambda v: (
        isinstance(v, list)
        and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)
    ),
    "list[str]": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
}


def validate_param_value(spec: ParamSpec, value: Any) -> list[str]:
    """Validate *value* against a ParamSpec's declared type and constraints.

    Returns a list of error strings.  An empty list means the value is valid.
    """
    errors: list[str] = []

    # --- type check ---
    checker = _TYPE_CHECKERS.get(spec.param_type)
    if checker is not None and not checker(value):
        errors.append(f"Expected type {spec.param_type}, got {type(value).__name__}")
        return errors  # skip constraint checks when type fails

    # --- constraint checks ---
    constraints: ParamConstraints | None = spec.constraints
    if constraints is None:
        return errors

    # scalar min/max
    if (
        constraints.min_value is not None
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        if value < constraints.min_value:
            errors.append(f"Value {value} < min_value {constraints.min_value}")
    if (
        constraints.max_value is not None
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        if value > constraints.max_value:
            errors.append(f"Value {value} > max_value {constraints.max_value}")

    # list length
    if isinstance(value, list):
        if constraints.min_length is not None and len(value) < constraints.min_length:
            errors.append(f"List length {len(value)} < min_length {constraints.min_length}")
        if constraints.max_length is not None and len(value) > constraints.max_length:
            errors.append(f"List length {len(value)} > max_length {constraints.max_length}")

        # ordered
        if constraints.ordered == "ascending":
            for i in range(1, len(value)):
                if value[i] < value[i - 1]:
                    errors.append(f"List not ascending at index {i}: {value[i - 1]} > {value[i]}")
                    break
        elif constraints.ordered == "descending":
            for i in range(1, len(value)):
                if value[i] > value[i - 1]:
                    errors.append(f"List not descending at index {i}: {value[i - 1]} < {value[i]}")
                    break

        # range on elements
        if constraints.range is not None and len(constraints.range) == 2:
            lo, hi = constraints.range
            for i, elem in enumerate(value):
                if isinstance(elem, (int, float)) and (elem < lo or elem > hi):
                    errors.append(f"Element {i} value {elem} outside range [{lo}, {hi}]")

    return errors


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

_CACHE_TTL = 60.0  # seconds


class ParamResolver:
    """Resolves parameter values using a scope cascade: user > tenant > system > default."""

    def __init__(
        self,
        specs: dict[str, ParamSpec],
        overrides: dict[tuple[str, str, str], Any] | None = None,
    ) -> None:
        self._specs = specs
        self._overrides: dict[tuple[str, str, str], Any] = dict(overrides) if overrides else {}
        self._cache: dict[tuple[str, str | None, str | None], tuple[Any, str, float]] = {}

    # -- public API ----------------------------------------------------------

    def resolve(
        self,
        key: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ) -> tuple[Any, str]:
        """Return ``(value, source)`` for *key*.

        Source is one of ``"user/{id}"``, ``"tenant/{id}"``, ``"system"``, or
        ``"default"``.  Raises :class:`KeyError` if *key* is unknown.
        """
        if key not in self._specs:
            raise KeyError(key)

        cache_key = (key, tenant_id, user_id)
        cached = self._cache.get(cache_key)
        if cached is not None:
            value, source, ts = cached
            if (time.monotonic() - ts) < _CACHE_TTL:
                return value, source

        value, source = self._cascade(key, tenant_id, user_id)
        self._cache[cache_key] = (value, source, time.monotonic())
        return value, source

    def set_override(self, key: str, scope: str, scope_id: str, value: Any) -> list[str]:
        """Validate and store an override.  Returns validation errors (empty = success)."""
        if key not in self._specs:
            return [f"Unknown parameter key: {key}"]
        errors = validate_param_value(self._specs[key], value)
        if errors:
            return errors
        self._overrides[(key, scope, scope_id)] = value
        # invalidate any cached entries for this key
        self._cache = {k: v for k, v in self._cache.items() if k[0] != key}
        return []

    # -- internals -----------------------------------------------------------

    def _cascade(
        self,
        key: str,
        tenant_id: str | None,
        user_id: str | None,
    ) -> tuple[Any, str]:
        # user
        if user_id is not None:
            user_val = self._overrides.get((key, "user", user_id))
            if user_val is not None:
                return user_val, f"user/{user_id}"
        # tenant
        if tenant_id is not None:
            tenant_val = self._overrides.get((key, "tenant", tenant_id))
            if tenant_val is not None:
                return tenant_val, f"tenant/{tenant_id}"
        # system
        system_val = self._overrides.get((key, "system", "system"))
        if system_val is not None:
            return system_val, "system"
        # default
        return self._specs[key].default, "default"


# ---------------------------------------------------------------------------
# Convenience helper
# ---------------------------------------------------------------------------


def resolve_value(
    raw: Any,
    resolver: ParamResolver | None,
    tenant_id: str | None = None,
) -> Any:
    """If *raw* is a :class:`ParamRef`, resolve it; otherwise return as-is."""
    if isinstance(raw, ParamRef):
        if resolver is None:
            return raw.default
        value, _ = resolver.resolve(raw.key, tenant_id=tenant_id)
        return value
    return raw
