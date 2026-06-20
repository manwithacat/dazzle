"""#1129: typed ``CustomRenderCtx`` for ``mode: custom`` renderers.

Before this fix, the dispatcher passed an empty dict to custom-mode
renderers; every renderer reached into framework internals via
defensive ``ctx.get(...)`` calls against an undocumented shape.

Post-fix the dispatcher builds a frozen ``CustomRenderCtx`` with
``request`` / ``params`` / ``services`` / ``auth_ctx`` /
``surface_name`` / ``workspace_name`` populated from the page
request context. Renderers that take ``ctx: dict[str, Any]`` keep
working — the typed shape is a sibling, not a replacement (Option
A from the issue body).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from dazzle.http.runtime.page_routes import _collect_request_params
from dazzle.render.context import CustomRenderCtx

# ---------------------------------------------------------------------------
# CustomRenderCtx dataclass — shape contract
# ---------------------------------------------------------------------------


def test_custom_render_ctx_is_frozen() -> None:
    """Frozen so renderers can't mutate framework state via the ctx."""
    ctx = CustomRenderCtx(
        request=MagicMock(),
        params={},
        services=MagicMock(),
        auth_ctx=None,
        surface_name="x",
        workspace_name=None,
    )
    import pytest

    with pytest.raises((AttributeError, Exception)):
        ctx.surface_name = "y"  # type: ignore[misc]


def test_custom_render_ctx_carries_all_documented_fields() -> None:
    """Lock the field set — adding a field is fine, removing one is
    a breaking change for the renderer protocol consumers."""
    fields = {f.name for f in CustomRenderCtx.__dataclass_fields__.values()}
    assert fields == {
        "request",
        "params",
        "services",
        "auth_ctx",
        "surface_name",
        "workspace_name",
    }


# ---------------------------------------------------------------------------
# _collect_request_params — path + query merge
# ---------------------------------------------------------------------------


def test_collect_request_params_merges_query_and_path() -> None:
    request = SimpleNamespace(
        query_params={"q": "search-term"},
        path_params={"id": "row-42"},
    )
    assert _collect_request_params(request) == {"q": "search-term", "id": "row-42"}


def test_collect_request_params_path_wins_on_collision() -> None:
    """Path params are route-declared and more specific than query
    string — they win on key collision."""
    request = SimpleNamespace(
        query_params={"id": "from-query"},
        path_params={"id": "from-path"},
    )
    assert _collect_request_params(request)["id"] == "from-path"


def test_collect_request_params_defensive_on_missing_attributes() -> None:
    """Test fixtures with bare mocks shouldn't crash here."""
    request = SimpleNamespace()
    assert _collect_request_params(request) == {}


def test_collect_request_params_coerces_to_str() -> None:
    """Values land as ``str`` for the typed ctx contract."""
    request = SimpleNamespace(
        query_params={"page": 3, "active": True},
        path_params={},
    )
    out = _collect_request_params(request)
    assert out == {"page": "3", "active": "True"}


# ---------------------------------------------------------------------------
# Dispatch integration — custom-mode receives CustomRenderCtx
# ---------------------------------------------------------------------------


def test_dispatch_render_passes_custom_render_ctx_through() -> None:
    """``dispatch_render`` accepts the union ``dict | CustomRenderCtx``
    and forwards verbatim to the handler — no unwrap, no normalize."""
    from dazzle.render.dispatch import dispatch_render

    received = {}

    class _Renderer:
        def render(self, surface: object, ctx: object) -> str:
            received["surface"] = surface
            received["ctx"] = ctx
            return "<div>ok</div>"

    services = SimpleNamespace(
        renderer_registry=SimpleNamespace(
            resolve=lambda _n: _Renderer(),
            registered_names=lambda: ["my_renderer"],
        ),
    )
    surface = SimpleNamespace(name="s", render="my_renderer")
    ctx = CustomRenderCtx(
        request=MagicMock(),
        params={"k": "v"},
        services=services,
        auth_ctx=None,
        surface_name="s",
        workspace_name="ws",
    )
    html = dispatch_render(surface, ctx=ctx, services=services)

    assert html == "<div>ok</div>"
    assert received["ctx"] is ctx
    assert isinstance(received["ctx"], CustomRenderCtx)
    # Renderer authors get IDE completion: ctx.params is a real dict,
    # not a defensive ctx.get("params", {}).
    assert received["ctx"].params == {"k": "v"}


def test_dispatch_render_still_accepts_dict_ctx_for_backcompat() -> None:
    """Existing renderers that take ``ctx: dict[str, Any]`` keep
    working — the typed shape is additive."""
    from dazzle.render.dispatch import dispatch_render

    received = {}

    class _Renderer:
        def render(self, surface: object, ctx: object) -> str:
            received["ctx"] = ctx
            return "ok"

    services = SimpleNamespace(
        renderer_registry=SimpleNamespace(
            resolve=lambda _n: _Renderer(),
            registered_names=lambda: ["my_renderer"],
        ),
    )
    surface = SimpleNamespace(name="s", render="my_renderer")
    dispatch_render(surface, ctx={"table": {"rows": []}}, services=services)

    assert received["ctx"] == {"table": {"rows": []}}
    assert not isinstance(received["ctx"], CustomRenderCtx)
