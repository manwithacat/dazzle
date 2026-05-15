"""Issue #1034 (v0.67.1): regression tests for the workspace + page
handler signature contract.

Pre-fix, both `_make_page_handler` and the workspace-route handler
construction used `functools.partial(...)` which strips type
annotations from `inspect.signature`. FastAPI then saw `request`
as an un-annotated parameter, defaulted it to `Query(...)`, and on
pydantic >= 2.13 hard-failed building a `TypeAdapter` for the
`Request` forward-ref — every `/app/workspaces/{name}` route
returned HTTP 422.

Fix: closure factories that wrap the inner handler in an
`async def handler(request: Request)` so the annotation survives
the `__signature__` introspection FastAPI performs at route-
registration time."""

from __future__ import annotations

import inspect

from fastapi import Request

from dazzle.ui.runtime.page_routes import (
    _make_page_handler,
    _make_workspace_handler,
)


class _DummyDeps:
    """Minimal stand-in for `_PageRouterConfig` — handlers don't unpack
    fields at signature-introspection time."""

    pass


def test_make_page_handler_preserves_request_annotation() -> None:
    """The closure-factory must expose `request: Request` so FastAPI's
    dependency-resolution path treats it as a request parameter, not
    a query parameter. Pre-fix `partial(...)` returned a callable
    whose `inspect.signature` had `request` with empty annotation."""
    handler = _make_page_handler(_DummyDeps(), "/x", _DummyDeps(), None)
    sig = inspect.signature(handler)
    request_param = sig.parameters.get("request")
    assert request_param is not None, "handler is missing `request` parameter"
    assert request_param.annotation is Request, (
        f"expected request: Request, got {request_param.annotation!r}"
    )


def test_make_workspace_handler_preserves_request_annotation() -> None:
    """Same contract for the workspace-route handler factory.
    Pre-fix this was the route producing the 422 — `partial` stripped
    the annotation and pydantic 2.13 then failed on the forward-ref."""
    handler = _make_workspace_handler(
        deps=_DummyDeps(),
        ws_ctx=_DummyDeps(),
        ws_route="/workspaces/x",
        ws_allowed_personas=[],
        ws_nav_items=[],
        ws_entity_items=[],
        ws_nav_groups=[],
        ws_app_name="test_app",
        primary_action_candidates=[],
    )
    sig = inspect.signature(handler)
    request_param = sig.parameters.get("request")
    assert request_param is not None
    assert request_param.annotation is Request


def test_make_page_handler_returns_callable_with_only_request_param() -> None:
    """The bound state (deps, route_path, ctx, view_name) is captured
    in the closure — only `request` should appear in the signature.
    FastAPI then has no other parameters to misinterpret as Query."""
    handler = _make_page_handler(_DummyDeps(), "/x", _DummyDeps(), "view_x")
    params = list(inspect.signature(handler).parameters.keys())
    assert params == ["request"]


def test_make_workspace_handler_returns_callable_with_only_request_param() -> None:
    """Same — workspace handler exposes only `request` outwardly.
    All per-workspace state (ws_ctx, ws_route, etc.) is in the closure."""
    handler = _make_workspace_handler(
        deps=_DummyDeps(),
        ws_ctx=_DummyDeps(),
        ws_route="/workspaces/x",
        ws_allowed_personas=[],
        ws_nav_items=[],
        ws_entity_items=[],
        ws_nav_groups=[],
        ws_app_name="t",
        primary_action_candidates=[],
    )
    params = list(inspect.signature(handler).parameters.keys())
    assert params == ["request"]


def test_handler_factories_produce_async_callables() -> None:
    """FastAPI requires `async def` handlers (or sync that get
    auto-wrapped). The closure factories return `async def` directly."""
    page_handler = _make_page_handler(_DummyDeps(), "/x", _DummyDeps(), None)
    ws_handler = _make_workspace_handler(
        deps=_DummyDeps(),
        ws_ctx=_DummyDeps(),
        ws_route="/x",
        ws_allowed_personas=[],
        ws_nav_items=[],
        ws_entity_items=[],
        ws_nav_groups=[],
        ws_app_name="t",
        primary_action_candidates=[],
    )
    assert inspect.iscoroutinefunction(page_handler)
    assert inspect.iscoroutinefunction(ws_handler)
