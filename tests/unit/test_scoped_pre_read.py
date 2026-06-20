"""Unit tests for `_scoped_pre_read` — runtime scope enforcement on
UPDATE/DELETE handlers (#1123, v0.71.19).

The helper sits between the permit gate and the actual write SQL in
`_build_cedar_handler`. It replaces the bare `service.execute(operation
="read", id=id)` pre-read with a scope-validated lookup so the handler
404s before the UPDATE/DELETE runs if the scope predicate rejects the
target row.

Three behaviour shapes to pin:

1. **No `scope:` rules for this op** → fall through to unscoped read
   (back-compat with pre-v0.71.19 behaviour and tests).
2. **`scope: all`** → fall through to unscoped read (no filter needed).
3. **`scope:` with field condition** → refetch via scope-filtered LIST;
   404 if row doesn't satisfy the predicate.
4. **No matching scope rule** (entity has scope blocks but none for
   this role/op) → default-deny: return None → caller 404s.

The 404-on-scope-fail shape matches the LIST endpoint's default-deny
behaviour — IDOR-style probing can't distinguish "row doesn't exist"
from "row exists but is out of scope."
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.http.runtime.route_generator import _scoped_pre_read


def _make_service(read_result: object = None, list_items: list | None = None) -> AsyncMock:
    """Stand-in for BaseService — only execute() is consulted."""
    service = MagicMock()

    async def _execute(operation: str, **kwargs):
        if operation == "read":
            return read_result
        if operation == "list":
            return {"items": list_items or [], "total": len(list_items or []), "page": 1}
        return None

    service.execute = AsyncMock(side_effect=_execute)
    return service


def _auth_context(roles: list[str], user_id: str = "u-1") -> SimpleNamespace:
    """Build a minimal AuthContext shape — the helper reads
    is_authenticated, user.id, user.roles."""
    user = SimpleNamespace(id=user_id, roles=roles)
    return SimpleNamespace(is_authenticated=True, user=user)


def _spec_with_scope_rule(*, op: str, persona: str, all_rows: bool = True) -> SimpleNamespace:
    """Build an EntityAccessSpec stand-in with one matching scope rule."""
    rule = SimpleNamespace(
        operation=SimpleNamespace(value=op),
        personas=[persona],
        condition=None if all_rows else SimpleNamespace(kind="comparison"),
        predicate=None if all_rows else SimpleNamespace(kind="user_attr_check"),
    )
    return SimpleNamespace(scopes=[rule])


# ---------------------------------------------------------------------------
# 1. Back-compat: no scope rules → unscoped read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_scope_rules_falls_through_to_unscoped_read() -> None:
    """When an entity has no scope: block, the helper must short-circuit
    to the legacy unscoped read. Keeps pre-v0.71.19 behaviour for
    entities that don't declare scope rules."""
    record = {"id": "row-1", "title": "x"}
    service = _make_service(read_result=record)
    spec = SimpleNamespace(scopes=None)

    result = await _scoped_pre_read(
        service=service,
        operation="update",
        id="row-1",
        cedar_access_spec=spec,
        auth_context=_auth_context(["role_admin"]),
        entity_name="Task",
        fk_graph=MagicMock(),  # provided but unused on this branch
        admin_personas=None,
    )

    assert result == record
    service.execute.assert_awaited_once_with(operation="read", id="row-1")


# ---------------------------------------------------------------------------
# 2. No fk_graph → fall through (defensive — test fixtures without FK)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_fk_graph_falls_through_to_unscoped_read() -> None:
    """Without an FK graph the predicate compiler can't run — the
    helper falls through rather than default-denying. Protects test
    fixtures and legacy callers that don't supply fk_graph."""
    record = {"id": "row-1"}
    service = _make_service(read_result=record)
    spec = _spec_with_scope_rule(op="update", persona="admin")

    result = await _scoped_pre_read(
        service=service,
        operation="update",
        id="row-1",
        cedar_access_spec=spec,
        auth_context=_auth_context(["role_admin"]),
        entity_name="Task",
        fk_graph=None,
        admin_personas=None,
    )

    assert result == record


# ---------------------------------------------------------------------------
# 3. scope: all matches → unscoped read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scope_all_matches_falls_through_to_unscoped_read() -> None:
    """`scope: all as: admin` + admin user → no filter applied, just
    a regular read. Matches the LIST handler's `scope: all` branch."""
    record = {"id": "row-1"}
    service = _make_service(read_result=record)
    spec = _spec_with_scope_rule(op="update", persona="admin", all_rows=True)

    result = await _scoped_pre_read(
        service=service,
        operation="update",
        id="row-1",
        cedar_access_spec=spec,
        auth_context=_auth_context(["role_admin"]),
        entity_name="Task",
        fk_graph=MagicMock(),
        admin_personas=None,
    )

    assert result == record
    # Used the unscoped read path — no LIST call.
    calls = [c.kwargs.get("operation") or c.args[0] for c in service.execute.await_args_list]
    assert "list" not in calls


# ---------------------------------------------------------------------------
# 4. Default-deny: scope block exists but no rule matches this role/op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_matching_scope_rule_returns_none_for_default_deny() -> None:
    """Entity has scope rules for some ops/roles, but none for the
    current request. Per ADR-0010 default-deny semantics, returns
    None → caller 404s. Same shape as the LIST handler's empty-result
    response when no scope rule matches."""
    service = _make_service(read_result={"id": "row-1"})
    # Scope rule for `list` only — not `update`.
    spec = _spec_with_scope_rule(op="list", persona="admin")

    result = await _scoped_pre_read(
        service=service,
        operation="update",
        id="row-1",
        cedar_access_spec=spec,
        auth_context=_auth_context(["role_admin"]),
        entity_name="Task",
        fk_graph=MagicMock(),
        admin_personas=None,
    )

    assert result is None
    # Helper short-circuited — never reached the read path.
    service.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# 5. Unauthenticated fallback — defensive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_falls_through_to_unscoped_read() -> None:
    """The permit gate rejects unauth users before this helper runs
    when cedar_access_spec is set. This branch is defensive — if
    somehow an unauth context reaches here, fall through rather than
    default-deny so the test path isn't surprised."""
    record = {"id": "row-1"}
    service = _make_service(read_result=record)
    spec = _spec_with_scope_rule(op="update", persona="admin", all_rows=True)
    unauth = SimpleNamespace(is_authenticated=False, user=None)

    result = await _scoped_pre_read(
        service=service,
        operation="update",
        id="row-1",
        cedar_access_spec=spec,
        auth_context=unauth,
        entity_name="Task",
        fk_graph=MagicMock(),
        admin_personas=None,
    )

    assert result == record


# ---------------------------------------------------------------------------
# Adversarial / negative scope-enforcement tests (#1173)
#
# These exercise the *attack* paths, not the happy path: a scope predicate
# that fails to compile, and an IDOR probe against a row outside the
# caller's scope. The contract under test is fail-closed — a broken or
# unsatisfied scope rule must deny, never widen access.
# ---------------------------------------------------------------------------


class TestAdversarialScopeEnforcement:
    """Negative-path coverage for runtime scope enforcement (#1173)."""

    @pytest.mark.asyncio
    async def test_predicate_compilation_failure_denies(self) -> None:
        """If the scope predicate raises during resolution (malformed FK
        path, null EXISTS binding, etc.), the resolver catches it and
        returns None — the handler then 404s. Fail-closed: a broken
        predicate must never fall through to an unscoped read."""
        service = _make_service(read_result={"id": "row-1"})
        spec = _spec_with_scope_rule(op="update", persona="admin", all_rows=False)

        with patch(
            "dazzle.http.runtime.scope_filters._resolve_predicate_filters",
            side_effect=RuntimeError("predicate boom"),
        ):
            result = await _scoped_pre_read(
                service=service,
                operation="update",
                id="row-1",
                cedar_access_spec=spec,
                auth_context=_auth_context(["role_admin"]),
                entity_name="Task",
                fk_graph=MagicMock(),
                admin_personas=None,
            )

        assert result is None
        # Denied before any DB access — never reached read or list.
        service.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_legacy_condition_failure_denies(self) -> None:
        """The legacy condition-tree path is equally fail-closed: if
        `_extract_condition_filters` raises, the resolver returns None
        rather than falling through to an unscoped read."""
        service = _make_service(read_result={"id": "row-1"})
        # predicate=None forces the legacy condition path.
        rule = SimpleNamespace(
            operation=SimpleNamespace(value="update"),
            personas=["admin"],
            condition=SimpleNamespace(kind="comparison"),
            predicate=None,
        )
        spec = SimpleNamespace(scopes=[rule])

        with patch(
            "dazzle.http.runtime.scope_filters._extract_condition_filters",
            side_effect=RuntimeError("condition boom"),
        ):
            result = await _scoped_pre_read(
                service=service,
                operation="update",
                id="row-1",
                cedar_access_spec=spec,
                auth_context=_auth_context(["role_admin"]),
                entity_name="Task",
                fk_graph=MagicMock(),
                admin_personas=None,
            )

        assert result is None
        service.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_idor_foreign_row_filtered_returns_none(self) -> None:
        """IDOR resistance: the scope predicate resolves to a real row
        filter, but the scoped re-fetch finds nothing — the target id
        belongs to another scope. The helper returns None → handler
        404s, indistinguishable from a genuinely non-existent row.

        `read` would happily return the row; only the scope-filtered
        `list` gates it. A handler that skipped the scoped pre-read
        (or trusted `read`) would leak another tenant's record."""
        service = _make_service(
            read_result={"id": "row-1", "owner_id": "someone-else"},
            list_items=[],  # scoped re-fetch finds nothing
        )
        spec = _spec_with_scope_rule(op="update", persona="admin", all_rows=False)

        with patch(
            "dazzle.http.runtime.scope_filters._resolve_predicate_filters",
            return_value={"owner_id": "u-1"},
        ):
            result = await _scoped_pre_read(
                service=service,
                operation="update",
                id="row-1",
                cedar_access_spec=spec,
                auth_context=_auth_context(["role_admin"], user_id="u-1"),
                entity_name="Task",
                fk_graph=MagicMock(),
                admin_personas=None,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_idor_owned_row_passes_scope(self) -> None:
        """Counterpart to the IDOR test: when the scoped re-fetch finds
        the row, the caller is in scope and the helper returns it."""
        record = {"id": "row-1", "owner_id": "u-1"}
        service = _make_service(read_result=record, list_items=[record])
        spec = _spec_with_scope_rule(op="update", persona="admin", all_rows=False)

        with patch(
            "dazzle.http.runtime.scope_filters._resolve_predicate_filters",
            return_value={"owner_id": "u-1"},
        ):
            result = await _scoped_pre_read(
                service=service,
                operation="update",
                id="row-1",
                cedar_access_spec=spec,
                auth_context=_auth_context(["role_admin"], user_id="u-1"),
                entity_name="Task",
                fk_graph=MagicMock(),
                admin_personas=None,
            )

        assert result == record
