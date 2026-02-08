"""
Input sanitization for string and text fields.

Provides HTML tag stripping to prevent XSS via the JSON API.
Jinja2 auto-escaping already protects SSR views, but API responses
must also be safe for client-side rendering.
"""

from __future__ import annotations

import re

# Pattern that matches all HTML tags
_ALL_TAGS_RE = re.compile(r"<[^>]+>")

# Dangerous tags (script, iframe, object, embed, etc.)
_DANGEROUS_TAGS_RE = re.compile(
    r"<\s*/?\s*(?:script|iframe|object|embed|applet|form|input|button|select|textarea)\b[^>]*>",
    re.IGNORECASE,
)

# Event handler attributes (onclick, onerror, onload, etc.)
_EVENT_HANDLER_RE = re.compile(
    r"\s+on\w+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE,
)

# javascript: protocol in href/src
_JS_PROTOCOL_RE = re.compile(
    r'(?:href|src|action)\s*=\s*["\']?\s*javascript:',
    re.IGNORECASE,
)


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


def strip_dangerous_tags(text: str) -> str:
    """Strip dangerous HTML tags and attributes from a text field value.

    Use for ``text`` fields where safe HTML (bold, italic, links) is
    acceptable but script injection must be prevented.

    Removes:
    - <script>, <iframe>, <object>, <embed>, <applet>, <form> and
      form-control tags
    - Event handler attributes (onclick, onerror, ...)
    - javascript: protocol URLs

    Args:
        text: Input text that may contain HTML

    Returns:
        Text with dangerous elements removed
    """
    if not text:
        return text
    result = _DANGEROUS_TAGS_RE.sub("", text)
    result = _EVENT_HANDLER_RE.sub("", result)
    result = _JS_PROTOCOL_RE.sub("", result)
    return result
