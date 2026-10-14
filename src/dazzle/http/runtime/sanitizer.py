"""
Input sanitization for single-line string fields.

``strip_html_tags`` removes every tag from ``str``/``email``/``url``/``slug``
and enum values on write (#135). Multi-line ``text`` values are not altered:
they are data, escaped wherever they are rendered into HTML, and
``widget=rich_text`` fields are cleaned by the allowlist sanitiser
``richtext_field.clean_rich_text`` (flense ships T and W, ADR-0057).
"""

import re

# Pattern that matches all HTML tags
_ALL_TAGS_RE = re.compile(r"<[^>]+>")


def strip_html_tags(text: str) -> str:
    """Strip all HTML tags from a string field value.

    Use for plain ``str`` fields where no markup is expected.
    Preserves the text content between tags.

    Args:
        text: Input text that may contain HTML tags

    Returns:
        Text with all HTML tags removed
    """
    if not text:
        return text
    return _ALL_TAGS_RE.sub("", text)
