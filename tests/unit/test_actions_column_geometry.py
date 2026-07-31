"""Actions column **layout concordance** via ``tests.layout_kit`` (L2).

LAYER: L2

Migrated from an inline Playwright fixture onto the shared harness +
named predicates (Phase 1 of css-layout-test-architecture).

Asserts relationships between rendered boxes:

* header label right edge ≈ last chip right edge
* chip strip is flex-end full-width
* multi-word transition chip wider than icon square
* resting icons do not reserve flex space (ghost flex)

No CSS-source regex — Chromium is the layout oracle.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

from tests.layout_kit.fixtures import (  # noqa: E402
    ACTIONS_COLUMN_MEASURE_JS,
    CHIP_STRIP_BASELINE_MEASURE_JS,
    RESTING_ICONS_MEASURE_JS,
    actions_column_table_body,
    actions_resting_icons_body,
)
from tests.layout_kit.harness import (  # noqa: E402
    LayoutState,
    dazzle_css_path,
    render_layout,
    wrap_fixture_html,
)
from tests.layout_kit.predicates import (  # noqa: E402
    ALIGN_END_EPS_PX,
    assert_multiword_chip_wider_than_icon,
    assert_no_ghost_flex_items,
    assert_shared_end,
    assert_single_baseline_no_stack,
    assert_strip_flex_end_full_width,
    require_no_error,
)


@pytest.fixture(scope="module")
def actions_geometry():
    css_path = dazzle_css_path()
    if not css_path.is_file():
        pytest.skip(f"missing bundled CSS {css_path}")
    html = wrap_fixture_html(actions_column_table_body(), css=css_path.read_text(encoding="utf-8"))
    snap = render_layout(
        html=html,
        state=LayoutState.RESTING,
        measure_js=ACTIONS_COLUMN_MEASURE_JS,
        tmp_name="dz-actions-column-geometry.html",
    )
    return snap.raw


def test_computed_strip_is_full_width_flex_end(actions_geometry: dict) -> None:
    require_no_error(actions_geometry)
    assert_strip_flex_end_full_width(
        display=actions_geometry["stripDisplay"],
        justify=actions_geometry["stripJustify"],
        width_css=actions_geometry["stripWidth"],
    )


def test_multiword_chip_wider_than_icon_square(actions_geometry: dict) -> None:
    """Concordance: 'In Progress' cannot be a 1.75rem icon square."""
    assert_multiword_chip_wider_than_icon(actions_geometry.get("multiWordChipPx"))


def test_header_text_and_last_chip_share_right_edge(actions_geometry: dict) -> None:
    """Concordance: ACTIONS label end ≈ last chip end (humanqa left-stack)."""
    rows = actions_geometry.get("rows") or []
    assert rows, actions_geometry
    failures = []
    for i, r in enumerate(rows):
        try:
            assert_shared_end(
                r["lastChipRight"],
                r["thTextRight"],
                eps=ALIGN_END_EPS_PX,
                label=f"row[{i}] chip vs ACTIONS header",
            )
        except AssertionError as exc:
            failures.append((i, r, str(exc)))
    assert not failures, failures


def test_chips_sit_near_cell_end_padding(actions_geometry: dict) -> None:
    rows = actions_geometry.get("rows") or []
    assert rows
    for i, r in enumerate(rows):
        delta = float(r["deltaToCellRight"])
        assert 0 <= delta < 24, (i, r)


def test_resting_state_icons_do_not_reserve_space_left_of_chips() -> None:
    """Without hover, opacity-0 icons must not shove chips left of ACTIONS.

    Human perception: chips 'hang left' under a right-aligned header because
    invisible icon buttons still participated in flex layout.
    """
    css_path = dazzle_css_path()
    if not css_path.is_file():
        pytest.skip(f"missing bundled CSS {css_path}")
    html = wrap_fixture_html(
        actions_resting_icons_body(),
        css=css_path.read_text(encoding="utf-8"),
    )
    # Do NOT hover — resting state
    snap = render_layout(
        html=html,
        state=LayoutState.RESTING,
        measure_js=RESTING_ICONS_MEASURE_JS,
        tmp_name="dz-actions-resting-icons.html",
    )
    data = snap.raw
    require_no_error(data)
    assert_no_ghost_flex_items(
        width=data["iconWidth"], height=data["iconHeight"], label="resting icon"
    )
    assert_shared_end(
        data["chipRight"],
        data["thTextRight"],
        eps=ALIGN_END_EPS_PX,
        label="resting chips under ACTIONS header",
    )


def test_multi_chip_actions_share_single_baseline_no_stack() -> None:
    """``overflow.cell_no_stack`` — multi SM chips stay one horizontal pack.

    Cycle 1538 layout_kit expand (Phase 1+ of css-layout-test-architecture).
    """
    css_path = dazzle_css_path()
    if not css_path.is_file():
        pytest.skip(f"missing bundled CSS {css_path}")
    html = wrap_fixture_html(
        actions_column_table_body(),
        css=css_path.read_text(encoding="utf-8"),
    )
    snap = render_layout(
        html=html,
        state=LayoutState.RESTING,
        measure_js=CHIP_STRIP_BASELINE_MEASURE_JS,
        tmp_name="dz-actions-chip-baseline.html",
    )
    data = snap.raw
    require_no_error(data)
    rows = data.get("rows") or []
    assert rows, data
    for i, r in enumerate(rows):
        assert_single_baseline_no_stack(
            list(r["tops"]),
            flex_wrap=r.get("flexWrap"),
            label=f"actions strip row[{i}]",
        )


def test_measure_shell_app_wider_than_product() -> None:
    """``measure.shell`` — app max-width ≥ product (content measure tokens).

    Cycle 1546: wire data-dz-measure + CSS; L2 pin that list (app) stays
    at least as wide as form/detail (product) under production cascade.
    """
    from tests.layout_kit.fixtures import SHELL_MEASURE_BODY, SHELL_MEASURE_JS
    from tests.layout_kit.predicates import assert_app_shell_wider_than_product

    css_path = dazzle_css_path()
    if not css_path.is_file():
        pytest.skip(f"missing bundled CSS {css_path}")
    # Wide viewport so app soft-cap (96rem) and product (48rem) both bind.
    html = wrap_fixture_html(
        SHELL_MEASURE_BODY,
        css=css_path.read_text(encoding="utf-8"),
        stage_width=1800,
    )
    snap = render_layout(
        html=html,
        state=LayoutState.RESTING,
        measure_js=SHELL_MEASURE_JS,
        viewport=(1900, 900),
        tmp_name="dz-shell-measure.html",
    )
    data = snap.raw
    require_no_error(data.get("product") or {})
    require_no_error(data.get("app") or {})
    product = data["product"]
    app = data["app"]
    wide = data["wide"]
    full = data["full"]

    def _max_px(entry: dict) -> float:
        raw = str(entry.get("maxWidthCss") or "")
        if raw.endswith("px"):
            return float(raw[:-2])
        if raw in ("none", "", "auto"):
            return float("inf")
        # rem → assume 16px root
        if raw.endswith("rem"):
            return float(raw[:-3]) * 16.0
        return float(entry.get("widthPx") or 0)

    product_max = _max_px(product)
    app_max = _max_px(app)
    wide_max = _max_px(wide)
    assert_app_shell_wider_than_product(app_max, product_max)
    assert product_max < wide_max <= app_max or wide_max == product_max, (
        product_max,
        wide_max,
        app_max,
    )
    # Full-bleed has no data-dz-measure → max-width none (unconstrained).
    assert full.get("measure") is None
    assert str(full.get("maxWidthCss") or "") in ("none", "auto", "")
