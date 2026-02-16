"""Text manipulation helpers for MCP handler functions."""

from __future__ import annotations

import re


def slugify(text: str) -> str:
    """Convert text to a snake_case slug (max 30 chars)."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    return text[:30]


def extract_issue_key(message: str) -> str:
    """Extract ``Entity.field`` key from a lint/validation message.

    Falls back to a truncated message if no entity/field pattern is found.
    """
    entity_match = re.search(r"[Ee]ntity ['\"](\w+)['\"]", message)
    field_match = re.search(r"[Ff]ield ['\"](\w+)['\"]", message)

    if entity_match and field_match:
        return f"{entity_match.group(1)}.{field_match.group(1)}"
    if entity_match:
        return entity_match.group(1)

    return message[:80] if len(message) > 80 else message
