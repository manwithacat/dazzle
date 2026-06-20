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
    "dazzle.back.runtime.auth",
    "dazzle.back.runtime.exception_handlers",
    "dazzle.back.runtime.site_routes",
    "dazzle.back.runtime.surface_access",
    "dazzle.back.runtime.tenant_middleware",
    "dazzle.back.runtime.debug_routes",
    "dazzle.back.runtime.event_explorer",
    "dazzle.back.runtime.route_generator",
    "dazzle.back.runtime.audit_routes",
    "dazzle.back.runtime.fragment_routes",
    "dazzle.back.runtime.realtime_routes",
    "dazzle.back.runtime.task_routes",
    "dazzle.back.runtime.test_routes",
    "dazzle.back.runtime.page_routes",
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
