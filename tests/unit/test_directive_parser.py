"""Tests for the directive parser (Phase 2).

Covers: :::type fences, prose between fences, backward compat,
unclosed fences, integration with copy_parser section parsers.
"""

from dazzle.core.directive_parser import process_markdown_with_directives


class TestNoDirectives:
    """When no fences are present, returns a single markdown section."""

    def test_plain_prose(self) -> None:
        raw = "Hello world.\n\nThis is a paragraph."
        sections = process_markdown_with_directives(raw)
        assert len(sections) == 1
        assert sections[0]["type"] == "markdown"
        assert "Hello world" in sections[0]["content"]

    def test_empty_string(self) -> None:
        sections = process_markdown_with_directives("")
        assert sections == []

    def test_whitespace_only(self) -> None:
        sections = process_markdown_with_directives("   \n\n  ")
        assert sections == []


class TestSingleDirective:
    """A single :::type ... ::: fence produces one typed section."""

    def test_features_directive(self) -> None:
        raw = """:::features
## Fast Performance
Our app is blazingly fast.

## Easy to Use
Simple and intuitive interface.
:::"""
        sections = process_markdown_with_directives(raw)
        assert len(sections) == 1
        assert sections[0]["type"] == "features"
        assert "items" in sections[0]
        items = sections[0]["items"]
        assert len(items) == 2
        assert items[0]["title"] == "Fast Performance"

    def test_cta_directive(self) -> None:
        raw = """:::cta
## Ready to start?
[Sign Up Free](/signup)
:::"""
        sections = process_markdown_with_directives(raw)
        assert len(sections) == 1
        s = sections[0]
        assert s["type"] == "cta"
        assert s.get("headline") == "Ready to start?"
        assert "primary_cta" in s

    def test_faq_directive(self) -> None:
        raw = """:::faq
## What is this?
It is a product.

## How much does it cost?
It is free.
:::"""
        sections = process_markdown_with_directives(raw)
        assert len(sections) == 1
        assert sections[0]["type"] == "faq"
        items = sections[0].get("items", [])
        assert len(items) == 2
        assert items[0]["question"] == "What is this"


class TestProseAndDirectives:
    """Prose between fences becomes markdown sections."""

    def test_prose_before_directive(self) -> None:
        raw = """Some intro text.

:::features
## Feature A
Description A.
:::"""
        sections = process_markdown_with_directives(raw)
        assert len(sections) == 2
        assert sections[0]["type"] == "markdown"
        assert "intro text" in sections[0]["content"]
        assert sections[1]["type"] == "features"

    def test_prose_between_directives(self) -> None:
        raw = """:::features
## Feature A
Description A.
:::

Middle paragraph here.

:::cta
## Join Us
[Sign Up](/signup)
:::"""
        sections = process_markdown_with_directives(raw)
        assert len(sections) == 3
        assert sections[0]["type"] == "features"
        assert sections[1]["type"] == "markdown"
        assert "Middle paragraph" in sections[1]["content"]
        assert sections[2]["type"] == "cta"

    def test_prose_after_directive(self) -> None:
        raw = """:::cta
## Go
[Click](/go)
:::

Footer text here."""
        sections = process_markdown_with_directives(raw)
        assert len(sections) == 2
        assert sections[0]["type"] == "cta"
        assert sections[1]["type"] == "markdown"
        assert "Footer text" in sections[1]["content"]


class TestMultipleDirectives:
    """Multiple directives produce correct section sequence."""

    def test_three_directives(self) -> None:
        raw = """:::hero
**Welcome**
:::

:::features
## A
Desc A.
:::

:::cta
## Ready?
[Go](/go)
:::"""
        sections = process_markdown_with_directives(raw)
        types = [s["type"] for s in sections]
        assert types == ["hero", "features", "cta"]


class TestUnclosedFence:
    """Unclosed ::: is treated as prose (no crash)."""

    def test_unclosed_directive_becomes_prose(self) -> None:
        raw = """Some text.

:::features
## Feature A
Description A.
"""
        sections = process_markdown_with_directives(raw)
        # Should not raise. The unclosed fence is treated as prose.
        assert len(sections) >= 1
        # First section is the prose before the fence
        # Second (if present) is the unclosed content treated as markdown
        for s in sections:
            assert "type" in s

    def test_completely_unclosed(self) -> None:
        raw = ":::features"
        sections = process_markdown_with_directives(raw)
        assert len(sections) >= 1


class TestNormalization:
    """Directive type names are normalized via copy_parser."""

    def test_testimonials_alias(self) -> None:
        raw = """:::testimonials
> "Great product."
> — Jane Doe, CEO at Corp
:::"""
        sections = process_markdown_with_directives(raw)
        assert sections[0]["type"] == "testimonials"

    def test_unknown_type_generic(self) -> None:
        raw = """:::custom-thing
## Something
Body text.
:::"""
        sections = process_markdown_with_directives(raw)
        assert sections[0]["type"] == "custom-thing"
