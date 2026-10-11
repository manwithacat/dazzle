"""Tests for the v0.61.71 `pair_strip` workspace stage (#5).

The AegisMark UX patterns roadmap (item #5) — the SIMS-sync-opt-in
prototype's `consent-grid` is a vertical stack of explicit
(info, action) pairs. Each row is two half-width panels; the layout
auto-flows multiple pairs into rows of two via CSS grid.

This first cycle ships pair_strip as a workspace **stage** value
(sibling to focus_metric, dual_pane_flow, scanner_table, etc.) —
the simplest extension point that gives authors the layout intent
without inventing new IR primitives. Every region under a
pair_strip stage gets `col_span=6`; CSS grid auto-flow handles the
row distribution. Authors keep their existing region declarations
unchanged.

Mobile fallback is the project's responsibility (typical media
query collapses the 12-column grid to a single column at narrow
widths). No framework-specific JS is needed.
"""

from __future__ import annotations

from pathlib import Path

# ───────────────────────── stage registration ──────────────────────────


class TestPairStripStageRegistered:
    """The two stage-table dictionaries in workspace_renderer.py
    must both have a `pair_strip` entry — STAGE_DEFAULT_SPANS for
    the col_span pattern and STAGE_FOLD_COUNTS for the eager-load
    count."""

    def test_in_default_spans(self) -> None:
        from dazzle.page.runtime.workspace_renderer import STAGE_DEFAULT_SPANS

        assert "pair_strip" in STAGE_DEFAULT_SPANS, (
            "pair_strip stage missing from STAGE_DEFAULT_SPANS — #5 lost"
        )
        # Pair-strip = every region half-width, autoflow into rows of two
        assert STAGE_DEFAULT_SPANS["pair_strip"] == 6

    def test_in_fold_counts(self) -> None:
        from dazzle.page.runtime.workspace_renderer import STAGE_FOLD_COUNTS

        assert "pair_strip" in STAGE_FOLD_COUNTS
        # Three pairs = six regions eagerly loaded above the fold
        assert STAGE_FOLD_COUNTS["pair_strip"] == 3


class TestPairStripDefaultColSpan:
    """`_default_col_span` must return 6 for every region under a
    pair_strip stage, regardless of position. CSS grid auto-flow
    then arranges them into rows of two."""

    def test_first_region_half_width(self) -> None:
        from dazzle.page.runtime.workspace_renderer import _default_col_span

        assert _default_col_span("pair_strip", 0) == 6

    def test_subsequent_regions_also_half_width(self) -> None:
        from dazzle.page.runtime.workspace_renderer import _default_col_span

        for idx in range(1, 8):
            assert _default_col_span("pair_strip", idx) == 6, (
                f"Region {idx} under pair_strip got non-6 span — would break "
                "the explicit pair shape"
            )

    def test_unrelated_stage_unaffected(self) -> None:
        """Regression guard — adding pair_strip mustn't change the
        col_span behaviour of any other stage."""
        from dazzle.page.runtime.workspace_renderer import _default_col_span

        # focus_metric: [12, 6] — first region full-width, rest half
        assert _default_col_span("focus_metric", 0) == 12
        assert _default_col_span("focus_metric", 1) == 6
        # dual_pane_flow: 6 — every region half-width
        assert _default_col_span("dual_pane_flow", 0) == 6


# ───────────────────────── responsive contract ──────────────────────────


class TestPairStripResponsiveBehaviour:
    """The framework relies on the project's CSS grid responsive
    rules to collapse pair_strip pairs to a single column on narrow
    viewports — no framework JS, no per-region template branching.
    The 12-column dashboard grid does this naturally because every
    region's `col-span-6` becomes equivalent to `col-span-12` once
    the grid is forced to a single column at the breakpoint.

    This test pins the contract: pair_strip declares ONLY the
    col_span, not any mobile-specific markup. Any mobile fallback
    lives in CSS, not the renderer."""

    def test_no_mobile_specific_branching_in_renderer(self) -> None:
        from dazzle.page.runtime import workspace_renderer

        src = Path(workspace_renderer.__file__).read_text()
        # The string `pair_strip` should only appear in the two stage
        # tables (and their comments) — no mobile-specific code paths.
        # If a future change adds renderer-level responsive branching
        # for pair_strip, this guard will trip and make the operator
        # think twice about whether CSS would do better.
        relevant_lines = [line for line in src.splitlines() if "pair_strip" in line]
        assert len(relevant_lines) <= 6, (
            "pair_strip references in renderer growing — confirm any new "
            "code is necessary; mobile fallback should live in CSS, not Python"
        )
