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
from dazzle.ui.runtime.page_routes import _maybe_dispatch_inner_html


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

    return SimpleNamespace(
        surface_name=surface.name,
        deps=SimpleNamespace(appspec=appspec),
        request=request,
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
    # Renderer received the surface AND a dict ctx (sparse, but a dict).
    call_args = handler.render.call_args
    assert call_args[0][0] is surface
    assert isinstance(call_args[0][1], dict)


def test_custom_mode_dispatch_passes_sparse_ctx_when_no_table_or_detail() -> None:
    """The renderer is expected to fetch its own data — the dispatched
    ctx should reflect that (no spurious `table`/`detail`/`form` keys)."""
    surface = _make_surface("tag_cloud", SurfaceMode.CUSTOM, "word_cloud")
    captured: dict = {}
    handler = MagicMock()

    def _capture(_surface, ctx):
        captured.update(ctx)
        return "ok"

    handler.render = MagicMock(side_effect=_capture)
    prc = _make_prc(surface, handler=handler)

    _maybe_dispatch_inner_html(prc, prc.render_ctx)

    # `_build_dispatch_ctx` returns {} when nothing populated.
    assert captured == {}


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
