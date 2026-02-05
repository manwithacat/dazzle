"""
Directive parser for markdown content with structured section fences.

Parses ``:::type ... :::`` fences within markdown content to produce
typed section dicts. Prose between fences becomes ``{type: "markdown"}``
sections. If no fences are found the entire content is returned as a
single markdown section (backward compatible).

Directive syntax::

    Prose paragraph rendered as markdown.

    :::features
    ## Fast Performance
    Our app is blazingly fast.

    ## Easy to Use
    Simple and intuitive interface.
    :::

    More prose here.

    :::cta
    ## Ready to start?
    [Sign Up Free](/signup)
    :::

Entry point:
    ``process_markdown_with_directives(raw, fmt) -> list[dict]``

The ``_parse_*_section()`` functions in :mod:`dazzle.core.copy_parser` are
reused for typed blocks so the parsing logic stays in one place.
"""

from __future__ import annotations

import re
from typing import Any

from dazzle.core.copy_parser import (
    _normalize_section_type,
    _parse_cta_section,
    _parse_faq_section,
    _parse_features_section,
    _parse_generic_section,
    _parse_hero_section,
    _parse_pricing_section,
    _parse_testimonials_section,
)

# Regex: ``:::type`` at the start of a line, optional trailing whitespace.
# The closing ``:::`` must also be at the start of a line.
_DIRECTIVE_OPEN = re.compile(r"^:::(\w[\w-]*)\s*$", re.MULTILINE)
_DIRECTIVE_CLOSE = re.compile(r"^:::\s*$", re.MULTILINE)


def process_markdown_with_directives(
    raw: str,
    fmt: str = "md",
) -> list[dict[str, Any]]:
    """Parse markdown with optional ``:::type`` directives into sections.

    Args:
        raw: Raw markdown content (before HTML rendering).
        fmt: Content format (``"md"`` or ``"html"``).

    Returns:
        List of section dicts. Each has at least a ``type`` key.
        Markdown sections include ``content`` (rendered HTML).
        Typed sections include fields extracted by the copy-parser.
    """
    sections: list[dict[str, Any]] = []
    pos = 0
    text = raw

    while pos < len(text):
        m_open = _DIRECTIVE_OPEN.search(text, pos)
        if m_open is None:
            # No more directives — remainder is prose
            prose = text[pos:].strip()
            if prose:
                sections.append(_make_markdown_section(prose, fmt))
            break

        # Prose before this directive
        prose = text[pos : m_open.start()].strip()
        if prose:
            sections.append(_make_markdown_section(prose, fmt))

        directive_type = m_open.group(1)
        body_start = m_open.end() + 1  # skip newline after :::type

        # Find closing :::
        m_close = _DIRECTIVE_CLOSE.search(text, body_start)
        if m_close is None:
            # Unclosed fence — treat rest as prose (no crash)
            remaining = text[m_open.start() :].strip()
            if remaining:
                sections.append(_make_markdown_section(remaining, fmt))
            break

        body = text[body_start : m_close.start()].strip()
        typed = _parse_directive_body(directive_type, body)
        sections.append(typed)

        pos = m_close.end()

    # Backward compat: no directives found → single markdown section
    if not sections and raw.strip():
        sections.append(_make_markdown_section(raw.strip(), fmt))

    return sections


def _make_markdown_section(
    raw_md: str,
    fmt: str = "md",
) -> dict[str, Any]:
    """Create a markdown section dict with rendered HTML content."""
    return {
        "type": "markdown",
        "content": _render(raw_md, fmt),
    }


def _render(raw: str, fmt: str) -> str:
    """Convert raw content to HTML."""
    if fmt in ("md", "markdown"):
        try:
            import markdown  # type: ignore[import-untyped]

            return str(
                markdown.markdown(raw, extensions=["extra", "sane_lists"]),
            )
        except ImportError:
            return raw
    return raw


def _parse_directive_body(
    directive_type: str,
    body: str,
) -> dict[str, Any]:
    """Parse the body of a ``:::type`` fence into a section dict.

    Reuses the copy_parser ``_parse_*_section()`` helpers.
    """
    normalized = _normalize_section_type(directive_type)

    # Map to copy_parser functions
    parsers = {
        "hero": _parse_hero_section,
        "features": _parse_features_section,
        "testimonials": _parse_testimonials_section,
        "pricing": _parse_pricing_section,
        "faq": _parse_faq_section,
        "cta": _parse_cta_section,
    }

    title = directive_type.replace("-", " ").title()
    parser = parsers.get(normalized)

    if parser is not None:
        block = parser(title, body)
    else:
        block = _parse_generic_section(title, normalized, body)

    # Convert ContentBlock to a section dict
    result: dict[str, Any] = {"type": normalized}

    if block.metadata:
        # Hero / CTA style: headline, subheadline, ctas
        if "headline" in block.metadata:
            result["headline"] = block.metadata["headline"]
        if "subheadline" in block.metadata:
            result["subhead"] = block.metadata["subheadline"]
        if "description" in block.metadata:
            result["subhead"] = block.metadata["description"]
        if "ctas" in block.metadata and block.metadata["ctas"]:
            ctas = block.metadata["ctas"]
            result["primary_cta"] = {
                "label": ctas[0].get("text", ""),
                "href": ctas[0].get("url", "/"),
            }
            if len(ctas) > 1:
                result["secondary_cta"] = {
                    "label": ctas[1].get("text", ""),
                    "href": ctas[1].get("url", "/"),
                }

    if block.subsections:
        result["items"] = block.subsections

    if block.title:
        result.setdefault("headline", block.title)

    return result
