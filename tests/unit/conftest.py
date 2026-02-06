"""Conftest for unit tests — sys.modules isolation.

Several MCP handler test files replace real modules in ``sys.modules`` with
MagicMock objects at import time (during pytest collection).  Without cleanup
these mocks leak into subsequently-collected test modules, causing import
errors and assertion failures for unrelated tests.

**How it works:**

1. ``pytest_configure`` — snapshot tracked ``sys.modules`` entries before any
   test file is imported.
2. ``pytest_collectreport`` — after each test module is collected (imported),
   diff ``sys.modules`` against the snapshot, stash the diff per-module, then
   restore the snapshot so the *next* module sees a clean namespace.
3. A module-scoped autouse fixture re-establishes the stashed mocks before that
   module's tests execute and tears them down afterwards.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Prefixes of sys.modules entries that test files might pollute.
# ---------------------------------------------------------------------------
_TRACKED_PREFIXES = (
    "dazzle.mcp.",
    "dazzle.mcp",
    "dazzle.api_kb",
    "dazzle_back.runtime.control_plane",
    "dazzle.core.sitespec_loader",
    "dazzle.core.copy_parser",
    "dazzle.core.site_coherence",
    "mcp.",
    "mcp",
    # Temporary module names used by spec_from_file_location
    "contribution_module",
    "event_first_tools_module",
    "process_module",
    "setup_module",
)


def _is_tracked(name: str) -> bool:
    if name in ("mcp", "dazzle.mcp"):
        return True
    return any(name.startswith(p) for p in _TRACKED_PREFIXES)


def _is_mock(obj: object) -> bool:
    """Return True if *obj* is a unittest.mock object (MagicMock, etc.)."""
    return type(obj).__module__ == "unittest.mock"


# Clean snapshot taken at session start.
_clean: dict[str, Any] = {}

# Per-module stashed diffs:  nodeid -> {module_name: module_or_mock}
_module_diffs: dict[str, dict[str, Any]] = {}


def pytest_configure(config: object) -> None:
    """Snapshot tracked sys.modules entries at session startup."""
    for name in list(sys.modules):
        if _is_tracked(name):
            _clean[name] = sys.modules[name]


def _clean_parent_attr(name: str) -> None:
    """Remove stale mock attribute on a parent package.

    After ``del sys.modules["a.b.c"]``, the ``a.b`` module object may still
    hold ``c`` as an attribute pointing at the now-removed mock.  This
    prevents Python's import machinery from re-importing ``a.b.c`` fresh.
    """
    parts = name.rsplit(".", 1)
    if len(parts) != 2:
        return
    parent_name, child = parts
    parent = sys.modules.get(parent_name)
    if parent is None:
        return
    child_attr = getattr(parent, child, None)
    if child_attr is not None and _is_mock(child_attr):
        try:
            delattr(parent, child)
        except AttributeError:
            pass


def _restore_clean() -> None:
    """Restore sys.modules to the clean snapshot."""
    # Remove entries added since the snapshot
    for name in list(sys.modules):
        if _is_tracked(name) and name not in _clean:
            del sys.modules[name]
            _clean_parent_attr(name)
    # Restore entries that were modified
    for name, val in _clean.items():
        if sys.modules.get(name) is not val:
            sys.modules[name] = val


def pytest_collectreport(report: Any) -> None:
    """After each test module collection, stash its diffs and restore clean state."""
    # Only care about Python test files
    nodeid = getattr(report, "nodeid", "")
    if not nodeid.endswith(".py"):
        return

    # Compute diff: which tracked entries were added or changed?
    diff: dict[str, Any] = {}
    for name in list(sys.modules):
        if _is_tracked(name):
            if name not in _clean:
                diff[name] = sys.modules[name]
            elif sys.modules[name] is not _clean[name]:
                diff[name] = sys.modules[name]

    if diff:
        _module_diffs[nodeid] = diff

    # Restore clean state for the next module's collection
    _restore_clean()


@pytest.fixture(autouse=True, scope="module")
def _manage_sys_modules_mocks(request: pytest.FixtureRequest) -> Any:
    """Re-establish this module's sys.modules mocks during test execution."""
    # Find our stashed diff by matching the file path to a nodeid.
    fspath = str(request.fspath)
    mocks: dict[str, Any] | None = None
    for nodeid, diff in _module_diffs.items():
        # nodeid is relative (e.g. "tests/unit/mcp/test_foo.py")
        # fspath is absolute; check suffix match
        normalized = nodeid.replace("/", os.sep)
        if fspath.endswith(normalized):
            mocks = diff
            break

    if not mocks:
        yield
        return

    # Re-establish the mocks and record what we displaced
    displaced: dict[str, Any | None] = {}
    for k, v in mocks.items():
        displaced[k] = sys.modules.get(k)
        sys.modules[k] = v

    yield

    # Tear down: restore exactly what was there before
    for k, prev in displaced.items():
        if prev is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = prev
        _clean_parent_attr(k)
