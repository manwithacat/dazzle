"""Named layout predicates — properties of rendered boxes/styles.

LAYER: L2

Each predicate documents one regression story. Prefer ratios / shared edges
over absolute coordinates. ε is per-predicate.
"""

from __future__ import annotations

from typing import Any

from tests.layout_kit.harness import Box

# Header text end vs content pack end (humanqa left-stack).
ALIGN_END_EPS_PX = 12.0
# 1.75rem icon square at 16px root.
ICON_SQUARE_PX = 28.0
# Resting ghost flex item residual.
GHOST_MAX_PX = 2.0


def assert_shared_end(
    a_right: float,
    b_right: float,
    *,
    eps: float = ALIGN_END_EPS_PX,
    label: str = "shared end",
) -> None:
    """``align.end_shared`` — two edges align within ε."""
    delta = abs(float(a_right) - float(b_right))
    assert delta <= eps, f"{label}: |{a_right} − {b_right}| = {delta} > eps={eps}"


def assert_no_ghost_flex_items(
    *,
    width: float,
    height: float,
    max_px: float = GHOST_MAX_PX,
    label: str = "ghost flex item",
) -> None:
    """``flex.resting_no_ghost`` — collapsed chrome must not reserve space."""
    assert float(width) < max_px and float(height) < max_px, (
        f"{label}: still reserves layout space {width}×{height} (max {max_px}px)"
    )


def assert_multiword_chip_wider_than_icon(
    chip_width: float,
    *,
    icon_px: float = ICON_SQUARE_PX,
    margin: float = 4.0,
    label: str = "multi-word chip",
) -> None:
    """``chip.not_icon_square`` — label chips must not be forced to 1.75rem."""
    assert chip_width is not None and float(chip_width) > icon_px + margin, (
        f"{label}: width {chip_width}px still looks like icon square (≤{icon_px}px)"
    )


def assert_strip_flex_end_full_width(
    *,
    display: str,
    justify: str,
    width_css: str,
    min_width_px: float = 100.0,
) -> None:
    """Actions strip is full-cell flex-end (not shrink-to-content)."""
    assert display == "flex", f"strip display={display!r}"
    assert justify == "flex-end", f"strip justify={justify!r}"
    w = float(str(width_css).replace("px", ""))
    assert w >= min_width_px, f"strip should span actions cell, width={width_css!r}"


def assert_box_near_cell_end(
    box: Box,
    cell: Box,
    *,
    max_pad: float = 24.0,
    label: str = "content pack",
) -> None:
    """Last chip / pack sits near the cell's right padding edge."""
    delta = float(cell.right) - float(box.right)
    assert 0 <= delta < max_pad, f"{label}: delta to cell right={delta} (box={box}, cell={cell})"


# Multi-chip actions: tops within ε; flex-wrap must stay nowrap (humanqa stack).
BASELINE_TOP_EPS_PX = 4.0


def assert_single_baseline_no_stack(
    tops: list[float],
    *,
    flex_wrap: str | None = None,
    eps: float = BASELINE_TOP_EPS_PX,
    label: str = "action children",
) -> None:
    """``overflow.cell_no_stack`` — action children share one baseline (no wrap stack).

    Multi-word SM chips + icons must stay a single horizontal pack. A wrap
    stack under a narrow actions column is the humanqa failure mode where
    chips look like a vertical pile left of the ACTIONS header.
    """
    if flex_wrap is not None:
        assert flex_wrap == "nowrap", f"{label}: flex-wrap={flex_wrap!r} (expected nowrap)"
    assert tops, f"{label}: no measured tops"
    lo, hi = min(tops), max(tops)
    assert (hi - lo) <= eps, (
        f"{label}: tops span {hi - lo:.2f}px > eps={eps} (tops={tops}) — children stacked"
    )


def assert_app_shell_wider_than_product(
    app_max_px: float,
    product_max_px: float,
    *,
    label: str = "measure.shell",
) -> None:
    """``measure.shell`` — ``data-dz-measure=app`` max-width ≥ product.

    Regression story: list/board surfaces need the soft ultrawide cap
    (``--dz-content-measure-app``); form/detail use the readable product
    measure (``--dz-content-measure``). If app ever collapses to product
    (or both unconstrained), tables pinch on wide monitors.
    """
    assert float(app_max_px) >= float(product_max_px), (
        f"{label}: app max-width {app_max_px}px < product {product_max_px}px"
    )
    assert float(product_max_px) > 0, f"{label}: product measure not applied"


def require_no_error(raw: dict[str, Any]) -> None:
    assert raw.get("error") is None, raw
