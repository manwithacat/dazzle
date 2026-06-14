"""#1394 — `current_tenant` scope/display variable (Layer 1).

`current_tenant` binds the host-resolved tenant (`request.state.tenant` from the
#1289 tenant_host resolver), DELIBERATELY distinct from the RLS row-tenancy
`dazzle.tenant_id`. Two surfaces:

  1. **Scope equality** — `field = current_tenant` (id-only) compiles to a
     `CurrentTenantRef` marker (param mode) / `current_setting('dazzle.host_tenant_id',
     true)::<type>` (policy mode). The marker resolvers fail closed (deny) when no
     host tenant is bound.
  2. **Display gate** — `current_tenant[.attr]` in `visible_when`/`when` resolves
     id/slug/kind/name from the render context at render time.

The GUC name (`HOST_TENANT_GUC`) is the dedicated host-tenant GUC, never
`dazzle.tenant_id` — proven by a real-Postgres round-trip in
``tests/integration/test_current_tenant_scope_pg.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dazzle.back.runtime.predicate_compiler import (
    CurrentTenantRef,
    _compile_value_ref,
)
from dazzle.back.runtime.rls_schema import HOST_TENANT_GUC, TENANT_GUC
from dazzle.back.runtime.tenant_render_context import inject_current_tenant
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.predicate_builder import build_scope_predicate
from dazzle.core.ir.predicates import ColumnCheck, CompOp, ValueRef
from dazzle.ui.utils.condition_eval import evaluate_condition

# ──────────────────────────── IR / builder ────────────────────────────

_SCOPE_DSL = """module t
app t "Test"
persona viewer "Viewer":
  capabilities: [read]
entity Doc "Doc":
  display_field: title
  id: uuid pk
  org: ref Doc
  title: str(80) required
  permit:
    read: role(viewer)
  scope:
    read: {rhs}
      as: viewer
"""


def _scope_predicate(rhs: str) -> object:
    mod = parse_dsl(_SCOPE_DSL.format(rhs=rhs), Path("t.dsl"))[5]
    doc = next(e for e in mod.entities if e.name == "Doc")
    return build_scope_predicate(doc.access.scopes[0].condition, "Doc", None)


class TestCurrentTenantIR:
    def test_bare_current_tenant_builds_columncheck_valueref(self) -> None:
        pred = _scope_predicate("org = current_tenant")
        assert isinstance(pred, ColumnCheck)
        assert pred.field == "org"
        assert pred.value.current_tenant is True
        # Mutually exclusive with the user fields.
        assert pred.value.current_user is False
        assert pred.value.user_attr is None

    def test_explicit_dot_id_is_same_as_bare(self) -> None:
        pred = _scope_predicate("org = current_tenant.id")
        assert isinstance(pred, ColumnCheck)
        assert pred.value.current_tenant is True

    def test_current_user_unaffected(self) -> None:
        # Regression: the new branch must not capture current_user.
        pred = _scope_predicate("org = current_user")
        assert getattr(pred, "user_attr", None) == "entity_id"


# ──────────────────────────── compiler ────────────────────────────


class TestCurrentTenantCompiler:
    def test_param_mode_emits_marker(self) -> None:
        sql, params = _compile_value_ref(ValueRef(current_tenant=True), policy=None)
        assert sql == "%s"
        assert params == [CurrentTenantRef()]

    def test_policy_mode_reads_host_tenant_guc(self) -> None:
        sql, params = _compile_value_ref(
            ValueRef(current_tenant=True), policy=object(), pg_type="uuid"
        )
        # NULLIF makes the empty-string pooled-reset state fail closed (deny)
        # instead of raising on `''::uuid`.
        assert sql == "NULLIF(current_setting('dazzle.host_tenant_id', true), '')::uuid"
        assert params == []

    def test_host_tenant_guc_is_distinct_from_rls_tenant_guc(self) -> None:
        # The whole point of #1394: never bind the RLS row-tenancy GUC.
        assert HOST_TENANT_GUC == "dazzle.host_tenant_id"
        assert HOST_TENANT_GUC != TENANT_GUC


# ──────────────────── marker resolution: fail closed ────────────────────


class TestMarkerResolutionFailsClosed:
    def test_scope_filter_denies_without_host_tenant(self) -> None:
        # No host tenant bound in the context var → the filter must deny (return
        # None), never emit an unfenced query.
        from dazzle.back.runtime import scope_filters

        pred = ColumnCheck(field="org", op=CompOp.EQ, value=ValueRef(current_tenant=True))
        result = scope_filters._resolve_predicate_filters(
            predicate=pred,
            entity_name="Doc",
            fk_graph=None,
            auth_context=None,
            user_id="u1",
            admin_personas=None,
        )
        assert result is None  # deny

    def test_scope_filter_binds_host_tenant_when_present(self) -> None:
        from dazzle.back.runtime import scope_filters
        from dazzle.back.runtime.tenant_isolation import (
            _current_host_tenant_id,
            set_current_host_tenant_id,
        )

        pred = ColumnCheck(field="org", op=CompOp.EQ, value=ValueRef(current_tenant=True))
        token = set_current_host_tenant_id("tenant-A-id")
        try:
            result = scope_filters._resolve_predicate_filters(
                predicate=pred,
                entity_name="Doc",
                fk_graph=None,
                auth_context=None,
                user_id="u1",
                admin_personas=None,
            )
        finally:
            _current_host_tenant_id.reset(token)
        assert result is not None
        sql, params = result["__scope_predicate"]
        assert "tenant-A-id" in params


# ─────────────── create-scope fail-closed (review Finding 1) ───────────────


class TestCreateScopeFailsClosed:
    """`field = current_tenant` create-scope must deny when no host tenant is
    bound — even when the payload omits the field (the `None == None` fail-open
    the security review caught)."""

    def test_resolve_value_denies_without_host_tenant(self) -> None:
        from dazzle.back.runtime.scope_create_eval import _CT_DENY, _compare, _resolve_value
        from dazzle.core.ir.predicates import CompOp

        # No host tenant in context → sentinel, not None.
        resolved = _resolve_value(ValueRef(current_tenant=True), "u1", {})
        assert resolved is _CT_DENY
        # The sentinel denies for EVERY operator — including NEQ, which would
        # otherwise be `left != sentinel` → always True → fail open.
        assert _compare(None, CompOp.EQ, resolved) is False
        assert _compare("any-tenant", CompOp.EQ, resolved) is False
        assert _compare("any-tenant", CompOp.NEQ, resolved) is False
        assert _compare(None, CompOp.NEQ, resolved) is False

    def test_resolve_value_binds_host_tenant_when_present(self) -> None:
        from dazzle.back.runtime.scope_create_eval import _compare, _resolve_value
        from dazzle.back.runtime.tenant_isolation import (
            _current_host_tenant_id,
            set_current_host_tenant_id,
        )
        from dazzle.core.ir.predicates import CompOp

        token = set_current_host_tenant_id("tenant-A")
        try:
            resolved = _resolve_value(ValueRef(current_tenant=True), "u1", {})
        finally:
            _current_host_tenant_id.reset(token)
        assert resolved == "tenant-A"
        assert _compare("tenant-A", CompOp.EQ, resolved) is True
        assert _compare("tenant-B", CompOp.EQ, resolved) is False


# ──────────────────────────── display gate ────────────────────────────


def _gate(field: str, op: str, value: str, context: dict) -> bool:
    cond = {"comparison": {"field": field, "operator": op, "value": {"literal": value}}}
    return evaluate_condition(cond, {}, context)


def _fake_request(tenant_id: str | None, *, slug: str = "acme", kind: str = "trust") -> Any:
    """A request whose ``state.tenant`` is a ResolvedTenant-shaped object (or None)."""
    tenant = (
        None
        if tenant_id is None
        else type("T", (), {"id": tenant_id, "slug": slug, "kind": kind, "name": "Acme"})()
    )
    return type("R", (), {"state": type("S", (), {"tenant": tenant})()})()


@pytest.fixture(autouse=True)
def _reset_host_tenant() -> Any:
    """Keep the host-tenant context var from leaking across tests."""
    from dazzle.back.runtime.tenant_isolation import _current_host_tenant_id

    token = _current_host_tenant_id.set(None)
    yield
    _current_host_tenant_id.reset(token)


_TID = "00000000-0000-0000-0000-000000000001"


class TestCurrentTenantDisplayGate:
    def _ctx(self, kind: str) -> dict:
        # #1394 review Finding 2: display injection is gated on the SAME host
        # context var as scope, so bind it before injecting.
        from dazzle.back.runtime.tenant_isolation import set_current_host_tenant_id

        set_current_host_tenant_id(_TID)
        ctx: dict = {}
        inject_current_tenant(ctx, _fake_request(_TID, kind=kind))
        return ctx

    def test_kind_match_visible(self) -> None:
        assert _gate("current_tenant.kind", "=", "trust", self._ctx("trust")) is True

    def test_kind_mismatch_hidden(self) -> None:
        assert _gate("current_tenant.kind", "=", "trust", self._ctx("school")) is False

    def test_slug_resolves(self) -> None:
        assert _gate("current_tenant.slug", "=", "acme", self._ctx("trust")) is True

    def test_bare_current_tenant_resolves_id(self) -> None:
        assert _gate("current_tenant", "=", _TID, self._ctx("trust")) is True

    def test_no_host_tenant_resolves_none(self) -> None:
        # Host context var unset (apex / non-tenant) → no injection → gate hides,
        # consistent with the scope path denying.
        empty: dict = {}
        inject_current_tenant(empty, _fake_request(_TID))  # var unset by fixture
        assert "current_tenant" not in empty
        assert _gate("current_tenant.kind", "=", "trust", empty) is False

    def test_invalid_attr_resolves_none(self) -> None:
        assert _gate("current_tenant.secret", "=", "x", self._ctx("trust")) is False


class TestInjectCurrentTenant:
    def test_populates_id_and_attrs(self) -> None:
        from dazzle.back.runtime.tenant_isolation import set_current_host_tenant_id

        set_current_host_tenant_id("abc")
        ctx: dict = {}
        inject_current_tenant(ctx, _fake_request("abc", slug="s", kind="trust"))
        assert ctx["current_tenant_id"] == "abc"
        assert ctx["current_tenant"] == {"id": "abc", "slug": "s", "kind": "trust", "name": "Acme"}

    def test_no_host_var_is_noop(self) -> None:
        # Even with request.state.tenant set, no host context var → no injection.
        ctx: dict = {}
        inject_current_tenant(ctx, _fake_request("abc"))
        assert ctx == {}

    def test_request_tenant_mismatch_exposes_id_only(self) -> None:
        # Host var binds tenant X but request.state.tenant is Y → expose id only
        # (the authoritative scope binding), never Y's slug/kind.
        from dazzle.back.runtime.tenant_isolation import set_current_host_tenant_id

        set_current_host_tenant_id("X")
        ctx: dict = {}
        inject_current_tenant(ctx, _fake_request("Y", slug="ywrong", kind="ykind"))
        assert ctx["current_tenant"]["id"] == "X"
        assert ctx["current_tenant"]["slug"] is None
        assert ctx["current_tenant"]["kind"] is None
