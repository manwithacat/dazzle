"""#1119 — `mode: custom` surfaces with a `render:` clause MUST dispatch
through the renderer registry.

Pre-#1119, `_maybe_dispatch_inner_html` had a guard that short-circuited
when neither `table`, `detail`, nor `form` was populated on the
PageContext — which is exactly the case for `mode: custom`. The
registered custom renderer was therefore never called for custom-mode
surfaces; the page silently fell back to legacy rendering.

This module pins both halves of the new contract:

1. Custom-mode + `render:` set → dispatch IS called, with a sparse ctx
   (`{}`), and the renderer's HTML is threaded through. Renderer
   exceptions are caught and fall back to legacy.
2. Non-custom modes (LIST/VIEW/CREATE/EDIT) with `render:` set retain
   the pre-#1119 guard — empty ctx means legacy fallback, not
   silent dispatch with empty data.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.page_routes import _maybe_dispatch_inner_html


def _make_surface(name: str, mode: SurfaceMode, render: str | None) -> SimpleNamespace:
    """Stand-in for an IR SurfaceSpec — `_maybe_dispatch_inner_html`
    only reads `.render` and `.mode`, so a namespace is enough."""
    return SimpleNamespace(name=name, mode=mode, render=render, related_groups=())


def _make_prc(
    surface: SimpleNamespace,
    *,
    handler: MagicMock | None = None,
    render_ctx: SimpleNamespace | None = None,
) -> SimpleNamespace:
    """Build the minimum _PageRequestContext shape for the helper.

    `_maybe_dispatch_inner_html` reads:
      - prc.surface_name
      - prc.deps.appspec.get_surface(name)
      - prc.request.app.state.services.renderer_registry
    """
    if render_ctx is None:
        render_ctx = SimpleNamespace(table=None, detail=None, form=None)

    appspec = SimpleNamespace(get_surface=lambda n: surface if n == surface.name else None)

    if handler is None:
        # Default handler returns a marker HTML string.
        handler = MagicMock()
        handler.render = MagicMock(return_value="<section>custom!</section>")

    registry = SimpleNamespace(
        resolve=lambda name: handler if name == surface.render else None,
        registered_names=lambda: {surface.render} if surface.render else set(),
    )
    services = SimpleNamespace(renderer_registry=registry)
    app_state = SimpleNamespace(services=services)
    request = SimpleNamespace(app=SimpleNamespace(state=app_state))

    # `auth_ctx` is read by the #1129 CustomRenderCtx construction
    # path and threaded into the typed ctx as-is. None is the anon
    # default the production helper handles the same way.
    return SimpleNamespace(
        surface_name=surface.name,
        deps=SimpleNamespace(appspec=appspec),
        request=request,
        auth_ctx=None,
        render_ctx=render_ctx,
        # The helper reads `prc.surface_name`; render_ctx is passed as
        # a separate argument.
    )


def test_custom_mode_with_render_dispatches_even_with_empty_ctx() -> None:
    """The core fix: a registered custom renderer for a mode: custom
    surface gets invoked at request time, even though ctx is sparse
    (no table/detail/form). Pre-#1119, the registered renderer was
    silently skipped — the bug that made #1116's manifest allowlist
    work but the resulting renderer never fire."""
    surface = _make_surface("tag_cloud", SurfaceMode.CUSTOM, "word_cloud")
    handler = MagicMock()
    handler.render = MagicMock(return_value="<section>cloud-html</section>")
    prc = _make_prc(surface, handler=handler)

    result = _maybe_dispatch_inner_html(prc, prc.render_ctx)

    assert result == "<section>cloud-html</section>"
    handler.render.assert_called_once()
    # #1129: renderer received the surface AND a typed CustomRenderCtx
    # (was a sparse dict pre-#1129). The dict ctx remains the contract
    # for non-custom modes via _build_dispatch_ctx.
    from dazzle.render.context import CustomRenderCtx

    call_args = handler.render.call_args
    assert call_args[0][0] is surface
    assert isinstance(call_args[0][1], CustomRenderCtx)
    assert call_args[0][1].surface_name == "tag_cloud"


def test_custom_mode_dispatch_passes_typed_custom_render_ctx() -> None:
    """#1129: the renderer is expected to fetch its own data — the
    dispatched ctx is now a typed ``CustomRenderCtx`` exposing
    ``request`` / ``params`` / ``services`` / ``auth_ctx`` /
    ``surface_name`` / ``workspace_name``, instead of the pre-#1129
    sparse-dict shape."""
    from dazzle.render.context import CustomRenderCtx

    surface = _make_surface("tag_cloud", SurfaceMode.CUSTOM, "word_cloud")
    captured: list = []
    handler = MagicMock()

    def _capture(_surface, ctx):
        captured.append(ctx)
        return "ok"

    handler.render = MagicMock(side_effect=_capture)
    prc = _make_prc(surface, handler=handler)

    _maybe_dispatch_inner_html(prc, prc.render_ctx)

    assert len(captured) == 1
    ctx = captured[0]
    assert isinstance(ctx, CustomRenderCtx)
    assert ctx.surface_name == "tag_cloud"
    assert ctx.auth_ctx is None
    # params merges path + query; both are absent in this fixture
    assert ctx.params == {}


def test_custom_mode_dispatch_falls_back_to_legacy_on_fragment_error() -> None:
    """If the registered renderer raises FragmentError, fall back to
    legacy rendering (return None). Existing safety net — same shape
    as the non-custom path uses."""
    from dazzle.render.fragment.errors import FragmentError

    surface = _make_surface("tag_cloud", SurfaceMode.CUSTOM, "broken_one")
    handler = MagicMock()
    handler.render = MagicMock(side_effect=FragmentError("renderer broken"))
    prc = _make_prc(surface, handler=handler)

    result = _maybe_dispatch_inner_html(prc, prc.render_ctx)

    assert result is None  # legacy fallback


def test_non_custom_mode_with_empty_ctx_still_falls_back_to_legacy() -> None:
    """Regression guard: the #1119 carve-out is for `mode: custom`
    only. CREATE / EDIT / etc. with `render:` set but no populated ctx
    must continue to fall back to legacy — the framework's own
    fragment adapter would raise NotImplementedError otherwise."""
    surface = _make_surface("user_create", SurfaceMode.CREATE, "fragment")
    handler = MagicMock()
    handler.render = MagicMock(return_value="<form>fragment-create</form>")
    prc = _make_prc(surface, handler=handler)

    result = _maybe_dispatch_inner_html(prc, prc.render_ctx)

    assert result is None
    handler.render.assert_not_called()


def test_custom_mode_without_render_clause_falls_back_to_legacy() -> None:
    """If a custom-mode surface has no `render:` clause at all, the
    function returns None at the very top (existing behaviour — no
    change). The fix is for mode: custom + explicit render: name."""
    surface = _make_surface("tag_cloud", SurfaceMode.CUSTOM, None)
    handler = MagicMock()
    handler.render = MagicMock(return_value="should-not-fire")
    prc = _make_prc(surface, handler=handler)

    result = _maybe_dispatch_inner_html(prc, prc.render_ctx)

    assert result is None
    handler.render.assert_not_called()


# ---------------------------------------------------------------------------
# #1118 — overlay composition at the dispatch layer
# ---------------------------------------------------------------------------


def test_custom_mode_dispatch_prepends_active_guide_overlay() -> None:
    """When `_inject_onboarding_step` has populated
    `render_ctx.active_guide_html`, the dispatch path MUST prepend
    that overlay to the renderer's inner HTML — matching the legacy
    path's `_render_typed_body` composition. Pre-#1118, the dispatch
    path bypassed the only call site that read `active_guide_html`,
    so guide overlays silently dropped on any surface that declared
    `render:` (including the default `render: fragment` on typed
    entity surfaces). The fix puts the composition at the same layer
    that produces the inner HTML."""
    surface = _make_surface("tag_cloud", SurfaceMode.CUSTOM, "word_cloud")
    handler = MagicMock()
    handler.render = MagicMock(return_value="<section>cloud</section>")
    prc = _make_prc(surface, handler=handler)
    prc.render_ctx.active_guide_html = (
        '<dz-onboarding-step data-guide="g" data-step="s"></dz-onboarding-step>'
    )

    result = _maybe_dispatch_inner_html(prc, prc.render_ctx)

    assert result is not None
    # Overlay first, body after — matches `_render_typed_body` order
    # so the user lands on the overlay.
    assert result.index("dz-onboarding-step") < result.index("<section>")
    assert result.endswith("<section>cloud</section>")


def test_dispatch_path_without_overlay_returns_inner_html_unchanged() -> None:
    """If no overlay is set, the dispatch path returns the raw inner
    HTML — no extra prefix, no whitespace, byte-for-byte the renderer
    output. Regression guard: the overlay-prepend must be a no-op when
    `active_guide_html` is empty."""
    surface = _make_surface("tag_cloud", SurfaceMode.CUSTOM, "word_cloud")
    handler = MagicMock()
    handler.render = MagicMock(return_value="<section>cloud</section>")
    prc = _make_prc(surface, handler=handler)
    prc.render_ctx.active_guide_html = ""  # explicitly empty

    result = _maybe_dispatch_inner_html(prc, prc.render_ctx)

    assert result == "<section>cloud</section>"


def test_non_custom_dispatch_path_also_prepends_overlay() -> None:
    """The bug surfaced on `render: fragment` LIST surfaces, not just
    custom mode — anywhere the dispatch path fires, the overlay must
    compose. Pin the LIST-mode-with-table-ctx branch too."""
    surface = _make_surface("user_list", SurfaceMode.LIST, "fragment")
    handler = MagicMock()
    handler.render = MagicMock(return_value="<table>rows</table>")
    # Populated table ctx so we go through the non-custom dispatch path.
    render_ctx = SimpleNamespace(
        table=SimpleNamespace(rows=[], columns=[], total=0, page=1),
        detail=None,
        form=None,
        active_guide_html='<dz-onboarding-step data-guide="g" data-step="s"></dz-onboarding-step>',
    )
    prc = _make_prc(surface, handler=handler, render_ctx=render_ctx)

    result = _maybe_dispatch_inner_html(prc, prc.render_ctx)

    assert result is not None
    assert "dz-onboarding-step" in result
    assert "<table>rows</table>" in result
    assert result.index("dz-onboarding-step") < result.index("<table>")
