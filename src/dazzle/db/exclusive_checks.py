"""Exclusive-anchor CHECK constraints (#1617 / #1620).

Derived from the same at-least-one-anchor invariant shape as
``dazzle.db.verify.unanchored_invariant_fields``. Soft verify reports
``unanchored`` (zero set) and ``exclusive_conflict`` (multi set); hard
CHECK enforces **exactly one** non-null exclusive FK at the storage layer.

Portable CASE form (works on Postgres; no reliance on ``num_nonnulls``).
"""

from __future__ import annotations

from typing import Any

from dazzle.db.verify import unanchored_invariant_fields


def exclusive_check_name(table: str, fields: list[str]) -> str:
    """Deterministic constraint name for alembic stability."""
    cols = "_".join(fields)
    # PG identifier limit 63; keep prefix + hash tail if long
    base = f"ck_{table}_excl_{cols}"
    if len(base) <= 63:
        return base
    import hashlib

    # Non-crypto short fingerprint for PG identifier length only (not a security hash).
    digest = hashlib.sha1(cols.encode(), usedforsecurity=False).hexdigest()[:8]
    return f"ck_{table}_excl_{digest}"[:63]


def exclusive_exactly_one_sql(fields: list[str]) -> str:
    """SQL boolean expression: exactly one of *fields* is non-null."""
    if len(fields) < 2:
        raise ValueError("exclusive CHECK needs at least two fields")
    parts = " + ".join(f'(CASE WHEN "{f}" IS NOT NULL THEN 1 ELSE 0 END)' for f in fields)
    return f"({parts}) = 1"


def _field_kind(entity: Any, name: str) -> str:
    for f in getattr(entity, "fields", None) or []:
        if str(getattr(f, "name", "")) != name:
            continue
        t = getattr(f, "type", None)
        k = getattr(t, "kind", None)
        return str(getattr(k, "value", k) or "")
    return ""


def exclusive_anchor_field_sets(entity: Any) -> list[list[str]]:
    """Return exclusive-anchor **ref** field lists from entity invariants.

    Only ``ref`` / ``belongs_to`` fields qualify as exclusive parents
    (``rel.exclusive_fks``). Scalar at-least-one invariants
    (``email != null or phone != null``) stay soft-verify-only — they are
    **not** exclusive FKs and must not emit CHECK or first_non_null.
    """
    sets: list[list[str]] = []
    for inv in getattr(entity, "invariants", None) or []:
        fields = unanchored_invariant_fields(inv)
        if not fields or len(fields) < 2:
            continue
        refs = [f for f in fields if _field_kind(entity, f) in ("ref", "belongs_to")]
        if len(refs) >= 2:
            sets.append(refs)
    return sets


def check_constraint_specs(entity: Any) -> list[tuple[str, str, list[str]]]:
    """(constraint_name, sql_condition, fields) for each exclusive set."""
    table = str(entity.name)
    out: list[tuple[str, str, list[str]]] = []
    for fields in exclusive_anchor_field_sets(entity):
        name = exclusive_check_name(table, fields)
        sql = exclusive_exactly_one_sql(fields)
        out.append((name, sql, fields))
    return out
