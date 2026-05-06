"""AppShell primitive — multi-slot application layout (P17 Phase 5)."""

from dazzle.render.fragment import AppShell, Heading, Page, Surface, Text
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


# ───────────────── Construction ─────────────────────────


def test_app_shell_minimal_body_only() -> None:
    a = AppShell(body=Text("hello"))
    assert a.sidebar is None
    assert a.header is None
    assert a.footer is None


def test_app_shell_all_slots() -> None:
    a = AppShell(
        body=Text("body"),
        sidebar=Text("sidebar"),
        header=Text("header"),
        footer=Text("footer"),
    )
    assert a.body is not None
    assert a.sidebar is not None
    assert a.header is not None
    assert a.footer is not None


# ───────────────── Renderer output ─────────────────────


def test_app_shell_emits_root_div_and_content_wrapper() -> None:
    html = _render(AppShell(body=Text("hi")))
    assert '<div class="dz-app-shell">' in html
    assert '<div class="dz-app-content">' in html


def test_app_shell_emits_main_with_id_for_skip_link_target() -> None:
    """The main element must carry id="main-content" so a11y skip-links
    point to a stable target — matches the legacy app_shell.html
    contract (`{{ skip_link("#main-content") }}` line 5)."""
    html = _render(AppShell(body=Text("body")))
    assert '<main class="dz-app-main" id="main-content">' in html


def test_app_shell_omits_sidebar_aside_when_no_sidebar() -> None:
    html = _render(AppShell(body=Text("body")))
    assert "dz-app-sidebar" not in html


def test_app_shell_renders_sidebar_in_aside_when_provided() -> None:
    html = _render(AppShell(body=Text("body"), sidebar=Text("nav-stuff")))
    assert '<aside class="dz-app-sidebar">' in html
    assert "nav-stuff" in html


def test_app_shell_renders_header_in_header_element_when_provided() -> None:
    html = _render(AppShell(body=Text("body"), header=Heading("My App", level=1)))
    assert '<header class="dz-app-header">' in html
    assert "My App" in html


def test_app_shell_renders_footer_in_footer_element_when_provided() -> None:
    html = _render(AppShell(body=Text("body"), footer=Text("© 2026")))
    assert '<footer class="dz-app-footer">' in html
    assert "© 2026" in html


def test_app_shell_slot_order_sidebar_header_main_footer() -> None:
    """Order matters for both visual layout and tab order: sidebar
    first (outside content wrapper), then within content: header,
    main, footer."""
    html = _render(
        AppShell(
            body=Text("BODY"),
            sidebar=Text("SIDE"),
            header=Text("HEAD"),
            footer=Text("FOOT"),
        )
    )
    # Sidebar comes before content wrapper
    side_idx = html.index("SIDE")
    content_open_idx = html.index('<div class="dz-app-content">')
    assert side_idx < content_open_idx

    # Within content: header < main < footer
    head_idx = html.index("HEAD")
    body_idx = html.index("BODY")
    foot_idx = html.index("FOOT")
    assert content_open_idx < head_idx < body_idx < foot_idx


def test_app_shell_inside_page_composes_full_chrome() -> None:
    """End-to-end: Page → AppShell → Surface. The canonical
    full-chrome composition for a Fragment-only app."""
    page = Page(
        title="My App",
        body=AppShell(
            sidebar=Text("Sidebar"),
            header=Text("Topbar"),
            body=Surface(header=Heading("Tasks", level=1), body=Text("Empty")),
        ),
    )
    html = _render(page)
    assert "<!DOCTYPE html>" in html
    assert '<body class="dz-page">' in html
    assert '<div class="dz-app-shell">' in html
    assert '<aside class="dz-app-sidebar">' in html
    assert '<main class="dz-app-main" id="main-content">' in html
    assert '<section class="dz-surface">' in html
    assert "Tasks" in html
