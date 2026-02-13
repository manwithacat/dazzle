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
    "dazzle_back.runtime.auth",
    "dazzle_back.runtime.exception_handlers",
    "dazzle_back.runtime.site_routes",
    "dazzle_back.runtime.surface_access",
    "dazzle_back.runtime.tenant_middleware",
    "dazzle_back.runtime.debug_routes",
    "dazzle_back.runtime.event_explorer",
    "dazzle_back.runtime.route_generator",
    "dazzle_back.runtime.ops_routes",
    "dazzle_back.runtime.audit_routes",
    "dazzle_back.runtime.console_routes",
    "dazzle_back.runtime.deploy_routes",
    "dazzle_back.runtime.fragment_routes",
    "dazzle_back.runtime.realtime_routes",
    "dazzle_back.runtime.task_routes",
    "dazzle_back.runtime.test_routes",
    "dazzle_ui.runtime.page_routes",
    "dazzle_ui.runtime.container.auth",
    "dazzle_ui.runtime.container.test_routes",
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
