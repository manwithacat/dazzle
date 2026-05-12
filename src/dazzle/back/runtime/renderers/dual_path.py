"""Phase 4B.3 — dual-path validation harness (residual byte-equivalence comparator).

Phase 4 (v0.67.59): the legacy-vs-typed dual-path renderers
(`render_via_legacy`, `render_via_typed`, `_LEGACY_TEMPLATE`,
`_StubRegion`) were retired alongside the v0.67.52 DISPLAY_TEMPLATE_MAP
flip — only 4 region templates remain on disk (`_typed_primitive.html`,
`audit_history.html`, `radar.html`, `tab_data.html`), so the 30+
template paths the legacy renderer dispatched to are mostly gone.

What's preserved here are the two byte-equivalence helpers
(`normalise_html`, `diff_summary`) that downstream typed-Fragment
tests still use to compare two HTML outputs without caring about
insignificant whitespace.
"""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")
_AFTER_OPEN_BRACKET = re.compile(r">\s+")
_BEFORE_CLOSE_BRACKET = re.compile(r"\s+<")
_BEFORE_SELF_CLOSE = re.compile(r"\s+/>")
# Strip whitespace before `>` when preceded by an attribute boundary
# (closing quote or word char). Catches Jinja `{% if %}…{% endif %}`
# artifacts that leave trailing space inside the opening tag, e.g.
# `<details class="x" >`. Scoped to attribute boundaries to avoid
# touching `< 5` in text content (script/SVG-path).
_BEFORE_TAG_CLOSE = re.compile(r'(["\w])\s+>')


def normalise_html(html: str) -> str:
    """Collapse insignificant whitespace for byte-equivalence comparison.

    Steps:
      1. Strip whitespace immediately after every `>` (handles both
         inter-tag gaps and leading whitespace inside text content
         that follows a tag).
      2. Strip whitespace immediately before every `<` (handles both
         inter-tag gaps and trailing whitespace before a closing tag).
      3. Collapse internal whitespace runs to a single space (handles
         intra-text-content whitespace).
      4. Trim leading/trailing whitespace.

    Does NOT preserve `<pre>` whitespace — the harness compares
    workspace regions where pre-formatted content doesn't appear, and
    aggressive normalisation makes Jinja-template indentation
    whitespace (around `{{ value }}` expressions) match the typed
    renderer's compact output.

    Does NOT reorder attributes — the typed FragmentRenderer emits
    deterministic order, so byte comparisons are stable.
    """
    s = _AFTER_OPEN_BRACKET.sub(">", html)
    s = _BEFORE_CLOSE_BRACKET.sub("<", s)
    # Canonicalize self-closing tags: `<tag />` and `<tag/>` are
    # equivalent XML; some renderers emit one form, some the other.
    s = _BEFORE_SELF_CLOSE.sub("/>", s)
    # Strip whitespace before `>` left by Jinja `{% if %}…{% endif %}`
    # blocks inside opening tags (e.g. `<details class="x" >`).
    s = _BEFORE_TAG_CLOSE.sub(r"\1>", s)
    s = _WHITESPACE.sub(" ", s)
    return s.strip()


def diff_summary(legacy_html: str, typed_html: str) -> str | None:
    """Return None if the two outputs are equivalent (after normalisation),
    or a short diff-summary string describing the mismatch.

    Useful for parametrised pytest assertions: `assert
    diff_summary(a, b) is None` gives a readable failure message for
    every byte-equivalent display port.
    """
    a = normalise_html(legacy_html)
    b = normalise_html(typed_html)
    if a == b:
        return None
    # Find first divergence position for a useful failure message.
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            ctx_start = max(0, i - 30)
            return (
                f"diverged at char {i}: "
                f"legacy=…{a[ctx_start : i + 30]!r} "
                f"typed=…{b[ctx_start : i + 30]!r}"
            )
    return f"length mismatch: legacy={len(a)} typed={len(b)}"


__all__ = [
    "diff_summary",
    "normalise_html",
]
