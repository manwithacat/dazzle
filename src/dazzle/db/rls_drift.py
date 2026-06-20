"""RLS policy drift detection (RLS tenancy Phase D — drift gate).

The shape-level companion to :func:`dazzle.db.rls_apply.apply_rls_policies`:
given a live database, it answers "does the live RLS policy set still match what
the DSL says it should be?" and reports any tenant-scoped table that has drifted.

**Shape-based, NOT qual-text.** Comparing the live ``pg_policies.qual`` /
``with_check`` TEXT to the generated predicate body is fragile — PostgreSQL
normalises and reparenthesises the expression, so a byte-diff false-positives on
a clean apply. Instead this compares the *policy SET* per table:

- the expected policy NAMES (``tenant_fence`` / ``tenant_baseline`` /
  ``scope_<verb>``) — the shared source of truth from
  :func:`dazzle.http.runtime.rls_schema.describe_rls_policies`;
- each policy's ``cmd`` (``ALL`` / ``SELECT`` / ``INSERT`` / ``UPDATE`` /
  ``DELETE``);
- each policy's permissive/restrictive flag;
- that RLS is ENABLED **and** FORCED on the table.

Drift is any of: RLS not enabled, RLS not forced, an expected policy missing, an
unexpected/extra policy present, or an expected policy present under the wrong
``cmd`` / permissive flag. Exact predicate-body equivalence is deliberately out
of scope (a deeper, separate check).

This module is purely diagnostic — it never applies or alters policies. The fix
for drift is ``dazzle db apply-rls`` (or ``dazzle db upgrade``), run as the table
owner.
"""

from __future__ import annotations

from typing import Any

from .connection import fetchall, fetchrow


def _live_policy_key(policy: dict[str, Any]) -> tuple[str, str, bool]:
    """Shape key for a live ``pg_policies`` row — ``(name, cmd, permissive)``.

    ``pg_policies.cmd`` is the upper-case command verb (``ALL`` / ``SELECT`` /
    ``INSERT`` / ``UPDATE`` / ``DELETE``); ``pg_policies.permissive`` is the text
    ``'PERMISSIVE'`` / ``'RESTRICTIVE'``. Both are normalised here so a live row
    compares directly against a :class:`PolicyDescriptor`'s shape.
    """
    name = str(policy["policyname"])
    cmd = str(policy["cmd"]).upper()
    permissive_raw = policy["permissive"]
    # pg_policies.permissive is text ('PERMISSIVE'/'RESTRICTIVE') but tolerate a
    # bool just in case a driver coerces it.
    if isinstance(permissive_raw, bool):
        permissive = permissive_raw
    else:
        permissive = str(permissive_raw).upper() == "PERMISSIVE"
    return (name, cmd, permissive)


def compare_table_policies(
    entity: str,
    expected: list[Any],
    live_policies: list[dict[str, Any]],
    *,
    rls_enabled: bool,
    rls_forced: bool,
) -> list[str]:
    """Compute the shape-level drift issues for one tenant-scoped table.

    Pure, DB-free comparison — unit-testable with a fake ``live_policies`` list.

    Args:
        entity: The table / entity name (for issue messages).
        expected: The :class:`PolicyDescriptor` list for this entity (the subset
            of :func:`describe_rls_policies` output where ``.entity == entity``).
        live_policies: Live ``pg_policies`` rows for this table — each a dict with
            ``policyname``, ``cmd``, ``permissive``.
        rls_enabled: ``pg_class.relrowsecurity`` for the table.
        rls_forced: ``pg_class.relforcerowsecurity`` for the table.

    Returns:
        A list of human-readable issue strings; empty when the live shape matches
        the expected shape exactly (and RLS is enabled + forced).
    """
    issues: list[str] = []

    if not rls_enabled:
        issues.append("RLS not enabled (ENABLE ROW LEVEL SECURITY missing)")
    if not rls_forced:
        issues.append("RLS not forced (FORCE ROW LEVEL SECURITY missing)")

    expected_names = {d.name for d in expected}

    live_keys = {_live_policy_key(p) for p in live_policies}
    live_names = {str(p["policyname"]) for p in live_policies}

    # Expected policies that are missing (by name) or present under the wrong
    # cmd/permissive shape.
    for d in expected:
        key = (d.name, d.cmd.upper(), d.permissive)
        if key in live_keys:
            continue
        if d.name not in live_names:
            issues.append(f"missing expected policy {d.name!r} ({d.cmd}, {_perm(d.permissive)})")
        else:
            # Name present but cmd/permissive differs — a shape mismatch.
            live_for_name = [
                _live_policy_key(p) for p in live_policies if str(p["policyname"]) == d.name
            ]
            issues.append(
                f"policy {d.name!r} has wrong shape: expected ({d.cmd}, {_perm(d.permissive)}), "
                f"live {[(c, _perm(perm)) for _n, c, perm in live_for_name]}"
            )

    # Unexpected/extra policies on the table (a name we never generate).
    for name in sorted(live_names - expected_names):
        issues.append(f"unexpected policy {name!r} present (not in the generated set)")

    return issues


def _perm(permissive: bool) -> str:
    return "PERMISSIVE" if permissive else "RESTRICTIVE"


async def _live_table_rls(conn: Any, table: str) -> tuple[bool, bool, bool]:
    """Return ``(table_exists, relrowsecurity, relforcerowsecurity)`` for a table."""
    row = await fetchrow(
        conn,
        "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
        "WHERE relname = %s AND relnamespace = 'public'::regnamespace",
        (table,),
    )
    if row is None:
        return (False, False, False)
    return (True, bool(row["relrowsecurity"]), bool(row["relforcerowsecurity"]))


async def _live_policies(conn: Any, table: str) -> list[dict[str, Any]]:
    """Live ``pg_policies`` rows (policyname, cmd, permissive) for a table."""
    rows = await fetchall(
        conn,
        "SELECT policyname, cmd, permissive FROM pg_policies "
        "WHERE schemaname = 'public' AND tablename = %s",
        (table,),
    )
    return [dict(r) for r in rows]


async def detect_rls_drift(conn: Any, appspec: Any, entities: list[Any]) -> list[dict[str, Any]]:
    """Return RLS shape-drift entries for an appspec's tenant-scoped tables.

    The expected policy set is :func:`describe_rls_policies` (the shared
    source-of-truth shape view); the live set is read from ``pg_class`` +
    ``pg_policies``. Comparison is shape-based (name + cmd + permissive + RLS
    enabled/forced), never qual-text (see module docstring).

    Each entry is ``{"entity": name, "issues": [...]}`` for a tenant-scoped table
    whose live RLS shape diverges from the expected set. The list is empty when
    every tenant-scoped table matches (or the app has no row-level tenancy — a
    non-``shared_schema`` isolation mode yields no expected policies, so this is a
    no-op).

    A table that is entirely ABSENT from the live DB is **not** reported as drift
    — that is an unmigrated DB (a different state), not policy drift, and flagging
    it would false-positive a fresh/never-upgraded database (mirrors
    :func:`detect_signable_drift`).

    Args:
        conn: A psycopg3 async connection (owned/closed by the caller).
        appspec: The application IR (``.tenancy``, ``.domain.entities``).
        entities: The converted back-spec entities (``convert_entities(...)``).

    Returns:
        A list of drift entries, ordered by entity name; empty = no drift.
    """
    from dazzle.http.runtime.rls_schema import describe_rls_policies

    descriptors = describe_rls_policies(appspec, entities)
    if not descriptors:
        return []

    # Group expected descriptors by entity, preserving order.
    by_entity: dict[str, list[Any]] = {}
    for d in descriptors:
        by_entity.setdefault(d.entity, []).append(d)

    drifts: list[dict[str, Any]] = []
    for entity_name in sorted(by_entity):
        exists, rls_enabled, rls_forced = await _live_table_rls(conn, entity_name)
        if not exists:
            # Unmigrated table — not policy drift (see docstring).
            continue
        live = await _live_policies(conn, entity_name)
        issues = compare_table_policies(
            entity_name,
            by_entity[entity_name],
            live,
            rls_enabled=rls_enabled,
            rls_forced=rls_forced,
        )
        if issues:
            drifts.append({"entity": entity_name, "issues": issues})

    return drifts
