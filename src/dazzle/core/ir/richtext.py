"""Rich-text schema — single source of truth for client + server.

Spec: dev_docs/2026-05-04-dz-richtext-spec.md (#977 cycle 4 §13.3).

The dz-richtext editor (`src/dazzle/page/runtime/static/js/dz-richtext.js`)
and the server-side `RichTextField` validator
(`src/dazzle/http/runtime/fields/richtext.py`) both read from this
module. Drift between client and server is caught by
`tests/unit/test_richtext_allowlist_parity.py`.

The schema is closed: anything outside this allowlist is dropped on
paste and on persist. This is the DSL principle (enumerable surface)
applied to rich text.
"""

from __future__ import annotations

import re
from typing import Final

# Block-level tags: each represents one paragraph-equivalent unit.
# `h1` is intentionally absent — the surface owns it (#983).
RICH_TEXT_BLOCK_TAGS: Final[frozenset[str]] = frozenset(
    {"p", "h2", "h3", "ul", "ol", "li", "blockquote", "pre"}
)

# Inline tags carry typographic emphasis and links. `a` carries `href`
# (the only attribute permitted anywhere in the schema).
RICH_TEXT_INLINE_TAGS: Final[frozenset[str]] = frozenset(
    {"strong", "em", "u", "s", "code", "a", "br"}
)

RICH_TEXT_ALLOWED_TAGS: Final[frozenset[str]] = RICH_TEXT_BLOCK_TAGS | RICH_TEXT_INLINE_TAGS

# Per-tag attribute allowlist. Empty for every tag except `a`.
RICH_TEXT_ALLOWED_ATTRS: Final[dict[str, frozenset[str]]] = {
    "a": frozenset({"href"}),
}

# Permitted href protocols / shapes. Compiled regex used by both
# client and server. Pattern intentionally simple and readable so the
# parity gate compares strings rather than ASTs.
RICH_TEXT_PROTOCOL_PATTERN: Final[str] = r"^(https?:|mailto:|/)"
RICH_TEXT_PROTOCOL_REGEX: Final[re.Pattern[str]] = re.compile(
    RICH_TEXT_PROTOCOL_PATTERN, re.IGNORECASE
)

# Default character cap on the *post-sanitisation* HTML string.
# Per-field overridable via `rich_text_max_length:` (cycle 5).
RICH_TEXT_MAX_LENGTH_DEFAULT: Final[int] = 50_000


def is_safe_href(href: str) -> bool:
    """True iff `href` matches the protocol allowlist."""
    return bool(RICH_TEXT_PROTOCOL_REGEX.match(href or ""))


__all__ = [
    "RICH_TEXT_ALLOWED_ATTRS",
    "RICH_TEXT_ALLOWED_TAGS",
    "RICH_TEXT_BLOCK_TAGS",
    "RICH_TEXT_INLINE_TAGS",
    "RICH_TEXT_MAX_LENGTH_DEFAULT",
    "RICH_TEXT_PROTOCOL_PATTERN",
    "RICH_TEXT_PROTOCOL_REGEX",
    "is_safe_href",
]
