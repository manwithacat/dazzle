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
