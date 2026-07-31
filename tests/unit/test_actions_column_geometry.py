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
