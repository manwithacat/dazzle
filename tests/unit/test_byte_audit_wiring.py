# tests/unit/test_byte_audit_wiring.py
"""#1551 review fix — byte_audit wired on the file-serving predicate, not only
when _has_auditable_entities.

Tests exercise DazzleBackendApp._wire_byte_audit directly via the MagicMock
pattern (same approach as test_rls_runtime_context.py) so no full boot / DB
is required.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI

from dazzle.http.runtime.byte_serving import ByteAudit
from dazzle.http.runtime.server import DazzleBackendApp


def _server(
    *,
    file_service_present: bool = True,
    database_url: str | None = "postgresql://test/db",
    audit_integrity: bool = False,
) -> tuple[MagicMock, FastAPI]:
    """Build a minimal DazzleBackendApp mock for _wire_byte_audit tests."""
    fa = FastAPI()
    srv = MagicMock(spec=DazzleBackendApp)
    srv._app = fa
    srv._file_service = object() if file_service_present else None
    srv._database_url = database_url
    srv._config = SimpleNamespace(audit_integrity=audit_integrity)
    srv._audit_logger = None
    return srv, fa


class _StubLogger:
    """Minimal AuditLogger stand-in: exposes async log_decision."""

    async def log_decision(self, **kw: object) -> None:
        pass


# ---------------------------------------------------------------------------
# Case 1: no file service → byte_audit never set (no document routes mount)
# ---------------------------------------------------------------------------


def test_no_file_service_noop() -> None:
    """_wire_byte_audit is a no-op when _file_service is absent."""
    srv, fa = _server(file_service_present=False)
    DazzleBackendApp._wire_byte_audit(srv, None)
    assert not hasattr(fa.state, "byte_audit")


# ---------------------------------------------------------------------------
# Case 2: file service present, audit_logger=None, no database → no-op
# (can't audit without a sink; serve_bytes already handles audit=None)
# ---------------------------------------------------------------------------


def test_file_service_no_db_noop() -> None:
    """No database configured → cannot create AuditLogger → byte_audit unset."""
    srv, fa = _server(database_url=None)
    DazzleBackendApp._wire_byte_audit(srv, None)
    assert not hasattr(fa.state, "byte_audit")


# ---------------------------------------------------------------------------
# Case 3 — THE BUG CASE: file service present, audit_logger=None (because
# _has_auditable_entities was False), but a database IS available.
# Before the fix byte_audit stayed None → silently unaudited byte access.
# ---------------------------------------------------------------------------


def test_file_service_with_db_constructs_logger_and_wires_byte_audit() -> None:
    """Key regression guard: audit_logger=None + _file_service set + DB present
    → _wire_byte_audit constructs an AuditLogger and sets app.state.byte_audit."""
    srv, fa = _server()
    stub = _StubLogger()

    with patch("dazzle.http.runtime.audit_log.AuditLogger", return_value=stub):
        DazzleBackendApp._wire_byte_audit(srv, None)  # audit_logger=None

    assert isinstance(fa.state.byte_audit, ByteAudit)
    # The freshly constructed logger is stored on the server instance too
    assert srv._audit_logger is stub


# ---------------------------------------------------------------------------
# Case 4: audit_logger already set (from _has_auditable_entities block) →
# reused, no second AuditLogger constructed.
# ---------------------------------------------------------------------------


def test_existing_audit_logger_reused_no_double_construction() -> None:
    """When audit_logger is already available (auditable entities exist),
    _wire_byte_audit reuses it and does NOT construct a second AuditLogger."""
    srv, fa = _server()
    existing_logger = _StubLogger()

    with patch("dazzle.http.runtime.audit_log.AuditLogger") as mock_al:
        DazzleBackendApp._wire_byte_audit(srv, existing_logger)

    mock_al.assert_not_called()  # no second construction
    assert isinstance(fa.state.byte_audit, ByteAudit)
    # _audit_logger NOT overwritten when we reuse the existing one
    assert srv._audit_logger is None  # mock didn't set it; existing was reused inline
