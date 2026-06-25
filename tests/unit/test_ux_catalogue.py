import pytest

from dazzle.testing.ux_catalogue import (
    CATALOGUE_MANIFEST,
    iter_catalogue_regions,
    load_showcase_appspec,
    render_catalogue_region,
)


def _render(name: str) -> str:
    appspec = load_showcase_appspec()
    for ir_region, ctx_region in iter_catalogue_regions(appspec):
        if ir_region.name == name:
            return render_catalogue_region(appspec, ir_region, ctx_region, CATALOGUE_MANIFEST[name])
    raise AssertionError(f"region {name} not found")


def test_list_renders_table_with_outlier_badge() -> None:
    html = _render("cat_list")
    assert "<table" in html or "dz-list" in html
    assert 'data-dz-tone="warning"' in html  # outlier_on flags the latency outlier


@pytest.mark.parametrize(
    "name, marker",
    [
        ("cat_metrics", "dz-metric-tile"),
        ("cat_bar_chart", "dz-bar-chart-region"),
        ("cat_comparison", "dz-bar-track"),
        ("cat_heatmap", "dz-heatmap-region"),
        ("cat_pivot", "dz-pivot-region"),
        ("cat_bullet", "dz-bullet-region"),
        ("cat_kanban", "dz-kanban-board"),
    ],
)
def test_mode_renders_primitive(name: str, marker: str) -> None:
    html = _render(name)
    assert html.strip(), f"{name} rendered empty"
    assert marker in html, f"{name} missing {marker!r}"
    assert "dz-empty" not in html, f"{name} fell through to an empty state"


def test_every_catalogue_region_has_a_manifest_entry() -> None:
    appspec = load_showcase_appspec()
    region_names = {r.name for r, _ in iter_catalogue_regions(appspec)}
    assert region_names == set(CATALOGUE_MANIFEST), (
        "ux_catalogue regions and CATALOGUE_MANIFEST keys must match exactly"
    )


def test_generated_page_has_all_modes() -> None:
    from dazzle.testing.ux_catalogue import generate_catalogue_markdown

    md = generate_catalogue_markdown()
    for marker in ("# UX Catalogue", "dz-catalogue-preview", "data-dz-tone", "```dsl", "cat_list:"):
        assert marker in md, f"generated page missing {marker!r}"


def test_generated_page_is_current() -> None:
    from pathlib import Path

    from dazzle.testing.ux_catalogue import OUT_PATH, generate_catalogue_markdown

    committed = Path(OUT_PATH).read_text() if Path(OUT_PATH).exists() else ""
    assert generate_catalogue_markdown() == committed, (
        "docs/reference/ux-catalogue.md is stale — run: python scripts/gen_ux_catalogue.py"
    )


def test_generated_css_is_current() -> None:
    from pathlib import Path

    from dazzle.testing.ux_catalogue import CSS_OUT_PATH, generate_catalogue_css

    committed = Path(CSS_OUT_PATH).read_text() if Path(CSS_OUT_PATH).exists() else ""
    assert generate_catalogue_css() == committed, (
        "docs/assets/dazzle-catalogue.css is stale — run: python scripts/gen_ux_catalogue.py"
    )
