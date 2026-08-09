"""menubar hyperpart emitter — unit pins (cycle 1769).

``menubar: true`` on the app block → shell ``Menubar`` / ``.dz-menubar``.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.qa.hyperpart_dsl_shapes import shapes_snapshot
from dazzle.render.fragment import FragmentRenderer, Menubar, MenubarAction, MenubarMenu
from dazzle.render.menubar import build_shell_menubar

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "examples" / "design_studio"


def test_menubar_emit_mounts_dz_spine() -> None:
    html = FragmentRenderer().render(
        Menubar(
            menus=(
                MenubarMenu(
                    label="File",
                    actions=(
                        MenubarAction(label="New", href="/app/new"),
                        MenubarAction(label="Export"),
                    ),
                ),
                MenubarMenu(
                    label="Edit",
                    actions=(MenubarAction(label="Undo"),),
                ),
            )
        )
    )
    assert 'class="dz-menubar"' in html
    assert "data-dz-menubar" in html
    assert 'class="dz-menubar__item"' in html
    assert 'class="dz-menubar__trigger"' in html
    assert 'class="dz-menubar__panel"' in html
    assert "File" in html
    assert "Edit" in html
    assert 'href="/app/new"' in html
    assert 'role="menuitem"' in html


def test_build_shell_menubar_respects_opt_in() -> None:
    ctx = SimpleNamespace(
        shell_menubar=False,
        extra={},
        nav_model=None,
        nav_groups=[],
        nav_items=[],
        app_name="Demo",
        current_route="/app",
    )
    assert build_shell_menubar(ctx) is None

    ctx.shell_menubar = True
    bar = build_shell_menubar(ctx)
    assert bar is not None
    html = FragmentRenderer().render(bar)
    assert "data-dz-menubar" in html
    assert "File" in html  # fallback chrome when nav empty


def test_build_shell_menubar_from_nav_groups() -> None:
    ctx = SimpleNamespace(
        shell_menubar=True,
        extra={},
        nav_model=None,
        nav_groups=[
            {
                "label": "Studio",
                "children": [
                    SimpleNamespace(label="Dashboard", route="/app/studio"),
                    SimpleNamespace(label="Brands", route="/app/brands"),
                ],
            }
        ],
        nav_items=[],
        app_name="Design Studio",
        current_route="/app",
    )
    bar = build_shell_menubar(ctx)
    assert bar is not None
    assert bar.menus[0].label == "Studio"
    html = FragmentRenderer().render(bar)
    assert "Dashboard" in html
    assert 'href="/app/studio"' in html


def test_design_studio_declares_menubar_opt_in() -> None:
    text = (DESIGN / "dsl" / "app.dsl").read_text(encoding="utf-8")
    assert "menubar: true" in text


def test_design_studio_appspec_features_menubar() -> None:
    appspec = load_project_appspec(DESIGN)
    cfg = getattr(appspec, "app_config", None)
    assert cfg is not None
    features = getattr(cfg, "features", None) or {}
    assert features.get("menubar") is True


def test_menubar_shape_live() -> None:
    snap = shapes_snapshot()
    assert "menubar" not in snap["planned_ids"]
    assert snap["next_planned"] != "menubar"
