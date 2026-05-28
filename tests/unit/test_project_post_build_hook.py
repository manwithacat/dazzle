"""Tests for the project post-build middleware-injection hook (#1290)."""

from __future__ import annotations

import logging
import sys
import types

import pytest

from dazzle.back.runtime.app_factory import (
    _PROJECT_INIT_MODULE,
    _invoke_project_post_build_hook,
)


@pytest.fixture
def cleanup_project_module():
    """Remove any test-installed pipeline.serve.app_init from sys.modules."""
    yield
    for name in list(sys.modules):
        if name == _PROJECT_INIT_MODULE or name.startswith(_PROJECT_INIT_MODULE + "."):
            del sys.modules[name]
    for parent in ("pipeline.serve", "pipeline"):
        sys.modules.pop(parent, None)


def _install_project_module(register_middleware=None, **extra_attrs):
    """Install a fake pipeline.serve.app_init module exposing the given hook."""
    pipeline = sys.modules.setdefault("pipeline", types.ModuleType("pipeline"))
    serve = sys.modules.setdefault("pipeline.serve", types.ModuleType("pipeline.serve"))
    pipeline.serve = serve  # type: ignore[attr-defined]
    app_init = types.ModuleType(_PROJECT_INIT_MODULE)
    if register_middleware is not None:
        app_init.register_middleware = register_middleware  # type: ignore[attr-defined]
    for key, value in extra_attrs.items():
        setattr(app_init, key, value)
    sys.modules[_PROJECT_INIT_MODULE] = app_init
    serve.app_init = app_init  # type: ignore[attr-defined]


def test_no_project_module_is_silent_noop(cleanup_project_module, caplog):
    """Most projects don't ship pipeline.serve.app_init; absence is a no-op."""
    caplog.set_level(logging.DEBUG, logger="dazzle.back.runtime.app_factory")
    sentinel_app = object()
    _invoke_project_post_build_hook(sentinel_app)  # type: ignore[arg-type]
    assert any("No project post-build hook" in r.message for r in caplog.records)


def test_module_without_register_middleware_is_noop(cleanup_project_module, caplog):
    """Module exists but doesn't expose the hook callable — debug log, no crash."""
    caplog.set_level(logging.DEBUG, logger="dazzle.back.runtime.app_factory")
    _install_project_module(register_middleware=None, other_attr=lambda: None)
    sentinel_app = object()
    _invoke_project_post_build_hook(sentinel_app)  # type: ignore[arg-type]
    assert any("has no register_middleware" in r.message for r in caplog.records)


def test_hook_is_invoked_with_app(cleanup_project_module):
    """When the hook is present, it receives the FastAPI app instance."""
    received: list[object] = []

    def fake_register(app):
        received.append(app)

    _install_project_module(register_middleware=fake_register)
    sentinel_app = object()
    _invoke_project_post_build_hook(sentinel_app)  # type: ignore[arg-type]
    assert received == [sentinel_app]


def test_hook_exception_propagates(cleanup_project_module):
    """A broken hook must not silently fail — re-raise so the operator sees it."""

    def broken_register(app):
        raise RuntimeError("project hook is broken")

    _install_project_module(register_middleware=broken_register)
    with pytest.raises(RuntimeError, match="project hook is broken"):
        _invoke_project_post_build_hook(object())  # type: ignore[arg-type]
