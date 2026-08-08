"""breadcrumb hyperpart emitter — unit pins (cycle 1761).

Shell trail: ``current_route`` + ``page_title`` → ``Breadcrumb`` /
``.dz-breadcrumb``. Fragment path: ``Breadcrumb`` / ``BreadcrumbItem``.
"""

from __future__ import annotations

from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.breadcrumbs import (
    Crumb,
    build_shell_breadcrumb,
    crumbs_to_breadcrumb,
)
from dazzle.render.context import PageContext
from dazzle.render.dispatch import build_app_chrome_page
from dazzle.render.fragment import Breadcrumb, BreadcrumbItem, FragmentRenderer


def test_breadcrumb_emit_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(
        Breadcrumb(
            items=(
                BreadcrumbItem(label="Home", href="/app"),
                BreadcrumbItem(label="Tasks", href="/app/task"),
                BreadcrumbItem(label="Fix login", href=None),
            )
        )
    )
    assert 'class="dz-breadcrumb"' in html
    assert 'aria-label="Breadcrumb"' in html
    assert "<ol>" in html
    assert 'href="/app"' in html
    assert 'href="/app/task"' in html
    assert 'aria-current="page"' in html
    assert "Fix login" in html
    # Current page is not a link
    assert 'aria-current="page">Fix login</li>' in html


def test_crumbs_to_breadcrumb_roundtrip() -> None:
    crumbs = [
        Crumb(label="Home", url="/"),
        Crumb(label="Projects", url="/projects"),
        Crumb(label="Alpha", url=None),
    ]
    frag = crumbs_to_breadcrumb(crumbs)
    html = FragmentRenderer().render(frag)
    assert 'class="dz-breadcrumb"' in html
    assert "Projects" in html
    assert 'aria-current="page">Alpha</li>' in html


def test_shell_breadcrumb_from_page_context() -> None:
    ctx = PageContext(
        page_title="Urgent queue",
        current_route="/app/workspaces/task_board",
        app_name="Simple Task",
    )
    bc = build_shell_breadcrumb(ctx)
    assert bc is not None
    html = FragmentRenderer().render(bc)
    assert 'class="dz-breadcrumb"' in html
    assert "Home" in html
    assert "Urgent queue" in html


def test_app_chrome_mounts_breadcrumb() -> None:
    ctx = PageContext(
        page_title="Task list",
        current_route="/app/task",
        app_name="Simple Task",
        nav_items=[],
    )
    page = build_app_chrome_page(ctx, "<div>body</div>")
    html = FragmentRenderer().render(page)
    assert 'class="dz-breadcrumb"' in html
    assert "Task list" in html
    assert "<div>body</div>" in html


def test_dsl_shapes_breadcrumb_live() -> None:
    snap = shapes_snapshot()
    planned = set(snap.get("planned_ids") or [])
    assert "breadcrumb" not in planned
    assert snap["next_planned"] != "breadcrumb"
    assert snap["live"] >= 68
