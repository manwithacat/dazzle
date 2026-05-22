"""Regression guard for #1187.

`dazzle e2e run-viewport` failed with `ModuleNotFoundError: dazzle.core.loader`
because `handlers/viewport_testing.py` imported a module that no longer exists.
Nothing imported the MCP handler modules in tests, so the stale import shipped
unnoticed. Importing every handler module here makes a broken import fail fast.
"""

import importlib
import pkgutil

import dazzle.mcp.server.handlers as handlers_pkg


def test_all_mcp_handler_modules_import() -> None:
    failures: list[str] = []
    for mod in pkgutil.iter_modules(handlers_pkg.__path__):
        name = f"{handlers_pkg.__name__}.{mod.name}"
        try:
            importlib.import_module(name)  # nosemgrep — name is from pkgutil over a fixed pkg
        except Exception as exc:  # noqa: BLE001 — collect every failure, not just the first
            failures.append(f"{name}: {exc!r}")
    assert not failures, "MCP handler modules failed to import:\n" + "\n".join(failures)
