"""Tests for the FastAPI lifespan that replaced the deprecated on_event hooks.

These assert the *behaviour* the lifespan must preserve: entering opens the DB
pool (and starts the audit logger when one is configured); exiting closes the
pool (and awaits the audit logger's stop). Getting this wrong silently breaks
startup (pool never opens) or the audit trail (logger never starts), so the
tests spy on the real side-effect calls rather than only checking for the
absence of the deprecation warning.
"""

from __future__ import annotations

import warnings
from unittest.mock import AsyncMock, MagicMock

from dazzle.core import ir
from dazzle.http.runtime.server import DazzleBackendApp, ServerConfig


def _make_appspec() -> ir.AppSpec:
    entity = ir.EntitySpec(
        name="Task",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                modifiers=[ir.FieldModifier.REQUIRED],
            ),
        ],
    )
    return ir.AppSpec(name="test_app", domain=ir.DomainSpec(entities=[entity]))


def _make_builder_with_app() -> DazzleBackendApp:
    """Construct a builder and its FastAPI app (which carries the lifespan).

    ``_create_app`` wires ``lifespan=self._lifespan`` at construction; the
    lifespan reads instance state (``self._db_manager`` / ``self._audit_logger``)
    only when it *runs* at startup, so the test sets those after construction.
    """
    builder = DazzleBackendApp(
        _make_appspec(),
        config=ServerConfig(database_url="postgresql://example/test"),
    )
    builder._create_app()
    return builder


async def test_lifespan_opens_and_closes_pool_with_audit_logger() -> None:
    """Audit-configured path: enter opens pool + starts logger; exit awaits
    stop then closes pool."""
    builder = _make_builder_with_app()
    db_manager = MagicMock()
    audit_logger = MagicMock()
    audit_logger.stop = AsyncMock()
    builder._db_manager = db_manager
    builder._audit_logger = audit_logger

    assert builder._app is not None
    async with builder._app.router.lifespan_context(builder._app):
        # Startup side effects fired on enter.
        db_manager.open_pool.assert_called_once()
        _, kwargs = db_manager.open_pool.call_args
        assert kwargs == {"min_size": 2, "max_size": 10}
        audit_logger.start.assert_called_once()
        # Not yet shut down.
        audit_logger.stop.assert_not_awaited()
        db_manager.close_pool.assert_not_called()

    # Shutdown side effects fired on exit.
    audit_logger.stop.assert_awaited_once()
    db_manager.close_pool.assert_called_once()


async def test_lifespan_without_audit_logger() -> None:
    """Audit-absent path: pool still opens/closes; no audit start/stop attempted."""
    builder = _make_builder_with_app()
    db_manager = MagicMock()
    builder._db_manager = db_manager
    builder._audit_logger = None

    assert builder._app is not None
    async with builder._app.router.lifespan_context(builder._app):
        db_manager.open_pool.assert_called_once()
        db_manager.close_pool.assert_not_called()

    db_manager.close_pool.assert_called_once()


async def test_lifespan_honours_pool_env_overrides(monkeypatch) -> None:
    """DAZZLE_DB_POOL_MIN/MAX are read at startup time, inside the lifespan."""
    monkeypatch.setenv("DAZZLE_DB_POOL_MIN", "5")
    monkeypatch.setenv("DAZZLE_DB_POOL_MAX", "42")
    builder = _make_builder_with_app()
    db_manager = MagicMock()
    builder._db_manager = db_manager
    builder._audit_logger = None

    assert builder._app is not None
    async with builder._app.router.lifespan_context(builder._app):
        pass

    _, kwargs = db_manager.open_pool.call_args
    assert kwargs == {"min_size": 5, "max_size": 42}


async def test_lifespan_emits_no_on_event_deprecation_warning() -> None:
    """Constructing the app and driving the lifespan emits no
    'on_event is deprecated' warning.

    FastAPI raises that warning at handler *registration* time, so we capture
    around both ``_create_app`` (where the app + lifespan are wired) and the
    lifespan run.
    """
    builder = DazzleBackendApp(
        _make_appspec(),
        config=ServerConfig(database_url="postgresql://example/test"),
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        builder._create_app()
        builder._db_manager = MagicMock()
        builder._audit_logger = None
        assert builder._app is not None
        async with builder._app.router.lifespan_context(builder._app):
            pass

    messages = [str(w.message) for w in caught]
    assert not any("on_event is deprecated" in m for m in messages), messages
