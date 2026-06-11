"""Unit tests for Phase C runtime — per-request ``dazzle.user_<attr>`` GUCs.

The scope policies (Task 2) read ``current_setting('dazzle.user_<attr>', true)``.
Task 3 wires the runtime to set those GUCs per transaction for the app-wide set
of referenced user attrs. These tests mirror the Phase B mock style in
``test_rls_runtime_context.py``:

  * the ``_current_rls_user_attrs`` contextvar carries the resolved per-request
    user-attr map;
  * ``_set_rls_user_attrs`` emits a parameterised ``set_config`` per attr (value
    as a bind param, never interpolated into the SQL string);
  * an unset/empty attr map → no ``set_config`` calls (fail-closed: each missing
    GUC denies its predicate);
  * the app-wide attr-name registry round-trips and stays a no-op when empty
    (non-shared_schema / no scope rules → nothing to set).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle.back.runtime.tenant_isolation import (
    _current_rls_user_attrs,
    _current_tenant_id,
    get_current_rls_user_attrs,
    get_rls_user_attr_names,
    register_rls_user_attr_names,
    set_current_rls_user_attrs,
)


@pytest.fixture(autouse=True)
def _reset_rls_context():
    """Keep this module hermetic — reset the RLS contextvars + registry per test.

    ``_bind_rls_tenant_id`` sets process/context state; without this reset a bind
    test would leak ``dazzle.tenant_id`` / ``dazzle.user_*`` into other modules'
    tests (e.g. Phase B's contextvar-roundtrip), making ordering-dependent.
    """
    tok_id = _current_tenant_id.set(None)
    tok_attrs = _current_rls_user_attrs.set(None)
    register_rls_user_attr_names(set())
    try:
        yield
    finally:
        _current_tenant_id.reset(tok_id)
        _current_rls_user_attrs.reset(tok_attrs)
        register_rls_user_attr_names(set())


def test_user_attrs_contextvar_roundtrip() -> None:
    assert get_current_rls_user_attrs() == {}
    tok = set_current_rls_user_attrs({"id": "u1", "school_id": "s1"})
    try:
        assert get_current_rls_user_attrs() == {"id": "u1", "school_id": "s1"}
    finally:
        _current_rls_user_attrs.reset(tok)
    assert get_current_rls_user_attrs() == {}


def test_attr_name_registry_roundtrip() -> None:
    """The app-wide attr-name set registered at startup round-trips."""
    register_rls_user_attr_names(set())
    assert get_rls_user_attr_names() == frozenset()
    register_rls_user_attr_names({"id", "school_id"})
    try:
        assert get_rls_user_attr_names() == frozenset({"id", "school_id"})
    finally:
        register_rls_user_attr_names(set())  # reset for isolation


def test_set_rls_user_attrs_emits_parameterised_set_config() -> None:
    from dazzle.back.runtime.pg_backend import _set_rls_user_attrs

    conn = MagicMock()
    _set_rls_user_attrs(conn, {"id": "u1", "school_id": "s1"})

    assert conn.execute.call_count == 2
    seen: dict[str, str] = {}
    for call in conn.execute.call_args_list:
        sql = str(call[0][0])
        params = call[0][1]
        assert "set_config" in sql
        # BOTH the GUC name and the value are bind params (%s) — neither is
        # interpolated into the SQL text. The SQL is the fixed
        # "SELECT set_config(%s, %s, true)" template for every attr.
        assert params[0] not in sql  # GUC name param (dazzle.user_<attr>)
        assert params[1] not in sql  # value param
        assert "u1" not in sql
        assert "s1" not in sql
        seen[params[0]] = params[1]
    # The runtime builds the name from the shared USER_GUC_PREFIX → dazzle.user_<attr>.
    assert seen == {"dazzle.user_id": "u1", "dazzle.user_school_id": "s1"}


def test_set_rls_user_attrs_value_is_bind_param_not_in_sql() -> None:
    """Adversarial: a value that looks like SQL must never reach the query string."""
    from dazzle.back.runtime.pg_backend import _set_rls_user_attrs

    conn = MagicMock()
    evil = "'; DROP TABLE users; --"
    _set_rls_user_attrs(conn, {"id": evil})

    assert conn.execute.call_count == 1
    sql = str(conn.execute.call_args[0][0])
    params = conn.execute.call_args[0][1]
    assert "DROP TABLE" not in sql
    assert params == ["dazzle.user_id", evil]


def test_set_rls_user_attrs_noop_when_empty() -> None:
    from dazzle.back.runtime.pg_backend import _set_rls_user_attrs

    conn = MagicMock()
    _set_rls_user_attrs(conn, {})
    assert not conn.execute.called  # nothing to set → each GUC stays unset → denies


def test_set_rls_user_attrs_noop_when_none() -> None:
    from dazzle.back.runtime.pg_backend import _set_rls_user_attrs

    conn = MagicMock()
    _set_rls_user_attrs(conn, None)
    assert not conn.execute.called


def test_bind_resolves_registered_attrs_into_contextvar(monkeypatch) -> None:
    """The auth dependency resolves each registered attr and stashes the map.

    Mirrors Phase B's tenant-id bind: ``__RBAC_DENY__``/None resolutions are
    skipped (their GUC stays unset → fail-closed).
    """
    from dazzle.back.runtime.auth import dependencies as deps

    register_rls_user_attr_names({"id", "school_id", "absent_attr"})
    try:
        resolved = {
            "id": "u1",
            "school_id": "s1",
            "absent_attr": "__RBAC_DENY__",
            "tenant_id": "t1",
        }

        def fake_resolve(attr: str, ctx) -> str:
            return resolved[attr]

        monkeypatch.setattr(
            "dazzle.back.runtime.scope_filters._resolve_user_attribute",
            fake_resolve,
        )

        auth_ctx = MagicMock()
        auth_ctx.is_authenticated = True
        auth_ctx.active_membership = None

        deps._bind_rls_tenant_id(auth_ctx)

        # tenant_id bound (Phase B behaviour preserved)
        from dazzle.back.runtime.tenant_isolation import get_current_tenant_id

        assert get_current_tenant_id() == "t1"
        # user attrs keyed by bare attr name: resolvable → set; DENY → omitted.
        attrs = get_current_rls_user_attrs()
        assert attrs == {"id": "u1", "school_id": "s1"}
        assert "absent_attr" not in attrs
    finally:
        register_rls_user_attr_names(set())


def test_bind_omits_empty_string_value(monkeypatch) -> None:
    """An attr resolving to '' is omitted, not set (companion §6.3).

    An empty-string GUC would survive ``current_setting`` (non-NULL) and then hit
    a hard ``::uuid`` cast error in the scope policy — so it must be dropped, same
    as ``__RBAC_DENY__`` (fail-closed: the predicate denies on the missing GUC).
    """
    from dazzle.back.runtime.auth import dependencies as deps

    register_rls_user_attr_names({"id"})
    try:

        def fake_resolve(attr: str, ctx) -> str:
            return "t1" if attr == "tenant_id" else ""

        monkeypatch.setattr(
            "dazzle.back.runtime.scope_filters._resolve_user_attribute",
            fake_resolve,
        )

        auth_ctx = MagicMock()
        auth_ctx.is_authenticated = True
        auth_ctx.active_membership = None
        deps._bind_rls_tenant_id(auth_ctx)

        assert "id" not in get_current_rls_user_attrs()
    finally:
        register_rls_user_attr_names(set())


def test_bind_noop_when_no_registered_attrs(monkeypatch) -> None:
    """No registered attrs (non-shared_schema / no scope rules) → user-attr map untouched.

    The autouse fixture leaves the contextvar at its ``None`` default; the dep
    must not bind a user-attr map, so ``get_current_rls_user_attrs()`` stays ``{}``
    (proving the dep left it alone — not that it actively set ``{}``).
    """
    from dazzle.back.runtime.auth import dependencies as deps

    register_rls_user_attr_names(set())

    def fake_resolve(attr: str, ctx) -> str:
        return "t1" if attr == "tenant_id" else "should-not-be-called"

    monkeypatch.setattr(
        "dazzle.back.runtime.scope_filters._resolve_user_attribute",
        fake_resolve,
    )

    auth_ctx = MagicMock()
    auth_ctx.is_authenticated = True
    auth_ctx.active_membership = None
    deps._bind_rls_tenant_id(auth_ctx)

    assert get_current_rls_user_attrs() == {}


def test_compute_app_wide_user_attr_names_union() -> None:
    """The app-wide set is the union of collect_user_attr_refs over every scope rule."""
    from dazzle.back.runtime.server import _compute_rls_user_attr_names
    from dazzle.core.ir.predicates import ColumnCheck, ValueRef

    # Two entities, each with one scope rule referencing a different attr.
    rule_a = MagicMock()
    rule_a.predicate = ColumnCheck(field="school_id", op="=", value=ValueRef(user_attr="school_id"))
    rule_b = MagicMock()
    rule_b.predicate = ColumnCheck(field="owner", op="=", value=ValueRef(current_user=True))

    ent_a = MagicMock()
    ent_a.access = MagicMock()
    ent_a.access.scopes = [rule_a]
    ent_b = MagicMock()
    ent_b.access = MagicMock()
    ent_b.access.scopes = [rule_b]
    ent_flat = MagicMock()
    ent_flat.access = None

    names = _compute_rls_user_attr_names([ent_a, ent_b, ent_flat])
    # current_user → "id"; current_user.school_id → "school_id"
    assert names == {"school_id", "id"}
