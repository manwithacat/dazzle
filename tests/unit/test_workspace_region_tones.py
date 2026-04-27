"""Tests for the v0.61.65 region `tones:` block.

The AegisMark UX patterns roadmap (item #2) — metric tiles in the
SIMS-sync-opt-in prototype carry per-tile accent strips so authors can
distinguish a "good" count (resolved) from a "bad" one (errors) at a
glance. Promoting tones to a region-level dict mirrors `aggregate:`,
keeps the per-metric vocabulary together, and reuses the action_grid
tone tokens (positive / warning / destructive / accent / neutral).

See ``dev_docs/2026-04-27-aegismark-ux-patterns.md`` for the full
roadmap context.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.module import ModuleFragment


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"

entity Item:
  id: uuid pk

workspace dash "Dash":
  metrics:
    source: Item
    display: metrics
    aggregate:
      active: count(Item)
      resolved: count(Item where status = closed)
      errors: count(Item where status = error)
"""


# ───────────────────────── parser ──────────────────────────


class TestTonesParser:
    def test_default_is_empty_dict(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.tones == {}

    def test_single_tone(self) -> None:
        src = _BASE_DSL + "    tones:\n      active: positive\n"
        region = _parse(src).workspaces[0].regions[0]
        assert region.tones == {"active": "positive"}

    def test_multiple_tones(self) -> None:
        src = (
            _BASE_DSL
            + "    tones:\n"
            + "      active: positive\n"
            + "      resolved: accent\n"
            + "      errors: destructive\n"
        )
        region = _parse(src).workspaces[0].regions[0]
        assert region.tones == {
            "active": "positive",
            "resolved": "accent",
            "errors": "destructive",
        }

    def test_tone_for_unknown_metric_is_allowed(self) -> None:
        """The parser does not validate that metric names exist in
        `aggregate:` — that's a job for the linter (future). Keeping
        the parser permissive lets authors stage tones and aggregates
        independently."""
        src = _BASE_DSL + "    tones:\n      ghost: warning\n"
        region = _parse(src).workspaces[0].regions[0]
        assert region.tones == {"ghost": "warning"}

    def test_tones_does_not_affect_aggregates(self) -> None:
        src_with = _BASE_DSL + "    tones:\n      active: positive\n"
        r_with = _parse(src_with).workspaces[0].regions[0]
        r_without = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert r_with.aggregates == r_without.aggregates
        assert r_with.source == r_without.source
        assert r_with.display == r_without.display


# ───────────────────────── identifier round-trip ──────────────────────────


class TestTonesAsIdentifier:
    """`tones` is a new keyword in v0.61.65. Per the #899 fix pattern,
    it MUST remain usable as an identifier elsewhere — added to
    KEYWORD_AS_IDENTIFIER_TYPES."""

    def test_tones_in_keyword_identifier_list(self) -> None:
        from dazzle.core.dsl_parser_impl.base import KEYWORD_AS_IDENTIFIER_TYPES
        from dazzle.core.lexer import TokenType

        assert TokenType.TONES in KEYWORD_AS_IDENTIFIER_TYPES

    def test_tones_as_field_name(self) -> None:
        src = """module t
app t "Test"

entity Skin:
  id: uuid pk
  tones: int
"""
        entity = _parse(src).entities[0]
        field_names = [f.name for f in entity.fields]
        assert "tones" in field_names


# ───────────────────────── runtime + template wiring ──────────────────────────


class TestTonesRuntimeWiring:
    def test_region_context_default_empty_dict(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r")
        assert ctx.tones == {}

    def test_region_context_carries_tones(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r", tones={"active": "positive"})
        assert ctx.tones == {"active": "positive"}


class TestComputeAggregateMetricsTones:
    """`_compute_aggregate_metrics` must attach `tone` to each metric
    dict whose name has a tones[] entry, and omit the key entirely
    when no tone is configured (so existing tile templates branch
    cleanly on `metric.tone is defined`)."""

    @pytest.mark.asyncio
    async def test_metrics_get_tone_when_configured(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _compute_aggregate_metrics

        metrics = await _compute_aggregate_metrics(
            aggregates={"active": "count", "resolved": "count"},
            repositories=None,
            total=42,
            items=[],
            tones={"active": "positive", "resolved": "accent"},
        )
        by_label = {m["label"]: m for m in metrics}
        assert by_label["Active"]["tone"] == "positive"
        assert by_label["Resolved"]["tone"] == "accent"

    @pytest.mark.asyncio
    async def test_metric_without_tone_omits_key(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _compute_aggregate_metrics

        metrics = await _compute_aggregate_metrics(
            aggregates={"active": "count", "untoned": "count"},
            repositories=None,
            total=10,
            items=[],
            tones={"active": "positive"},
        )
        by_label = {m["label"]: m for m in metrics}
        assert by_label["Active"]["tone"] == "positive"
        assert "tone" not in by_label["Untoned"], (
            "Untoned metrics must omit the tone key — existing templates "
            "branch on `metric.tone is defined`"
        )

    @pytest.mark.asyncio
    async def test_no_tones_dict_leaves_metrics_untouched(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _compute_aggregate_metrics

        metrics = await _compute_aggregate_metrics(
            aggregates={"active": "count"},
            repositories=None,
            total=5,
            items=[],
            tones=None,
        )
        assert "tone" not in metrics[0]


class TestTonesTemplateBinding:
    """The metrics template must surface a per-tile background tint
    when `metric.tone` is set, and fall through to the default muted
    background otherwise."""

    def _template_text(self) -> str:
        path = (
            Path(__file__).resolve().parents[2]
            / "src/dazzle_ui/templates/workspace/regions/metrics.html"
        )
        return path.read_text()

    def test_template_reads_metric_tone(self) -> None:
        text = self._template_text()
        assert "metric.tone" in text, (
            "metrics.html dropped `metric.tone` binding — AegisMark roadmap item #2 lost"
        )

    def test_template_emits_data_dz_tone_attribute(self) -> None:
        """v0.61.70 (#906): tone tints come from `dz-tones.css` keyed
        off `data-dz-tone`, NOT from inline Tailwind arbitrary-value
        classes (those were JIT-invisible and shipped without rules).
        The template must still emit the attribute so the CSS can
        match it. The actual per-tone branches are pinned in
        `test_dz_tones_css.py::TestDzTonesCssRulesPresent`."""
        text = self._template_text()
        assert 'data-dz-tone="' in text, (
            "metrics.html must emit data-dz-tone — dz-tones.css keys off it"
        )


# ───────────────────────── invariants ──────────────────────────


class TestTonesIsPresentationOnly:
    """Like region `class:` and `eyebrow:`, tones is a pure
    presentation hook — no impact on data, scope, or aggregates."""

    def test_tones_does_not_change_metric_value(self) -> None:
        import asyncio

        from dazzle_back.runtime.workspace_rendering import _compute_aggregate_metrics

        async def run() -> tuple[list[dict], list[dict]]:
            with_tones = await _compute_aggregate_metrics(
                aggregates={"active": "count"},
                repositories=None,
                total=100,
                items=[],
                tones={"active": "positive"},
            )
            without_tones = await _compute_aggregate_metrics(
                aggregates={"active": "count"},
                repositories=None,
                total=100,
                items=[],
                tones=None,
            )
            return with_tones, without_tones

        with_t, without_t = asyncio.run(run())
        assert with_t[0]["value"] == without_t[0]["value"]
        assert with_t[0]["label"] == without_t[0]["label"]
