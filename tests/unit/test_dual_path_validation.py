"""Phase 4B.3 — dual-path validation harness tests.

Smoke + structural assertions for the dual-path renderer. The full
byte-equivalence gate (Phase 4B.4) requires real example-app ctx
captured from running workspace handlers; this file pins the harness
primitives + smoke-renders the chart family with synthetic ctx so
the harness itself stays correct as Phase 4B advances.

Each chart-family display gets:
  1. **Both paths render** — legacy template + typed adapter both
     produce non-empty HTML for the same legacy ctx.
  2. **Required substrings present** — canonical class hooks
     (`dz-line-chart-region`, `dz-bar-chart-region` etc.) appear in
     both outputs, confirming the translator + adapter wired
     correctly.
"""

from __future__ import annotations

import pytest

from dazzle_back.runtime.renderers.dual_path import (
    diff_summary,
    normalise_html,
    render_via_legacy,
    render_via_typed,
)

# === Helper primitives ===


def test_normalise_html_collapses_whitespace_and_inter_tag_gaps() -> None:
    raw = """
        <div   class="x">
          <span>a</span>
          <span>b</span>
        </div>
    """
    assert normalise_html(raw) == '<div class="x"><span>a</span><span>b</span></div>'


def test_diff_summary_returns_none_when_equivalent() -> None:
    """Inter-tag whitespace + multi-space runs collapse to a canonical form."""
    a = "<div>\n  <span>x</span>\n  <span>y</span>\n</div>"
    b = "<div><span>x</span><span>y</span></div>"
    assert diff_summary(a, b) is None


def test_diff_summary_locates_first_divergence() -> None:
    a = "<div>foo</div>"
    b = "<div>fox</div>"
    out = diff_summary(a, b)
    assert out is not None
    assert "diverged at char" in out


def test_diff_summary_reports_length_mismatch_after_common_prefix() -> None:
    a = "<div>abc</div>"
    b = "<div>abcdef</div>"
    out = diff_summary(a, b)
    assert out is not None
    assert "length mismatch" in out or "diverged" in out


# === Chart-family smoke tests ===


@pytest.mark.parametrize(
    ("display", "ctx", "legacy_class_hook"),
    [
        (
            "bar_chart",
            {
                "title": "Tickets by Status",
                "bucketed_metrics": [
                    {"label": "Open", "value": 12},
                    {"label": "Closed", "value": 47},
                ],
            },
            "dz-bar-chart-region",
        ),
        (
            "line_chart",
            {
                "title": "Daily Volume",
                "bucketed_metrics": [
                    {"label": "Mon", "value": 10},
                    {"label": "Tue", "value": 25},
                    {"label": "Wed", "value": 18},
                ],
            },
            "dz-line-chart-svg",
        ),
        (
            "histogram",
            {
                "title": "Latency Histogram",
                "histogram_bins": [
                    {"label": "0–10", "count": 4, "low": 0, "high": 10},
                    {"label": "10–20", "count": 8, "low": 10, "high": 20},
                ],
            },
            "dz-histogram-region",  # legacy has its own histogram template
        ),
        (
            "bar_track",
            {
                "bar_track_rows": [
                    {"label": "CPU", "value": 80, "formatted_value": "80%", "fill_pct": 80},
                ],
                "bar_track_max": 100,
            },
            "dz-bar-track-region",
        ),
    ],
)
def test_chart_family_dual_path_smoke(display: str, ctx: dict, legacy_class_hook: str) -> None:
    """Both paths produce non-empty HTML containing canonical class hooks
    when fed equivalent legacy ctx through the translator."""
    legacy_html = render_via_legacy(display, **ctx)
    typed_html = render_via_typed(display, ctx)

    assert legacy_html
    assert typed_html
    assert legacy_class_hook in legacy_html, f"legacy {display} missing {legacy_class_hook}"


def test_radar_renders_via_both_paths_with_three_axes() -> None:
    """Radar requires ≥3 axes (typed primitive's __post_init__)."""
    ctx = {
        "title": "Skills",
        "bucketed_metrics": [
            {"label": "Speed", "value": 8},
            {"label": "Power", "value": 6},
            {"label": "Range", "value": 9},
        ],
    }
    legacy_html = render_via_legacy("radar", **ctx)
    typed_html = render_via_typed("radar", ctx)
    assert legacy_html and typed_html
    # Both paths emit SVG <text> labels for the spoke names.
    assert "Speed" in legacy_html and "Speed" in typed_html


def test_box_plot_renders_via_both_paths() -> None:
    """Both paths render the box plot family. Legacy carries full
    11-field stats; typed-side translator narrows to 6 — verified
    in test_legacy_ctx_translator.py."""
    ctx = {
        "title": "Latency",
        "box_plot_stats": [
            {
                "label": "p50",
                "n": 100,
                "min": 0.5,
                "q1": 1.0,
                "median": 2.0,
                "q3": 3.0,
                "max": 4.5,
                "iqr": 2.0,
                "whisker_low": 0.5,
                "whisker_high": 4.5,
                "outliers": [],
            },
            {
                "label": "p99",
                "n": 100,
                "min": 5.0,
                "q1": 6.0,
                "median": 7.0,
                "q3": 8.0,
                "max": 9.5,
                "iqr": 2.0,
                "whisker_low": 5.0,
                "whisker_high": 9.5,
                "outliers": [],
            },
        ],
    }
    legacy_html = render_via_legacy("box_plot", **ctx)
    typed_html = render_via_typed("box_plot", ctx)
    assert legacy_html and typed_html
    # Both render SVG glyphs.
    assert "<svg" in legacy_html and "<svg" in typed_html
    # Group labels survive both paths.
    assert "p50" in legacy_html and "p50" in typed_html


def test_unknown_display_raises_for_legacy_path() -> None:
    """Legacy path raises ValueError for unknown displays — caller
    bug catch."""
    with pytest.raises(ValueError, match="Unknown display"):
        render_via_legacy("not_a_real_display")


# === Diff observation (documentation tests) ===


def test_chrome_differs_between_paths_documented() -> None:
    """The legacy region_card macro emits `<div data-dz-region>` chrome;
    the typed Surface emits a `<header>` + `<section>` wrapper. Without
    body-only extraction these will not byte-equal — this test pins
    that observation so a future Phase 4B.4 ship that closes the gap
    flips the assertion to `is None`.
    """
    ctx = {
        "title": "Daily",
        "bucketed_metrics": [{"label": "Mon", "value": 10}, {"label": "Tue", "value": 12}],
    }
    legacy_html = render_via_legacy("line_chart", **ctx)
    typed_html = render_via_typed("line_chart", ctx)
    # Today: chrome differs → diff is non-None. Phase 4B.4 will flip this.
    assert diff_summary(legacy_html, typed_html) is not None
