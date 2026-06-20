"""Unit tests for RLS runtime context + apply gating (Phase B)."""

from __future__ import annotations

from unittest.mock import MagicMock

from dazzle.http.runtime.tenant_isolation import (
    _current_tenant_id,
    get_current_tenant_id,
    set_current_tenant_id,
)


def test_tenant_id_contextvar_roundtrip() -> None:
    assert get_current_tenant_id() is None
    tok = set_current_tenant_id("11111111-1111-1111-1111-111111111111")
    try:
        assert get_current_tenant_id() == "11111111-1111-1111-1111-111111111111"
    finally:
        _current_tenant_id.reset(tok)
    assert get_current_tenant_id() is None


def test_set_tenant_context_emits_set_config_when_id_present() -> None:
    from dazzle.http.runtime.pg_backend import _set_tenant_context

    conn = MagicMock()
    _set_tenant_context(conn, "abc")
    # parameterised set_config(..., true); never SET LOCAL string-interpolation
    assert conn.execute.called
    args = conn.execute.call_args
    sql = str(args[0][0])
    assert "set_config" in sql and "dazzle.tenant_id" in sql
    # value passed as a bind parameter, not interpolated
    assert "abc" not in sql
    # the value is a positional bind param
    assert args[0][1] == ["abc"]


def test_set_tenant_context_noop_when_id_none() -> None:
    from dazzle.http.runtime.pg_backend import _set_tenant_context

    conn = MagicMock()
    _set_tenant_context(conn, None)
    assert not conn.execute.called  # unset → fail-closed (fence denies), nothing set


def test_apply_rls_policies_noop_when_no_tenancy() -> None:
    """_apply_rls_policies must not touch the engine when tenancy is None."""
    from dazzle.http.runtime.server import DazzleBackendApp

    app = MagicMock(spec=DazzleBackendApp)
    app._appspec = MagicMock()
    app._appspec.tenancy = None
    app._entities = []  # build_all_rls_ddl takes (appspec, entities); gate is on tenancy

    engine = MagicMock()
    DazzleBackendApp._apply_rls_policies(app, engine)

    assert not engine.begin.called  # no DDL when tenancy absent


def test_apply_rls_policies_noop_when_not_shared_schema() -> None:
    """_apply_rls_policies must no-op for non-shared_schema isolation modes."""
    from dazzle.core.ir import TenancyMode
    from dazzle.http.runtime.server import DazzleBackendApp

    app = MagicMock(spec=DazzleBackendApp)
    app._appspec = MagicMock()
    app._appspec.tenancy = MagicMock()
    app._appspec.tenancy.isolation.mode = TenancyMode.SCHEMA_PER_TENANT
    app._entities = []  # build_all_rls_ddl takes (appspec, entities); gate is on mode

    engine = MagicMock()
    DazzleBackendApp._apply_rls_policies(app, engine)

    assert not engine.begin.called  # only shared_schema gets the fence


def test_apply_rls_failure_propagates_out_of_setup_database() -> None:
    """C-1: an RLS-apply failure must HALT boot, not be swallowed by the
    tolerant dev-mode create_all try/except (which would boot fence-less).
    """
    from unittest.mock import patch

    import pytest

    from dazzle.http.runtime.server import DazzleBackendApp

    app = MagicMock(spec=DazzleBackendApp)
    app._database_url = "postgresql://localhost/x"
    app._entities = []
    app._appspec = MagicMock()
    app._appspec.surfaces = []
    # _apply_rls_policies blows up (e.g. permissions / DDL error).
    app._apply_rls_policies.side_effect = RuntimeError("fence DDL failed")
    app._should_create_schema_on_startup.return_value = True

    with (
        patch("dazzle.http.runtime.pg_backend.PostgresBackend"),
        patch("sqlalchemy.create_engine"),
        patch("dazzle.http.runtime.sa_schema.build_metadata"),
        patch("dazzle.http.runtime.server._tenancy_metadata_kwargs", return_value={}),
        pytest.raises(RuntimeError, match="fence DDL failed"),
    ):
        DazzleBackendApp._setup_database(app)

    # The tolerant create_all/_apply_search_indexes path must NOT swallow it.
    assert app._apply_rls_policies.called
