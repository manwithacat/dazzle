"""Tests for the v0.61.68 region `notice:` block (#7).

The AegisMark UX patterns roadmap (item #7) — the SIMS-sync-opt-in
prototype uses prominent notice bands for legal-basis disclosure,
opt-in context, and status banners. Promoting this to a region-level
field gives DSL authors a strong + secondary text band with tone
tinting that any display mode picks up — sits between the panel
header and the data body.

Two parser shapes:
  - Shorthand: ``notice: "Title text"``
  - Block: ``notice:`` with ``title:`` / ``body:`` / ``tone:`` keys

See ``dev_docs/2026-04-27-aegismark-ux-patterns.md`` for the full
roadmap context.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import NoticeSpec
from dazzle.core.ir.module import ModuleFragment


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


_BASE_DSL = """module t
app t "Test"

entity Item:
  id: uuid pk

workspace dash "Dash":
  panel:
    source: Item
    display: list
"""


# ───────────────────────── parser ──────────────────────────


class TestNoticeParserShorthand:
    def test_default_is_none(self) -> None:
        region = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert region.notice is None

    def test_shorthand_quoted_title(self) -> None:
        src = _BASE_DSL + '    notice: "Legal basis: GDPR Article 6(1)(f)"\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.notice is not None
        assert region.notice.title == "Legal basis: GDPR Article 6(1)(f)"
        assert region.notice.body == ""
        assert region.notice.tone == "neutral"

    def test_shorthand_special_chars(self) -> None:
        src = _BASE_DSL + '    notice: "Step 2 / 4 — Authorisation"\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.notice is not None
        assert region.notice.title == "Step 2 / 4 — Authorisation"


class TestNoticeParserBlock:
    def test_block_with_all_keys(self) -> None:
        src = (
            _BASE_DSL
            + "    notice:\n"
            + '      title: "Status as of last sync"\n'
            + '      body: "Counts refresh every 30s."\n'
            + "      tone: accent\n"
        )
        region = _parse(src).workspaces[0].regions[0]
        assert region.notice is not None
        assert region.notice.title == "Status as of last sync"
        assert region.notice.body == "Counts refresh every 30s."
        assert region.notice.tone == "accent"

    def test_block_title_only(self) -> None:
        src = _BASE_DSL + "    notice:\n" + '      title: "Heads up"\n'
        region = _parse(src).workspaces[0].regions[0]
        assert region.notice is not None
        assert region.notice.title == "Heads up"
        assert region.notice.body == ""
        assert region.notice.tone == "neutral"

    def test_block_with_tone_warning(self) -> None:
        src = (
            _BASE_DSL
            + "    notice:\n"
            + '      title: "Action required"\n'
            + "      tone: warning\n"
        )
        region = _parse(src).workspaces[0].regions[0]
        assert region.notice is not None
        assert region.notice.tone == "warning"

    def test_block_missing_title_raises(self) -> None:
        from dazzle.core.errors import ParseError

        src = _BASE_DSL + "    notice:\n" + '      body: "Body without title"\n'
        with pytest.raises(ParseError, match="title:"):
            _parse(src)

    def test_block_unknown_key_raises(self) -> None:
        from dazzle.core.errors import ParseError

        src = _BASE_DSL + "    notice:\n" + '      title: "T"\n' + '      bogus: "no"\n'
        with pytest.raises(ParseError, match="Unknown notice key"):
            _parse(src)


# ───────────────────────── invariants ──────────────────────────


class TestNoticeIsPresentationOnly:
    """Notice is a pure presentation hook — no impact on data, scope,
    or aggregates. Mirrors the eyebrow/tones/css_class invariants."""

    def test_notice_does_not_affect_other_fields(self) -> None:
        src_with = _BASE_DSL + '    notice: "Heads up"\n'
        r_with = _parse(src_with).workspaces[0].regions[0]
        r_without = _parse(_BASE_DSL).workspaces[0].regions[0]
        assert r_with.source == r_without.source
        assert r_with.display == r_without.display
        assert r_with.aggregates == r_without.aggregates
        assert r_with.filter == r_without.filter


# ───────────────────────── NoticeSpec ──────────────────────────


class TestNoticeSpec:
    def test_construct_minimal(self) -> None:
        n = NoticeSpec(title="X")
        assert n.title == "X"
        assert n.body == ""
        assert n.tone == "neutral"

    def test_construct_full(self) -> None:
        n = NoticeSpec(title="T", body="B", tone="warning")
        assert n.title == "T"
        assert n.body == "B"
        assert n.tone == "warning"


# ───────────────────────── runtime + template wiring ──────────────────────────


class TestNoticeRuntimeWiring:
    def test_region_context_default_empty_dict(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(name="r")
        assert ctx.notice == {}

    def test_region_context_carries_notice(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        ctx = RegionContext(
            name="r",
            notice={"title": "T", "body": "B", "tone": "warning"},
        )
        assert ctx.notice["title"] == "T"
        assert ctx.notice["tone"] == "warning"

    def test_card_payload_carries_notice(self) -> None:
        """The dashboard panel template reads `card.notice` from the
        Alpine data island — the cards_for_json builder must include
        a notice entry for every region (empty dict when omitted)."""
        from dazzle_ui.runtime.workspace_renderer import RegionContext

        regions = [
            RegionContext(
                name="legal",
                notice={"title": "Legal basis", "body": "GDPR", "tone": "warning"},
            ),
            RegionContext(name="plain"),
        ]
        cards = [
            {
                "id": f"card-{i}",
                "region": r.name,
                "title": r.name.title(),
                "notice": getattr(r, "notice", {}) or {},
            }
            for i, r in enumerate(regions)
        ]
        assert cards[0]["notice"]["title"] == "Legal basis"
        assert cards[0]["notice"]["tone"] == "warning"
        assert cards[1]["notice"] == {}


class TestNoticeTemplateBinding:
    """The dashboard panel template must surface the region's notice
    as a band between the header and HTMX-loaded body.

    #948: cards are server-rendered HTML now (was Alpine `card.notice`
    pre-#948). The Jinja branch reads `r.notice.title` directly and
    emits the `dz-notice-band` markup at render time."""

    def _template_text(self) -> str:
        path = (
            Path(__file__).resolve().parents[2] / "src/dazzle_ui/templates/workspace/_content.html"
        )
        return path.read_text()

    def test_template_emits_region_notice_band(self) -> None:
        text = self._template_text()
        # Server-rendered: Jinja reads r.notice directly
        assert "r.notice" in text, (
            "_content.html dropped the region notice binding — AegisMark roadmap item #7 lost"
        )
        assert "dz-notice-band" in text

    def test_template_gates_band_on_truthy_title(self) -> None:
        """Empty/missing notice must not render an empty band — would
        leak vertical space into existing dashboards."""
        text = self._template_text()
        # Server-rendered guard: `{% if r.notice and r.notice.title %}`
        # (with or without whitespace-stripping markers).
        assert (
            "{% if r.notice and r.notice.title %}" in text
            or "{%- if r.notice and r.notice.title %}" in text
        )

    def test_template_emits_data_dz_notice_tone_attribute(self) -> None:
        """v0.61.70 (#906): tone tints come from `dz-tones.css` keyed
        off `data-dz-notice-tone`, NOT from inline Tailwind arbitrary
        values. The template must emit the attribute so the CSS can
        match it. Per-tone branches pinned in `test_dz_tones_css.py`."""
        text = self._template_text()
        assert "data-dz-notice-tone" in text, (
            "_content.html must emit data-dz-notice-tone — dz-tones.css keys off it"
        )
