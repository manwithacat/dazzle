"""Shared test helpers for MCP handler tests.

MCP handler test files use ``importlib.util`` to import handler modules
directly (bypassing ``dazzle.mcp.__init__`` which depends on the ``mcp``
package).  Each test file mocks ``dazzle.mcp.server.handlers`` in
``sys.modules`` to satisfy relative imports.

Since handlers now import from ``.common``, the mock must also include
``dazzle.mcp.server.handlers.common``.  Use :func:`install_handlers_common_mock`
for a simple MagicMock, or :func:`install_handlers_common_real` when tests
need the real ``load_project_appspec`` (i.e. tests that create real DSL files).
"""

from __future__ import annotations

import json
import sys
from functools import wraps
from types import ModuleType
from unittest.mock import MagicMock


def _make_handler_error_json():  # noqa: ANN202
    """Create a ``handler_error_json`` decorator matching the real one."""

    def handler_error_json(fn):  # noqa: ANN001, ANN202
        @wraps(fn)
        def wrapper(*a, **kw):  # noqa: ANN002, ANN003, ANN202
            try:
                return fn(*a, **kw)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        return wrapper

    return handler_error_json


def _make_async_handler_error_json():  # noqa: ANN202
    """Create an ``async_handler_error_json`` decorator matching the real one."""

    def async_handler_error_json(fn):  # noqa: ANN001, ANN202
        @wraps(fn)
        async def wrapper(*a, **kw):  # noqa: ANN002, ANN003, ANN202
            try:
                return await fn(*a, **kw)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        return wrapper

    return async_handler_error_json


def install_handlers_common_mock() -> ModuleType:
    """Register a minimal ``handlers.common`` module.

    Suitable for tests that don't depend on real DSL parsing.
    Provides ``handler_error_json`` and ``async_handler_error_json``
    as real decorators so decorated handlers behave correctly.
    """
    common = ModuleType("dazzle.mcp.server.handlers.common")
    common.__package__ = "dazzle.mcp.server.handlers"

    def _extract_progress(args=None):  # noqa: ANN001, ANN202
        ctx = MagicMock()
        ctx.log_sync = MagicMock()
        return ctx

    _hej = _make_handler_error_json()
    _ahej = _make_async_handler_error_json()
    common.extract_progress = _extract_progress  # type: ignore[attr-defined]
    common.wrap_handler_errors = _hej  # type: ignore[attr-defined]
    common.wrap_async_handler_errors = _ahej  # type: ignore[attr-defined]
    # Backward-compatible aliases
    common.handler_error_json = _hej  # type: ignore[attr-defined]
    common.async_handler_error_json = _ahej  # type: ignore[attr-defined]

    sys.modules["dazzle.mcp.server.handlers.common"] = common
    return common


def install_handlers_common_real() -> ModuleType:
    """Register a ``handlers.common`` mock with *real* DSL loading.

    ``extract_progress`` returns a MagicMock progress context.
    ``load_project_appspec`` delegates to the real core modules.
    ``handler_error_json`` catches exceptions and returns JSON errors.

    Use this when tests create real ``dazzle.toml`` + ``.dsl`` files
    and expect actual parsing.
    """
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules

    common = ModuleType("dazzle.mcp.server.handlers.common")
    common.__package__ = "dazzle.mcp.server.handlers"

    def _extract_progress(args=None):  # noqa: ANN001, ANN202
        ctx = MagicMock()
        ctx.log_sync = MagicMock()
        return ctx

    def _load_project_appspec(project_root):  # noqa: ANN001, ANN202
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        return build_appspec(modules, manifest.project_root)

    _hej = _make_handler_error_json()
    _ahej = _make_async_handler_error_json()
    common.extract_progress = _extract_progress  # type: ignore[attr-defined]
    common.load_project_appspec = _load_project_appspec  # type: ignore[attr-defined]
    common.wrap_handler_errors = _hej  # type: ignore[attr-defined]
    common.wrap_async_handler_errors = _ahej  # type: ignore[attr-defined]
    # Backward-compatible aliases
    common.handler_error_json = _hej  # type: ignore[attr-defined]
    common.async_handler_error_json = _ahej  # type: ignore[attr-defined]

    sys.modules["dazzle.mcp.server.handlers.common"] = common
    return common
