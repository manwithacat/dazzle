"""Smoke tests for route module imports.

Ensures that all route modules can be imported without NameError or
ImportError at the module level. This catches the class of bug where
removing `from __future__ import annotations` leaves TYPE_CHECKING-
guarded imports that are needed at runtime for type annotations.
"""

import importlib

import pytest

# Modules that define FastAPI route handlers or exception handlers.
# These are the ones where Pydantic/FastAPI introspects annotations at runtime.
ROUTE_MODULES = [
    "dazzle.http.runtime.auth",
    "dazzle.http.runtime.exception_handlers",
    "dazzle.http.runtime.site_routes",
    "dazzle.http.runtime.surface_access",
    "dazzle.http.runtime.tenant_middleware",
    "dazzle.http.runtime.debug_routes",
    "dazzle.http.runtime.event_explorer",
    "dazzle.http.runtime.route_generator",
    "dazzle.http.runtime.audit_routes",
    "dazzle.http.runtime.fragment_routes",
    "dazzle.http.runtime.realtime_routes",
    "dazzle.http.runtime.task_routes",
    "dazzle.http.runtime.test_routes",
    "dazzle.http.runtime.page_routes",
]


@pytest.mark.parametrize("module_path", ROUTE_MODULES, ids=lambda m: m.rsplit(".", 1)[-1])
def test_route_module_imports_cleanly(module_path: str) -> None:
    """Each route module should import without NameError or AttributeError.

    This catches TYPE_CHECKING imports that should be unconditional
    in modules where `from __future__ import annotations` was removed.
    """
    try:
        importlib.import_module(module_path)
    except (NameError, AttributeError) as exc:
        pytest.fail(
            f"{module_path} failed to import: {exc}\n"
            "Likely cause: a TYPE_CHECKING-guarded import is used in a "
            "runtime annotation after removing `from __future__ import annotations`."
        )
