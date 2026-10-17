"""#1778: tenant-bound seam DML (`for_each_tenant`) + the upgrade RLS tripwire.

Unit half — fake binds / mocked cursors. The real-Postgres proof (tripwire
raises on unbound fenced DML; `for_each_tenant` inserts per tenant under it) is
``tests/integration/test_tenant_dml_pg.py``.
"""

import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dazzle.db.artifact_registry import DB_ARTIFACTS, RlsPosture
from dazzle.db.tenant_ids import TENANT_SOURCE_TABLE, iter_tenant_ids, tenant_exists
from dazzle.http.alembic.tenant_dml import RLS_TRIPWIRE_ATTR, for_each_tenant
from dazzle.http.runtime.rls_schema import TENANT_GUC

_ENV_PY = Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "alembic" / "env.py"


class _FakePsycopgConn:
    """Records every SQL string; answers the organizations reads."""

    def __init__(self, tenant_ids: list[str]) -> None:
        self.tenant_ids = tenant_ids
        self.queries: list[str] = []

    def execute(self, sql: str, params: Any = None) -> Any:
        self.queries.append(sql)
        rows = [(t,) for t in self.tenant_ids]
        if params is not None:
            rows = [r for r in rows if r[0] == params[0]]
        return SimpleNamespace(fetchall=lambda: rows, fetchone=lambda: rows[0] if rows else None)


class _FakeBind:
    """Just enough of a SQLAlchemy Connection for ``for_each_tenant``."""

    def __init__(self, counts: dict[str, int], *, row_security: str = "off") -> None:
        self.counts = counts
        self.row_security = row_security
        self.driver_calls: list[tuple[str, Any]] = []
        self.statements: list[tuple[str, str, dict[str, Any]]] = []
        self.current_tenant = ""
        self.dbapi = _FakePsycopgConn(list(counts))
        self.connection = SimpleNamespace(dbapi_connection=self.dbapi)

    def exec_driver_sql(self, sql: str, params: Any = None) -> Any:
        self.driver_calls.append((sql, params))
        if params is None:  # the row_security read
            return SimpleNamespace(scalar=lambda: self.row_security)
        name, value = params
        if name == TENANT_GUC:
            self.current_tenant = value
        elif name == "row_security":
            self.row_security = value
        return SimpleNamespace(rowcount=1)

    def execute(self, stmt: Any, params: dict[str, Any]) -> Any:
        assert self.row_security == "on", "DML must run with row_security on"
        self.statements.append((str(stmt), self.current_tenant, params))
        return SimpleNamespace(rowcount=self.counts[self.current_tenant])


def _run(bind: _FakeBind, sql: str = "INSERT INTO t SELECT 1", **kw: Any) -> dict[str, int]:
    with patch("alembic.op.get_bind", return_value=bind):
        return for_each_tenant(sql, **kw)


# ── tenant enumeration ────────────────────────────────────────────────────────


def test_tenant_source_is_unfenced_and_the_only_table_read() -> None:
    """Enumeration must never read a fenced table (it would see zero tenants)."""
    posture = {a.name: a.rls for a in DB_ARTIFACTS}
    assert posture[TENANT_SOURCE_TABLE] is RlsPosture.NON_FENCED

    conn = _FakePsycopgConn(["t-b", "t-a"])
    assert iter_tenant_ids(conn) == ["t-b", "t-a"]
    assert tenant_exists(conn, "t-a") is True
    assert tenant_exists(conn, "t-zz") is False
    for sql in conn.queries:
        assert f"FROM {TENANT_SOURCE_TABLE} " in sql
        assert sql.count("FROM") == 1 and "JOIN" not in sql.upper()


def test_iter_tenant_ids_accepts_dict_rows() -> None:
    conn = SimpleNamespace(
        execute=lambda sql: SimpleNamespace(fetchall=lambda: [{"id": "t-1"}, {"id": "t-2"}])
    )
    assert iter_tenant_ids(conn) == ["t-1", "t-2"]


# ── for_each_tenant ───────────────────────────────────────────────────────────


def test_for_each_tenant_binds_each_tenant_and_restores_state() -> None:
    bind = _FakeBind({"t-a": 3, "t-b": 2}, row_security="off")

    counts = _run(bind, "INSERT INTO t SELECT :x", params={"x": 1})

    assert counts == {"t-a": 3, "t-b": 2}
    # One execution per tenant, each with that tenant bound and the params passed.
    assert [(t, p) for _s, t, p in bind.statements] == [("t-a", {"x": 1}), ("t-b", {"x": 1})]
    # The tenant id only ever travels as a bind parameter to set_config.
    guc_sets = [p for s, p in bind.driver_calls if p is not None and p[0] == TENANT_GUC]
    assert guc_sets == [(TENANT_GUC, "t-a"), (TENANT_GUC, "t-b"), (TENANT_GUC, "")]
    assert all("t-a" not in s and "t-b" not in s for s, _p in bind.driver_calls)
    # row_security: forced on for the loop, then restored to the tripwire value.
    rs = [p[1] for _s, p in bind.driver_calls if p is not None and p[0] == "row_security"]
    assert rs == ["on", "off"]
    assert bind.current_tenant == ""


def test_for_each_tenant_restores_state_on_error() -> None:
    bind = _FakeBind({"t-a": 1})

    def _boom(stmt: Any, params: Any) -> Any:
        raise RuntimeError("statement failed")

    bind.execute = _boom  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="statement failed"):
        _run(bind)
    assert bind.current_tenant == ""
    assert bind.row_security == "off"


@pytest.mark.parametrize(
    ("counts", "warned"),
    [({"t-a": 0, "t-b": 0}, True), ({}, True), ({"t-a": 0, "t-b": 4}, False)],
    ids=["all_zero", "no_tenants", "some_rows"],
)
def test_for_each_tenant_warns_when_nothing_changed(
    counts: dict[str, int], warned: bool, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="dazzle.http.alembic.tenant_dml"):
        assert _run(_FakeBind(counts)) == counts
    assert any("affected 0 rows" in r.message for r in caplog.records) is warned


# ── env.py tripwire ───────────────────────────────────────────────────────────


def _load_env_module(attributes: dict[str, Any]) -> Any:
    """Import env.py against a mocked Alembic context (offline at import time)."""
    ctx = MagicMock()
    ctx.config.config_file_name = None
    ctx.config.get_main_option.return_value = "postgresql://u@h/db"
    ctx.config.attributes = attributes
    ctx.is_offline_mode.return_value = True
    spec = importlib.util.spec_from_file_location("_dazzle_env_under_test", _ENV_PY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with (
        patch("alembic.context", ctx),
        patch("dazzle.http.alembic.metadata_loader.load_target_metadata", side_effect=OSError),
    ):
        spec.loader.exec_module(module)
    return module, ctx


@pytest.mark.parametrize(
    ("attributes", "armed"),
    [({RLS_TRIPWIRE_ATTR: True}, True), ({}, False)],
    ids=["armed", "not_requested"],
)
def test_env_py_sets_row_security_off_only_when_requested(
    attributes: dict[str, Any], armed: bool
) -> None:
    module, ctx = _load_env_module(attributes)
    order = MagicMock()
    connection = MagicMock()
    cursor = connection.connection.cursor.return_value
    order.attach_mock(cursor.execute, "cursor_execute")
    order.attach_mock(ctx.run_migrations, "run_migrations")
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection

    with patch("sqlalchemy.create_engine", return_value=engine):
        module.run_migrations_online()

    calls = [c[0] for c in order.mock_calls]
    if armed:
        assert calls == ["cursor_execute", "run_migrations"], calls
        assert cursor.execute.call_args.args == ("SET LOCAL row_security = off",)
    else:
        assert calls == ["run_migrations"], calls


# ── seam text ─────────────────────────────────────────────────────────────────


def test_data_seam_points_at_for_each_tenant(tmp_path: Path) -> None:
    from dazzle.cli.db import _inject_data_seams
    from dazzle.db.schema_render import SEAM_MARKER

    rev = tmp_path / "abc_rev.py"
    rev.write_text(
        f"def upgrade():\n    op.execute('{SEAM_MARKER}')\n    op.alter_column('t', 'c')\n",
        encoding="utf-8",
    )

    _inject_data_seams(SimpleNamespace(path=str(rev)))

    text = rev.read_text(encoding="utf-8")
    assert SEAM_MARKER not in text
    assert "    # === DATA MIGRATION (hand-author) ===" in text
    assert "NO tenant" in text and "zero rows" in text
    assert "    #   from dazzle.http.alembic.tenant_dml import for_each_tenant" in text
    compile(text, str(rev), "exec")  # the block is comments only
