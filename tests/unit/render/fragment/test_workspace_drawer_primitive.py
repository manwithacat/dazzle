"""Phase 4B.5.b.3 (v0.66.124): byte-equivalence + structural tests for
the typed `WorkspaceDrawer` primitive.

The drawer is a fixed-shape singleton — backdrop div + aside + IIFE
that wires `dzDrawer.open()` / `.close()` and the document-level
htmx:afterSettle defensive close (#934). No parameters; the entire
markup + script is loaded from the canonical static asset
`render/fragment/static/workspace_drawer.html`."""

from __future__ import annotations

from dazzle.render.fragment import FragmentRenderer, WorkspaceDrawer
from dazzle_back.runtime.renderers.dual_path import diff_summary
from dazzle_ui.runtime.template_renderer import create_jinja_env


def _legacy_drawer_block() -> str:
    """Render the drawer block from the legacy `_content.html` template
    via Jinja — same path the workspace runtime takes."""
    src = open(  # noqa: SIM115
        "src/dazzle_ui/templates/workspace/_content.html"
    ).read()
    start = src.index('<div id="dz-drawer-backdrop"')
    drawer = src[start:].rstrip()
    env = create_jinja_env()
    return env.from_string(drawer).render()


def _typed_render() -> str:
    return FragmentRenderer().render(WorkspaceDrawer())


def test_workspace_drawer_byte_equivalent_to_legacy() -> None:
    """The typed primitive emits byte-for-byte identical markup +
    IIFE compared to the legacy `_content.html` drawer block."""
    assert diff_summary(_legacy_drawer_block(), _typed_render()) is None


def test_workspace_drawer_emits_backdrop_and_aside() -> None:
    """Backdrop + aside are the contract IDs the drawer JS keys off."""
    html = _typed_render()
    assert 'id="dz-drawer-backdrop"' in html
    assert 'class="dz-drawer-backdrop"' in html
    assert 'id="dz-detail-drawer"' in html
    assert '<aside id="dz-detail-drawer" class="dz-drawer">' in html


def test_workspace_drawer_emits_close_handlers() -> None:
    """Backdrop + close button both fire `window.dzDrawer.close()`
    inline. The escape keydown listener is wired in the IIFE."""
    html = _typed_render()
    assert 'onclick="window.dzDrawer.close()"' in html
    assert html.count("window.dzDrawer.close()") >= 3  # backdrop + button + IIFE close()


def test_workspace_drawer_includes_init_guard() -> None:
    """`window.__dzDrawerInit` install-once guard prevents N stacked
    listeners after N workspace nav swaps (#934)."""
    html = _typed_render()
    assert "window.__dzDrawerInit" in html


def test_workspace_drawer_carries_htmx_after_settle_defensive_close() -> None:
    """The drawer's defensive close on `htmx:afterSettle` (#934) — if
    a swap landed anywhere other than `#dz-detail-drawer-content`,
    force the drawer closed so stale `is-open` state can't leak across
    workspace nav."""
    html = _typed_render()
    assert "htmx:afterSettle" in html
    assert "dz-detail-drawer-content" in html


def test_workspace_drawer_emits_drawer_open_custom_event_listener() -> None:
    """`document.body.addEventListener('dz:drawerOpen', ...)` is the
    cross-component contract — any region/card can dispatch the event
    to open the drawer with a target URL."""
    html = _typed_render()
    assert "dz:drawerOpen" in html
    assert "window.dzDrawer.open" in html


def test_workspace_drawer_emits_escape_keydown_handler() -> None:
    """Escape closes the drawer when open."""
    html = _typed_render()
    assert "'Escape'" in html
    assert "window.dzDrawer.isOpen" in html
