"""Regression guard for #1187.

`dazzle e2e run-viewport` failed with `ModuleNotFoundError: dazzle.core.loader`
because `handlers/viewport_testing.py` imported a module that no longer exists.
Nothing imported the MCP handler modules in tests, so the stale import shipped
unnoticed. Importing every handler module here makes a broken import fail fast.
"""

import importlib
import pkgutil
import sys

import dazzle.mcp.server.handlers as handlers_pkg


def test_all_mcp_handler_modules_import() -> None:
    # The package imports nothing eagerly, so the modules loaded here would
    # otherwise outlive this test bound to this module's copy of the server
    # state (tests/unit/conftest.py re-stashes ``dazzle.mcp.*`` per module).
    before = set(sys.modules)
    failures: list[str] = []
    try:
        for mod in pkgutil.iter_modules(handlers_pkg.__path__):
            name = f"{handlers_pkg.__name__}.{mod.name}"
            try:
                importlib.import_module(name)  # nosemgrep — name is from pkgutil over a fixed pkg
            except Exception as exc:  # noqa: BLE001 — collect every failure, not just the first
                failures.append(f"{name}: {exc!r}")
    finally:
        for name in set(sys.modules) - before:
            if name.startswith(handlers_pkg.__name__ + "."):
                del sys.modules[name]
                parent_name, _, child = name.rpartition(".")
                parent = sys.modules.get(parent_name)
                if parent is not None and hasattr(parent, child):
                    delattr(parent, child)
    assert not failures, "MCP handler modules failed to import:\n" + "\n".join(failures)
