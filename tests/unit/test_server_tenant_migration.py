"""Tests for DazzleBackendApp._migrate_tenant_schemas (#1209).

Fail-closed invariant: under ``isolation = "schema"`` any per-tenant
migration failure must accumulate, log at ERROR, and raise a
``RuntimeError`` at the end of the loop so boot halts rather than
silently falling back to the ``public`` schema.

Note: ``_migrate_tenant_schemas`` is only called from the boot path when
``tenant_config.isolation == "schema"`` (see ``server.py`` ~line 725).
There is no isolation-mode branch inside the method itself, so the
"non-schema isolation should not raise" case is enforced at the call
site rather than inside the function under test — no test for that
guard is included here.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from dazzle.http.runtime.server import DazzleBackendApp


@dataclass
class _FakeTenant:
    """Minimal stand-in for ``TenantRecord`` — only fields the loop reads."""

    slug: str
    schema_name: str
    status: str = "active"


def _make_app_stub() -> DazzleBackendApp:
    """Build a bare ``DazzleBackendApp`` instance for unit-testing
    ``_migrate_tenant_schemas`` in isolation. Sidesteps the heavy
    real ``__init__`` and pins only the attributes the method touches.
    """
    app = DazzleBackendApp.__new__(DazzleBackendApp)
    app._database_url = "postgresql://localhost/test"  # type: ignore[attr-defined]
    app._entities = []  # type: ignore[attr-defined]
    fake_appspec = MagicMock()
    fake_appspec.surfaces = []
    app._appspec = fake_appspec  # type: ignore[attr-defined]
    return app


class _Counter:
    """Records every per-tenant migration attempt + selects which fail.

    Wired in as the side-effect of ``metadata.create_all`` so each
    invocation maps 1:1 to one tenant's per-loop iteration.
    """

    def __init__(self, fail_for: set[str]) -> None:
        self.fail_for = fail_for
        self.calls: list[str] = []
        self._current_schema: str | None = None

    def note_schema(self, schema: str) -> None:
        self._current_schema = schema

    def create_all(self, conn: object) -> None:
        schema = self._current_schema or "<unknown>"
        self.calls.append(schema)
        if schema in self.fail_for:
            raise RuntimeError(f"simulated migration failure for {schema}")


def _patched_run(
    tenants: list[_FakeTenant],
    counter: _Counter,
):
    """Yield an ExitStack with all patches applied; the caller invokes
    ``_migrate_tenant_schemas`` inside the ``with`` block."""

    stack = ExitStack()

    # 1. Patch TenantRegistry at its source module.
    fake_registry = MagicMock()
    fake_registry.ensure_table.return_value = None
    fake_registry.list.return_value = tenants
    stack.enter_context(
        patch(
            "dazzle.tenant.registry.TenantRegistry",
            return_value=fake_registry,
        )
    )

    # 2. Patch build_metadata at its source module — the production code
    #    imports it locally inside ``_migrate_tenant_schemas``, so the
    #    patch must target ``dazzle.http.runtime.sa_schema``.
    fake_metadata = MagicMock()
    fake_metadata.create_all.side_effect = counter.create_all
    stack.enter_context(
        patch(
            "dazzle.http.runtime.sa_schema.build_metadata",
            return_value=fake_metadata,
        )
    )

    # 3. Patch create_engine. The fake engine's connect() returns a
    #    context-manager-wrapped conn whose cursor's execute() records
    #    the schema identifier passed to ``SET search_path TO {}``.
    def _make_engine(*args: object, **kwargs: object) -> MagicMock:
        engine = MagicMock()

        def _connect() -> MagicMock:
            conn_ctx = MagicMock()
            conn = MagicMock()
            conn_ctx.__enter__.return_value = conn
            conn_ctx.__exit__.return_value = False

            cur = MagicMock()
            dbapi_conn = MagicMock()
            dbapi_conn.cursor.return_value = cur
            conn.connection = dbapi_conn

            def _execute(stmt: object) -> None:
                # The psycopg ``Composed`` is iterable; walk it and
                # pick the first ``Identifier`` we find. ``Identifier``
                # stores its identifier name(s) on the private ``_obj``
                # tuple (psycopg 3.x). Falling back to a repr-scan if
                # that contract ever shifts.
                try:
                    pieces = list(stmt)  # type: ignore[arg-type]
                except TypeError:
                    pieces = []
                for piece in pieces:
                    if type(piece).__name__ == "Identifier":
                        obj = getattr(piece, "_obj", None)
                        if obj:
                            counter.note_schema(obj[0])
                            return
                # Fallback: scan repr (shouldn't be needed in 3.x).
                counter.note_schema(str(stmt))

            cur.execute.side_effect = _execute
            return conn_ctx

        engine.connect.side_effect = _connect
        engine.dispose.return_value = None
        return engine

    stack.enter_context(patch("sqlalchemy.create_engine", side_effect=_make_engine))

    return stack


class TestMigrateTenantSchemasFailClosed:
    """#1209 — fail-closed under ``isolation = "schema"``."""

    def test_single_tenant_failure_raises(self) -> None:
        """One failing tenant → RuntimeError naming that schema."""
        app = _make_app_stub()
        tenants = [_FakeTenant(slug="alpha", schema_name="tenant_alpha")]
        counter = _Counter(fail_for={"tenant_alpha"})
        with _patched_run(tenants, counter):
            with pytest.raises(RuntimeError) as excinfo:
                app._migrate_tenant_schemas()
        msg = str(excinfo.value)
        assert "tenant_alpha" in msg
        assert "simulated migration failure" in msg
        assert "#1209" in msg
        assert counter.calls == ["tenant_alpha"]

    def test_multi_tenant_failure_aggregates(self) -> None:
        """Two of three tenants fail → RuntimeError names both, and the
        third tenant was still attempted before the raise."""
        app = _make_app_stub()
        tenants = [
            _FakeTenant(slug="alpha", schema_name="tenant_alpha"),
            _FakeTenant(slug="bravo", schema_name="tenant_bravo"),
            _FakeTenant(slug="charlie", schema_name="tenant_charlie"),
        ]
        counter = _Counter(fail_for={"tenant_alpha", "tenant_charlie"})
        with _patched_run(tenants, counter):
            with pytest.raises(RuntimeError) as excinfo:
                app._migrate_tenant_schemas()
        msg = str(excinfo.value)
        # Both failed schemas appear in the message.
        assert "tenant_alpha" in msg
        assert "tenant_charlie" in msg
        # The passing tenant is NOT in the failure list.
        assert "tenant_bravo" not in msg
        # All three tenants were still attempted (no early bail).
        assert counter.calls == ["tenant_alpha", "tenant_bravo", "tenant_charlie"]
        # Reports a count.
        assert "2 schema" in msg

    def test_all_clean_is_silent(self) -> None:
        """No tenant failures → no exception, function returns normally."""
        app = _make_app_stub()
        tenants = [
            _FakeTenant(slug="alpha", schema_name="tenant_alpha"),
            _FakeTenant(slug="bravo", schema_name="tenant_bravo"),
        ]
        counter = _Counter(fail_for=set())
        with _patched_run(tenants, counter):
            # No raise.
            app._migrate_tenant_schemas()
        assert counter.calls == ["tenant_alpha", "tenant_bravo"]

    def test_invalid_schema_name_counts_as_failure(self) -> None:
        """A schema name failing the identifier regex is a failure, not
        a silent skip — preserves the fail-closed invariant for the
        validator branch too."""
        app = _make_app_stub()
        tenants = [
            _FakeTenant(slug="bad", schema_name="tenant-with-dash"),
            _FakeTenant(slug="good", schema_name="tenant_good"),
        ]
        counter = _Counter(fail_for=set())
        with _patched_run(tenants, counter):
            with pytest.raises(RuntimeError) as excinfo:
                app._migrate_tenant_schemas()
        msg = str(excinfo.value)
        assert "tenant-with-dash" in msg
        assert "invalid schema name" in msg
        # The well-named tenant was still attempted.
        assert counter.calls == ["tenant_good"]

    def test_inactive_tenants_skipped(self) -> None:
        """Suspended/archived tenants do not participate in migration —
        and are not counted as failures."""
        app = _make_app_stub()
        tenants = [
            _FakeTenant(slug="active", schema_name="tenant_active"),
            _FakeTenant(slug="suspended", schema_name="tenant_suspended", status="suspended"),
        ]
        counter = _Counter(fail_for=set())
        with _patched_run(tenants, counter):
            app._migrate_tenant_schemas()
        assert counter.calls == ["tenant_active"]
