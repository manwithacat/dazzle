"""#1462: framework stores skip boot schema DDL in production (non-owner serve).

Under shared_schema RLS the runtime serves as a non-owner role (dazzle_app,
NOSUPERUSER NOBYPASSRLS) so RLS is enforced — but that role cannot run
CREATE/ALTER/CREATE INDEX. AuthStore / FileMetadataStore / AuditLogger used to
run owner-only DDL in `_init_db` at every boot, halting a non-owner startup.
They now skip that DDL in production (the schema is migration-managed there), via
`skip_boot_schema_ddl()`. The `users_email_lower_key` case-insensitive email index
that `_init_db` used to create is now part of the migration-managed schema
(framework_schema + the ADR-0044 parity gate proves it), so gating loses nothing.
"""

from __future__ import annotations

import pytest

from dazzle.core.environment import skip_boot_schema_ddl
from dazzle.http.runtime.audit_log import AuditLogger
from dazzle.http.runtime.auth.store import AuthStore
from dazzle.http.runtime.file_storage import FileMetadataStore

pytestmark = pytest.mark.gate


def test_skip_boot_schema_ddl_tracks_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAZZLE_ENV", "production")
    assert skip_boot_schema_ddl() is True
    monkeypatch.setenv("DAZZLE_ENV", "development")
    assert skip_boot_schema_ddl() is False


def _boom() -> None:
    raise AssertionError("_init_db opened a DB connection — boot DDL was NOT gated")


@pytest.mark.parametrize("store_cls", [AuthStore, FileMetadataStore, AuditLogger])
def test_init_db_runs_no_ddl_in_production(
    store_cls: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In production every framework store's _init_db must short-circuit before
    touching the database (no CREATE/ALTER) — proven by making any connection
    attempt fail."""
    monkeypatch.setenv("DAZZLE_ENV", "production")
    store = store_cls.__new__(store_cls)  # bypass __init__; exercise _init_db in isolation
    # Boom BOTH connection seams: stores hardened in #1504 connect via _connect_raw,
    # others still via _get_connection — either being called would fail the test.
    monkeypatch.setattr(store, "_get_connection", _boom, raising=False)
    monkeypatch.setattr(store, "_connect_raw", _boom, raising=False)
    store._init_db()  # must return cleanly without opening a connection


def test_init_db_runs_ddl_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside production the gate is open — _init_db DOES try to connect (the
    pre-#1462 behaviour is preserved for dev, where no migrations run)."""
    monkeypatch.setenv("DAZZLE_ENV", "development")
    store = AuthStore.__new__(AuthStore)
    called: list[bool] = []

    def _record() -> None:
        called.append(True)
        raise RuntimeError("stop after connect attempt")

    # #1504: _init_db connects via _connect_raw (runs under the init lock, must
    # not re-enter ensure_initialized).
    monkeypatch.setattr(store, "_connect_raw", _record, raising=False)
    with pytest.raises(RuntimeError, match="stop after connect"):
        store._init_db()
    assert called, "dev path must attempt boot DDL"
