"""Tests for structured content pages (Phases 1 + 3).

Phase 1: SectionKind.MARKDOWN, SectionSpec.source, hybrid pages.
Phase 3: New section types (comparison, value_highlight, split_content,
         card_grid, trust_bar) and their IR models.
"""

from dazzle.core.ir.sitespec import (
    CardItem,
    ComparisonColumn,
    ComparisonRow,
    ContentSourceSpec,
    CTASpec,
    MediaSpec,
    SectionKind,
    SectionSpec,
    TrustBarItem,
)

# =========================================================================
# Phase 1: Markdown sections
# =========================================================================


class TestMarkdownSectionKind:
    """SectionKind.MARKDOWN exists and is valid."""

    def test_markdown_enum_value(self) -> None:
        assert SectionKind.MARKDOWN == "markdown"
        assert SectionKind("markdown") is SectionKind.MARKDOWN

    def test_section_spec_accepts_markdown(self) -> None:
        section = SectionSpec(type=SectionKind.MARKDOWN)
        assert section.type == SectionKind.MARKDOWN

    def test_section_spec_source_field(self) -> None:
        source = ContentSourceSpec(path="pages/about.md")
        section = SectionSpec(
            type=SectionKind.MARKDOWN,
            source=source,
        )
        assert section.source is not None
        assert section.source.path == "pages/about.md"

    def test_section_spec_source_defaults_none(self) -> None:
        section = SectionSpec(type=SectionKind.HERO, headline="Hi")
        assert section.source is None

    def test_hybrid_page_mixed_sections(self) -> None:
        """A page can interleave hero, markdown, and cta sections."""
        from dazzle.core.ir.sitespec import PageKind, PageSpec

        page = PageSpec(
            route="/about",
            type=PageKind.LANDING,
            title="About",
            sections=[
                SectionSpec(
                    type=SectionKind.HERO,
                    headline="About Us",
                ),
                SectionSpec(
                    type=SectionKind.MARKDOWN,
                    source=ContentSourceSpec(path="pages/about-story.md"),
                ),
                SectionSpec(
                    type=SectionKind.CTA,
                    headline="Join us",
                    primary_cta=CTASpec(label="Sign Up", href="/signup"),
                ),
            ],
        )
        assert len(page.sections) == 3
        assert page.sections[0].type == SectionKind.HERO
        assert page.sections[1].type == SectionKind.MARKDOWN
        assert page.sections[2].type == SectionKind.CTA


# =========================================================================
# Phase 3: New section types
# =========================================================================


class TestComparisonSection:
    """Comparison section type with columns and rows."""

    def test_comparison_enum(self) -> None:
        assert SectionKind.COMPARISON == "comparison"

    def test_comparison_column(self) -> None:
        col = ComparisonColumn(label="Us", highlighted=True)
        assert col.label == "Us"
        assert col.highlighted is True

    def test_comparison_row(self) -> None:
        row = ComparisonRow(
            feature="SSO",
            cells=["Yes", "No", "Add-on"],
        )
        assert row.feature == "SSO"
        assert len(row.cells) == 3

    def test_comparison_section_spec(self) -> None:
        section = SectionSpec(
            type=SectionKind.COMPARISON,
            headline="How we compare",
            columns=[
                ComparisonColumn(label="Us", highlighted=True),
                ComparisonColumn(label="Competitor A"),
            ],
            items=[
                ComparisonRow(feature="Price", cells=["$29", "$49"]),
                ComparisonRow(feature="Support", cells=["24/7", "Email"]),
            ],
        )
        assert len(section.columns) == 2
        assert len(section.items) == 2


class TestValueHighlightSection:
    """Value highlight section (large typography callout)."""

    def test_value_highlight_enum(self) -> None:
        assert SectionKind.VALUE_HIGHLIGHT == "value_highlight"

    def test_value_highlight_uses_headline_body_ctas(self) -> None:
        section = SectionSpec(
            type=SectionKind.VALUE_HIGHLIGHT,
            headline="10x faster deployments",
            subhead="Ship with confidence",
            body="Our platform reduces deploy time by 90%.",
            primary_cta=CTASpec(label="Try Free", href="/signup"),
        )
        assert section.headline == "10x faster deployments"
        assert section.body is not None
        assert section.primary_cta is not None


class TestSplitContentSection:
    """Split content section (text + image)."""

    def test_split_content_enum(self) -> None:
        assert SectionKind.SPLIT_CONTENT == "split_content"

    def test_split_content_with_alignment(self) -> None:
        section = SectionSpec(
            type=SectionKind.SPLIT_CONTENT,
            headline="Built for teams",
            body="Collaborate in real time.",
            media=MediaSpec(kind="image", src="/img/team.png", alt="Team"),
            alignment="right",
        )
        assert section.alignment == "right"
        assert section.media is not None

    def test_alignment_defaults_none(self) -> None:
        section = SectionSpec(type=SectionKind.SPLIT_CONTENT)
        assert section.alignment is None


class TestCardGridSection:
    """Card grid section with per-card CTAs."""

    def test_card_grid_enum(self) -> None:
        assert SectionKind.CARD_GRID == "card_grid"

    def test_card_item(self) -> None:
        card = CardItem(
            title="Feature A",
            body="Description",
            icon="zap",
            cta=CTASpec(label="Learn More", href="/features/a"),
        )
        assert card.title == "Feature A"
        assert card.cta is not None
        assert card.icon == "zap"

    def test_card_grid_section_spec(self) -> None:
        section = SectionSpec(
            type=SectionKind.CARD_GRID,
            headline="Solutions",
            items=[
                CardItem(title="A", body="Desc A"),
                CardItem(title="B", body="Desc B"),
            ],
        )
        assert len(section.items) == 2


class TestTrustBarSection:
    """Trust bar section (horizontal signal strip)."""

    def test_trust_bar_enum(self) -> None:
        assert SectionKind.TRUST_BAR == "trust_bar"

    def test_trust_bar_item(self) -> None:
        item = TrustBarItem(text="SOC 2 Certified", icon="shield-check")
        assert item.text == "SOC 2 Certified"
        assert item.icon == "shield-check"

    def test_trust_bar_section_spec(self) -> None:
        section = SectionSpec(
            type=SectionKind.TRUST_BAR,
            items=[
                TrustBarItem(text="SOC 2"),
                TrustBarItem(text="GDPR"),
                TrustBarItem(text="99.9% Uptime"),
            ],
        )
        assert len(section.items) == 3


# =========================================================================
# Loader round-trip
# =========================================================================


class TestSitespecLoaderNewTypes:
    """Loader parses YAML data for new section types."""

    def test_parse_markdown_section(self) -> None:
        from dazzle.core.sitespec_loader import _parse_section

        data = {
            "type": "markdown",
            "source": {"path": "pages/about.md", "format": "md"},
        }
        section = _parse_section(data)
        assert section.type == SectionKind.MARKDOWN
        assert section.source is not None
        assert section.source.path == "pages/about.md"

    def test_parse_comparison_section(self) -> None:
        from dazzle.core.sitespec_loader import _parse_section

        data = {
            "type": "comparison",
            "headline": "Compare",
            "columns": [
                {"label": "Us", "highlighted": True},
                {"label": "Them"},
            ],
            "items": [
                {"feature": "Price", "cells": ["$29", "$49"]},
            ],
        }
        section = _parse_section(data)
        assert section.type == SectionKind.COMPARISON
        assert len(section.columns) == 2
        assert section.columns[0].highlighted is True
        assert len(section.items) == 1

    def test_parse_card_grid_with_cta(self) -> None:
        from dazzle.core.sitespec_loader import _parse_section

        data = {
            "type": "card_grid",
            "headline": "Solutions",
            "items": [
                {
                    "title": "Card A",
                    "body": "Desc",
                    "cta": {"label": "Go", "href": "/a"},
                },
            ],
        }
        section = _parse_section(data)
        assert section.type == SectionKind.CARD_GRID
        assert len(section.items) == 1
        assert section.items[0].cta is not None  # type: ignore[union-attr]

    def test_parse_trust_bar_section(self) -> None:
        from dazzle.core.sitespec_loader import _parse_section

        data = {
            "type": "trust_bar",
            "items": [
                {"text": "SOC 2", "icon": "shield-check"},
                {"text": "GDPR"},
            ],
        }
        section = _parse_section(data)
        assert section.type == SectionKind.TRUST_BAR
        assert len(section.items) == 2

    def test_parse_split_content_section(self) -> None:
        from dazzle.core.sitespec_loader import _parse_section

        data = {
            "type": "split_content",
            "headline": "Built for teams",
            "body": "Collaborate.",
            "alignment": "right",
            "media": {"kind": "image", "src": "/img/t.png"},
        }
        section = _parse_section(data)
        assert section.type == SectionKind.SPLIT_CONTENT
        assert section.alignment == "right"
        assert section.media is not None

    def test_parse_value_highlight_section(self) -> None:
        from dazzle.core.sitespec_loader import _parse_section

        data = {
            "type": "value_highlight",
            "headline": "10x faster",
            "body": "We make it quick.",
            "primary_cta": {"label": "Try", "href": "/try"},
        }
        section = _parse_section(data)
        assert section.type == SectionKind.VALUE_HIGHLIGHT
        assert section.primary_cta is not None


# =========================================================================
# Copy parser new mappings
# =========================================================================


class TestCopyParserNewMappings:
    """copy_parser._normalize_section_type maps new aliases."""

    def test_comparison_aliases(self) -> None:
        from dazzle.core.copy_parser import _normalize_section_type

        assert _normalize_section_type("Comparison") == "comparison"
        assert _normalize_section_type("Compare") == "comparison"
        assert _normalize_section_type("VS") == "comparison"

    def test_card_grid_aliases(self) -> None:
        from dazzle.core.copy_parser import _normalize_section_type

        assert _normalize_section_type("Cards") == "card-grid"
        assert _normalize_section_type("Card Grid") == "card-grid"

    def test_trust_bar_aliases(self) -> None:
        from dazzle.core.copy_parser import _normalize_section_type

        assert _normalize_section_type("Trust Bar") == "trust-bar"
        assert _normalize_section_type("Trust") == "trust-bar"
        assert _normalize_section_type("Trust Signals") == "trust-bar"

    def test_value_highlight_aliases(self) -> None:
        from dazzle.core.copy_parser import _normalize_section_type

        assert _normalize_section_type("Value Highlight") == "value-highlight"
        assert _normalize_section_type("Highlight") == "value-highlight"

    def test_split_content_aliases(self) -> None:
        from dazzle.core.copy_parser import _normalize_section_type

        assert _normalize_section_type("Split Content") == "split-content"
        assert _normalize_section_type("Split") == "split-content"


# =========================================================================
# Dark mode CSS for new types
# =========================================================================


class TestDarkModeNewSectionTypes:
    """Dark mode rules exist for new section types."""

    def test_dark_mode_rules_for_new_sections(self) -> None:
        from pathlib import Path

        css_path = Path(
            "src/dazzle_ui/runtime/static/css/site-sections.css",
        )
        css = css_path.read_text()

        for cls in [
            ".dz-section-comparison",
            ".dz-section-value-highlight",
            ".dz-section-card-grid",
            ".dz-section-trust-bar",
            ".dz-section-split-content",
        ]:
            assert cls in css, f"Missing CSS for {cls}"

        # Check dark mode overrides exist
        assert '[data-theme="dark"] .dz-section-comparison' in css
        assert '[data-theme="dark"] .dz-section-card-grid' in css
        assert '[data-theme="dark"] .dz-card-item' in css
