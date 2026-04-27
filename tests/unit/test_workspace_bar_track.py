"""Tests for the v0.61.53 bar_track display mode (#893).

Three layers:
  1. Parser: ``display: bar_track`` + ``track_max:`` + ``track_format:``
     parse into the IR. The data path reuses the existing single-dim
     `group_by` + `aggregates` pipeline — no new vocabulary needed.
  2. Runtime: when `display == "BAR_TRACK"` and `bucketed_metrics` is
     populated (via `_compute_bucketed_aggregates` — same path as
     bar_chart), post-process into row dicts with `fill_pct` (clamped
     to [0, 100]) and `formatted_value` (Python `format()` applied).
     Auto-max when `track_max:` is omitted.
  3. Template: `bar_track.html` renders one row per bucket with
     pill-shaped track, fill width = `fill_pct`, formatted value on
     right; honours empty-state fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import DisplayMode
from dazzle.core.ir.module import ModuleFragment


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"
entity Score:
  id: uuid pk
  ao: enum[ao1,ao2,ao3]
  confidence: float
workspace dash "Dash":
  ao_confidence:
    source: Score
    display: bar_track
    group_by: ao
    aggregate:
      value: avg(confidence)
"""


# ───────────────────────────── parser ──────────────────────────────


class TestBarTrackParser:
    def test_minimal_bar_track(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.display == DisplayMode.BAR_TRACK
        assert region.group_by == "ao"
        assert "value" in region.aggregates
        # Defaults: no explicit max, no format spec
        assert region.track_max is None
        assert region.track_format is None

    def test_track_max_parses(self) -> None:
        src = _BASE_DSL + "    track_max: 1.0\n"
        region = _parse(src).workspaces[0].regions[0]
        assert region.track_max == 1.0

    def test_track_max_int_coerces_to_float(self) -> None:
        src = _BASE_DSL + "    track_max: 100\n"
        region = _parse(src).workspaces[0].regions[0]
        assert region.track_max == 100.0
        assert isinstance(region.track_max, float)

    def test_track_format_parses(self) -> None:
        src = _BASE_DSL + '    track_format: "{:.0%}"\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.track_format == "{:.0%}"

    def test_track_format_must_be_quoted(self) -> None:
        """Format specs commonly contain `:` and `{}` which don't
        tokenise as bare identifiers — quoted string is required."""
        from dazzle.core.errors import ParseError

        src = _BASE_DSL + "    track_format: {:.0%}\n"
        with pytest.raises(ParseError):
            _parse(src)

    def test_full_repro_dsl_from_issue(self) -> None:
        """The exact DSL shape from #893 — modulo the rows/track_value
        keyword aliases that were collapsed into the existing
        group_by/aggregates vocabulary."""
        src = """module t
app t "Test"
entity MarkingResult:
  id: uuid pk
  assessment_objective: enum[ao1,ao2,ao3]
  confidence: float
workspace dash "Dash":
  ao_confidence_stack:
    source: MarkingResult
    display: bar_track
    group_by: assessment_objective
    aggregate:
      value: avg(confidence)
    track_max: 1.0
    track_format: "{:.0%}"
    empty: "No confidence data yet."
"""
        region = _parse(src).workspaces[0].regions[0]
        assert region.display == DisplayMode.BAR_TRACK
        assert region.track_max == 1.0
        assert region.track_format == "{:.0%}"
        assert region.empty_message == "No confidence data yet."


# ───────────────────────── runtime post-processing ─────────────────────────


def _build_rows(
    bucketed_metrics: list[dict],
    track_max: float | None,
    track_format: str = "",
):
    """Helper that mirrors the runtime post-processing logic — kept
    in the test file so we can exercise the math without booting a
    workspace renderer."""
    _values: list[float] = []
    for b in bucketed_metrics:
        try:
            _values.append(float(b.get("value") or 0))
        except (TypeError, ValueError):
            _values.append(0.0)
    bar_track_max = (
        float(track_max)
        if track_max is not None
        else (max(_values) if _values and max(_values) > 0 else 1.0)
    )
    rows = []
    for b, v in zip(bucketed_metrics, _values, strict=True):
        fill_pct = max(0.0, min(100.0, (v / bar_track_max) * 100.0)) if bar_track_max else 0.0
        try:
            if not track_format:
                formatted = str(v)
            elif "{" in track_format:
                formatted = track_format.format(v)
            else:
                formatted = format(v, track_format)
        except (ValueError, TypeError, KeyError, IndexError):
            formatted = str(v)
        rows.append(
            {
                "label": str(b.get("label") or ""),
                "value": v,
                "fill_pct": fill_pct,
                "formatted_value": formatted,
            }
        )
    return rows, bar_track_max


class TestBarTrackPostProcessing:
    """The runtime turns `bucketed_metrics` (label/value dicts from the
    standard chart pipeline) into `bar_track_rows` with `fill_pct`
    (0-100, clamped) and `formatted_value` (format spec applied)."""

    def test_explicit_track_max_drives_fill_pct(self) -> None:
        buckets = [
            {"label": "AO1", "value": 0.5},
            {"label": "AO2", "value": 0.75},
            {"label": "AO3", "value": 1.0},
        ]
        rows, track_max = _build_rows(buckets, track_max=1.0, track_format="{:.0%}")
        assert track_max == 1.0
        assert rows[0]["fill_pct"] == 50.0
        assert rows[1]["fill_pct"] == 75.0
        assert rows[2]["fill_pct"] == 100.0

    def test_auto_max_uses_largest_bucket(self) -> None:
        """When `track_max:` is omitted, the runtime auto-scales to the
        largest bucket so all bars fit in [0, 1] of the track."""
        buckets = [
            {"label": "A", "value": 5.0},
            {"label": "B", "value": 10.0},
            {"label": "C", "value": 7.5},
        ]
        rows, track_max = _build_rows(buckets, track_max=None)
        assert track_max == 10.0
        assert rows[0]["fill_pct"] == 50.0
        assert rows[1]["fill_pct"] == 100.0
        assert rows[2]["fill_pct"] == 75.0

    def test_format_spec_applied(self) -> None:
        buckets = [{"label": "A", "value": 0.847}]
        rows, _ = _build_rows(buckets, track_max=1.0, track_format="{:.0%}")
        assert rows[0]["formatted_value"] == "85%"

    def test_format_spec_thousands_sep(self) -> None:
        buckets = [{"label": "Q1", "value": 12345.0}]
        rows, _ = _build_rows(buckets, track_max=20000.0, track_format="{:,.0f}")
        assert rows[0]["formatted_value"] == "12,345"

    def test_no_format_spec_uses_str(self) -> None:
        buckets = [{"label": "A", "value": 42.0}]
        rows, _ = _build_rows(buckets, track_max=100.0)
        assert rows[0]["formatted_value"] == "42.0"

    def test_invalid_format_spec_falls_back_to_str(self) -> None:
        """Malformed format spec (e.g. `{:zz}`) must not crash the
        dashboard — fall back to raw str so the page still renders."""
        buckets = [{"label": "A", "value": 5.0}]
        rows, _ = _build_rows(buckets, track_max=10.0, track_format="{:zz}")
        # Falls back to str(value)
        assert rows[0]["formatted_value"] == "5.0"

    def test_value_above_track_max_clamps_to_100(self) -> None:
        """Values above the explicit max clamp to 100% fill so the bar
        doesn't overflow the track visually."""
        buckets = [{"label": "A", "value": 1.5}]
        rows, _ = _build_rows(buckets, track_max=1.0)
        assert rows[0]["fill_pct"] == 100.0

    def test_negative_value_clamps_to_zero(self) -> None:
        """Negative values clamp to 0% — bar doesn't render in
        negative space (the issue notes this is a future
        enhancement)."""
        buckets = [{"label": "A", "value": -5.0}]
        rows, _ = _build_rows(buckets, track_max=10.0)
        assert rows[0]["fill_pct"] == 0.0

    def test_empty_buckets_yields_empty_rows(self) -> None:
        rows, track_max = _build_rows([], track_max=None)
        assert rows == []
        # Auto-max falls back to 1.0 to avoid div-by-zero downstream
        assert track_max == 1.0

    def test_zero_value_yields_zero_fill(self) -> None:
        buckets = [{"label": "A", "value": 0.0}]
        rows, _ = _build_rows(buckets, track_max=1.0)
        assert rows[0]["fill_pct"] == 0.0
        assert rows[0]["formatted_value"] == "0.0"

    def test_non_numeric_value_treated_as_zero(self) -> None:
        """Defensive: malformed bucket values shouldn't crash the
        post-processor — coerce to 0.0."""
        buckets = [{"label": "A", "value": "not a number"}]
        rows, _ = _build_rows(buckets, track_max=10.0)
        assert rows[0]["value"] == 0.0
        assert rows[0]["fill_pct"] == 0.0


# ───────────────────────── template wiring ─────────────────────────


class TestBarTrackTemplateWiring:
    """The template path map and renderer wiring must be in place for
    the runtime branch to find `bar_track.html`."""

    def test_template_map_includes_bar_track(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "BAR_TRACK" in DISPLAY_TEMPLATE_MAP
        assert DISPLAY_TEMPLATE_MAP["BAR_TRACK"] == "workspace/regions/bar_track.html"

    def test_template_file_exists(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/bar_track.html"
        )
        assert path.is_file(), "bar_track.html template missing"

    def test_template_uses_region_card_macro(self) -> None:
        """Card-safety invariant — every region template wraps content
        in the `region_card` macro so chrome lives in the dashboard
        slot, not the region itself."""
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/bar_track.html"
        )
        contents = path.read_text()
        assert "region_card" in contents, "bar_track.html missing region_card wrapper"
        assert "{% call region_card" in contents, "region_card not invoked"

    def test_region_context_carries_bar_track_fields(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r", track_max=1.0, track_format="{:.0%}")
        assert ctx.track_max == 1.0
        assert ctx.track_format == "{:.0%}"

    def test_region_context_defaults(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r")
        assert ctx.track_max is None
        assert ctx.track_format == ""

    def test_bar_track_in_single_dim_chart_modes(self) -> None:
        """The runtime must include BAR_TRACK in the single-dim chart
        mode set so `_compute_bucketed_aggregates` fires for it.
        Static check on the source — if a future edit drops BAR_TRACK
        from the set, the bar_track region would silently render
        with zero buckets."""
        src = (
            Path(__file__).resolve().parents[2] / "src/dazzle_back/runtime/workspace_rendering.py"
        ).read_text()
        # The set literal must mention BAR_TRACK as a single-dim mode.
        assert '"BAR_TRACK"' in src, "BAR_TRACK missing from single-dim chart modes"
        # Spot-check the surrounding _single_dim_chart_modes context.
        assert "_single_dim_chart_modes" in src
