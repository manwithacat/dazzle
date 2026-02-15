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

import sys
from types import ModuleType
from unittest.mock import MagicMock


def install_handlers_common_mock() -> ModuleType:
    """Register a MagicMock-based ``handlers.common`` module.

    Suitable for tests that don't depend on real DSL parsing.
    """
    sys.modules["dazzle.mcp.server.handlers.common"] = MagicMock()
    return sys.modules["dazzle.mcp.server.handlers.common"]  # type: ignore[return-value]


def install_handlers_common_real() -> ModuleType:
    """Register a ``handlers.common`` mock with *real* DSL loading.

    ``extract_progress`` returns a MagicMock progress context.
    ``load_project_appspec`` delegates to the real core modules.
    ``handler_error_json`` is an identity decorator.

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

    common.extract_progress = _extract_progress  # type: ignore[attr-defined]
    common.load_project_appspec = _load_project_appspec  # type: ignore[attr-defined]
    common.handler_error_json = lambda fn: fn  # type: ignore[attr-defined]

    sys.modules["dazzle.mcp.server.handlers.common"] = common
    return common
