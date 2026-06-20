"""Issue #1034 (v0.67.1) + follow-up #1112: regression tests for the
workspace, page, experience, and root-redirect handler signature contract.

Pre-fix, both `_make_page_handler` and the workspace-route handler
construction used `functools.partial(...)` which strips type
annotations from `inspect.signature`. FastAPI then saw `request`
as an un-annotated parameter, defaulted it to `Query(...)`, and on
pydantic >= 2.13 hard-failed building a `TypeAdapter` for the
`Request` forward-ref — every `/app/workspaces/{name}` route
returned HTTP 422.

#1034 fixed the workspace + page handlers. #1112 covers the three
remaining `partial(_experience_*, deps)` bindings in `experience_routes`
and the `partial(_root_redirect, deps, ...)` binding in `page_routes`,
which were still poisoning the shared pydantic TypeAdapter cache at
app-mount time even when the DSL had no `experience` blocks (the router
is mounted unconditionally).

Fix: closure factories that wrap the inner handler in an
`async def handler(request: Request, ...)` so the annotation survives
the `__signature__` introspection FastAPI performs at route-
registration time."""

from __future__ import annotations

import inspect
from pathlib import Path

from fastapi import Request

from dazzle.http.runtime.experience_routes import (
    _make_experience_entry_handler,
    _make_experience_step_get_handler,
    _make_experience_step_post_handler,
)
from dazzle.http.runtime.page_routes import (
    _make_page_handler,
    _make_root_redirect_handler,
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
        authored_actions=[],
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
        authored_actions=[],
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
        authored_actions=[],
    )
    assert inspect.iscoroutinefunction(page_handler)
    assert inspect.iscoroutinefunction(ws_handler)


# ---------------------------------------------------------------------------
# #1112 — experience + root-redirect factories
# ---------------------------------------------------------------------------


def test_make_experience_entry_handler_preserves_request_annotation() -> None:
    """GET /experiences/{name} — `request: Request` must survive the
    closure-factory pass. Pre-fix `partial(_experience_entry, deps)`
    poisoned the TypeAdapter cache even when no experience blocks
    existed (router mounted unconditionally)."""
    handler = _make_experience_entry_handler(_DummyDeps())
    sig = inspect.signature(handler)
    assert list(sig.parameters.keys()) == ["request", "name"]
    assert sig.parameters["request"].annotation is Request
    assert sig.parameters["name"].annotation is str
    assert inspect.iscoroutinefunction(handler)


def test_make_experience_step_get_handler_preserves_request_annotation() -> None:
    """GET /experiences/{name}/{step}."""
    handler = _make_experience_step_get_handler(_DummyDeps())
    sig = inspect.signature(handler)
    assert list(sig.parameters.keys()) == ["request", "name", "step"]
    assert sig.parameters["request"].annotation is Request
    assert inspect.iscoroutinefunction(handler)


def test_make_experience_step_post_handler_preserves_request_annotation() -> None:
    """POST /experiences/{name}/{step}."""
    handler = _make_experience_step_post_handler(_DummyDeps())
    sig = inspect.signature(handler)
    assert list(sig.parameters.keys()) == ["request", "name", "step"]
    assert sig.parameters["request"].annotation is Request
    assert inspect.iscoroutinefunction(handler)


def test_make_root_redirect_handler_preserves_request_annotation() -> None:
    """GET / — root redirect to persona's default workspace. Pre-fix
    `partial(_root_redirect, deps, persona_ws_routes, fallback_ws_route)`
    stripped the Request annotation even though the route itself 307s
    before validation runs — the annotation was needed at OpenAPI-build
    time to avoid the pydantic adapter failure."""
    handler = _make_root_redirect_handler(_DummyDeps(), {}, "/app/workspaces/x")
    sig = inspect.signature(handler)
    assert list(sig.parameters.keys()) == ["request"]
    assert sig.parameters["request"].annotation is Request
    assert inspect.iscoroutinefunction(handler)


# ---------------------------------------------------------------------------
# Durable lint gate — catches any future `partial(_h, ...)` where `_h`
# has `request: Request`. This is the gate the v0.67.1 fix lacked, which
# is why #1112 was needed at all.
# ---------------------------------------------------------------------------


def test_no_partial_bound_request_handlers() -> None:
    """No `partial(_h, ...)` may bind a handler with `request: Request`.

    `functools.partial` strips type annotations from `inspect.signature`,
    so FastAPI sees `request` as unannotated and pydantic >= 2.13 fails
    building a TypeAdapter for the Request forward-ref. This poisons the
    shared adapter cache for every other route in the app — symptoms
    cascade as 422s on unrelated workspace landings and 500s on
    /openapi.json.

    Use a closure factory (`_make_X_handler`) instead. See #1034 / #1112.

    AST-based so docstring references to `partial(_h, ...)` (explaining
    the historical bug) don't trip the gate — only real call expressions.
    """
    import ast

    runtime_roots = (
        Path("src/dazzle/page/runtime"),
        Path("src/dazzle/http/runtime"),
    )
    offenders: list[str] = []
    for root in runtime_roots:
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            try:
                tree = ast.parse(text, filename=str(py))
            except SyntaxError:
                continue

            # Collect names of async handlers in this file whose
            # signature has `request: Request`.
            request_handlers: set[str] = set()
            for node in ast.walk(tree):
                if not isinstance(node, ast.AsyncFunctionDef):
                    continue
                for arg in node.args.args:
                    if (
                        arg.arg == "request"
                        and isinstance(arg.annotation, ast.Name)
                        and arg.annotation.id == "Request"
                    ):
                        request_handlers.add(node.name)
                        break

            # Walk real Call expressions for `partial(_handler, ...)` or
            # `functools.partial(_handler, ...)`.
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                is_partial = (isinstance(func, ast.Name) and func.id == "partial") or (
                    isinstance(func, ast.Attribute) and func.attr == "partial"
                )
                if not is_partial or not node.args:
                    continue
                first = node.args[0]
                if not isinstance(first, ast.Name):
                    continue
                if first.id in request_handlers:
                    offenders.append(
                        f"{py}:{node.lineno}: partial({first.id}, ...) — "
                        f"{first.id} takes `request: Request`. "
                        f"Use a closure factory instead (see _make_*_handler)."
                    )

    assert not offenders, (
        "partial(_h, ...) bindings strip the `request: Request` annotation "
        "and poison pydantic's TypeAdapter cache. Use a closure factory.\n\n" + "\n".join(offenders)
    )
