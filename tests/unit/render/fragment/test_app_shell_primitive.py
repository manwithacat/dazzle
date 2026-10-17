"""AppShell primitive — multi-slot application layout (P17 Phase 5)."""

import pytest

from dazzle.render.fragment import AppShell, Heading, Page, Surface, Text
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


@pytest.mark.parametrize(
    ("shell", "present", "absent"),
    [
        pytest.param(
            AppShell(body=Text("hi")),
            (
                '<div class="dz-app-shell"',
                '<div class="dz-app-content">',
                # a11y skip-links target a stable id on <main> (legacy
                # `{{ skip_link("#main-content") }}` contract).
                '<main class="dz-app-main" id="main-content">',
            ),
            ("dz-app-sidebar",),
            id="body-only-emits-root-content-main-no-sidebar",
        ),
        pytest.param(
            AppShell(body=Text("body"), sidebar=Text("nav-stuff")),
            ('<aside class="dz-app-sidebar"', "nav-stuff"),
            (),
            id="sidebar-in-aside",
        ),
        pytest.param(
            AppShell(body=Text("body"), header=Heading("My App", level=1)),
            ('<header class="dz-app-header">', "My App"),
            (),
            id="header-in-header-element",
        ),
        pytest.param(
            AppShell(body=Text("body"), footer=Text("© 2026")),
            ('<footer class="dz-app-footer">', "© 2026"),
            (),
            id="footer-in-footer-element",
        ),
        # #1294 — sidebar reachability: the CSS keys the off-screen/visible
        # state off data-dz-sidebar, which the renderer once never emitted
        # (geometry is checked in the e2e harness; these are the DOM guards).
        pytest.param(
            AppShell(body=Text("hi"), sidebar=Text("nav")),
            ('data-dz-sidebar="open"', 'id="dz-app-sidebar"'),
            (),
            id="1294-sidebar-open-by-default-with-toggle-target-id",
        ),
        pytest.param(
            AppShell(body=Text("hi"), sidebar=Text("nav"), sidebar_state="closed"),
            ('data-dz-sidebar="closed"',),
            (),
            id="1294-sidebar-closed-when-set",
        ),
        pytest.param(
            AppShell(body=Text("hi"), sidebar_state='evil"><script>'),
            ('data-dz-sidebar="open"',),
            ("<script>",),
            id="1294-invalid-sidebar-state-sanitised-to-open",
        ),
        # #1798 — the narrow-drawer backdrop is server-emitted beside a sidebar
        # (the controller only toggles data-dz-drawer); no sidebar, no scrim.
        pytest.param(
            AppShell(body=Text("hi"), sidebar=Text("nav")),
            (
                '<div class="dz-app-backdrop" data-dz-sidebar-backdrop aria-hidden="true"></div></div>',
            ),
            ("data-dz-drawer",),
            id="1798-sidebar-emits-drawer-backdrop-as-last-child",
        ),
        pytest.param(
            AppShell(body=Text("hi")),
            (),
            ("data-dz-sidebar-backdrop",),
            id="1798-no-sidebar-no-backdrop",
        ),
        # content measure (cycle 1546): empty / full-bleed means no max-width.
        *(
            pytest.param(
                AppShell(body=Text("body"), content_measure=measure),
                (),
                ("data-dz-measure",),
                id=f"measure-omitted-for-{label}",
            )
            for measure, label in [
                ("", "empty"),
                ("full", "full"),
                ("  ", "blank"),
                ("unknown", "unknown"),
            ]
        ),
    ],
)
def test_app_shell_renders(shell: AppShell, present: tuple, absent: tuple) -> None:
    html = _render(shell)
    assert [s for s in present if s not in html] == []
    assert [s for s in absent if s in html] == []


@pytest.mark.parametrize(
    ("measure", "expected"),
    [("app", "app"), ("product", "product"), ("wide", "wide"), ("Product", "product")],
    ids=["app", "product", "wide", "case-normalised"],
)
def test_app_shell_emits_content_measure_on_main(measure: str, expected: str) -> None:
    """PageContext.content_measure reaches the DOM on <main> (the shell
    content column), not the shell root (cycle 1546)."""
    html = _render(AppShell(body=Text("body"), content_measure=measure))
    main = html[html.index("<main") : html.index("</main>") + 7]
    assert f'data-dz-measure="{expected}"' in main


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
    content_open_idx = html.index('<div class="dz-app-content">')
    assert html.index("SIDE") < content_open_idx
    assert content_open_idx < html.index("HEAD") < html.index("BODY") < html.index("FOOT")


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
    assert '<div class="dz-app-shell"' in html
    assert '<aside class="dz-app-sidebar"' in html
    assert '<main class="dz-app-main" id="main-content">' in html
    assert '<section class="dz-surface">' in html
    assert "Tasks" in html
