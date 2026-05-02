"""Linter for ADR-0022 — `<template x-for>` with Alpine-bound children.

Walks every `*.html` under `src/dazzle_ui/templates/` and finds every
`<template x-for=...>` block whose immediate child element carries any
Alpine-style attribute (`x-*`, `:`, or `@` prefixed). Each match is a
candidate for the #970-class regression: idiomorph evaluates the
cloned children's bindings before Alpine re-establishes the x-for scope.

ADR-0022 codifies the policy. Two exceptions are kept:
  1. The element itself owns its `x-data` scope (rebinds via destroyTree
     + initTree on morph)
  2. The element is in a region that is genuinely never htmx-morphed
     (e.g. global toast container, command palette overlay)

The linter handles both via an explicit ALLOWLIST of `(file, anchor)`
tuples — the anchor is a substring of the line's `x-for=...` expression
that uniquely identifies the use. Adding a new entry requires verifying
the location is outside any htmx-morph region AND adding a comment in
the template explaining why the exception is safe.

To clean up false positives: refactor the template to use an `x-init`
helper (canonical pattern: `dzFilterRefSelect` in `dz-alpine.js`).
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "src" / "dazzle_ui" / "templates"

# Strip Jinja `{# ... #}` comments first so historical-context comments
# (e.g. "previously used <template x-for>...") don't trip the linter.
_JINJA_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)

# Match an opening <template x-for=...> tag. Capture the x-for expression
# so we can match against the allowlist.
_TEMPLATE_XFOR_RE = re.compile(
    r'<template\b[^>]*\bx-for\s*=\s*["\']([^"\']*)["\'][^>]*>',
    re.IGNORECASE,
)

# Match the FIRST element after the <template ...> tag. <template x-for>
# requires exactly one element child; whitespace + comments between
# template-open and the child element are ignored.
#
# We strip leading whitespace + comment runs imperatively (see
# `_skip_leading_whitespace_and_comments` below) instead of expressing
# the comment-skip in the regex, because nested quantifiers like
# `(?:<!--.*?-->\s*)*` exhibit catastrophic backtracking on inputs of
# the shape `<!--<!--<!--...` (CodeQL py/redos).
_FIRST_CHILD_TAG_RE = re.compile(
    r"<(\w+)((?:\s+[^>]*)?)>",
    re.DOTALL,
)
_LEADING_COMMENT_RE = re.compile(r"\s*<!--.*?-->", re.DOTALL)


def _skip_leading_whitespace_and_comments(text: str) -> str:
    """Trim leading whitespace + HTML comment runs from *text*.

    Linear-time alternative to a regex with nested quantifiers — each
    iteration consumes at least one character, so the worst case is
    O(n) on the input length.
    """
    while True:
        stripped = text.lstrip()
        match = _LEADING_COMMENT_RE.match(stripped)
        if match is None:
            return stripped
        text = stripped[match.end() :]


# Alpine-style attribute name patterns. Match attribute NAMES at word
# boundary, before the `=` sign.
#   x-*   — Alpine's longhand directives (x-text, x-bind, x-show, etc.)
#   :*    — Alpine's bind shorthand (:value, :class, :data-foo)
#   @*    — Alpine's event shorthand (@click, @keyup.window)
_ALPINE_ATTR_RE = re.compile(
    r"""(?:^|\s)
        (
          x-[a-z][a-z0-9-]*   # x-* directives
          | :[a-z][a-z0-9.-]* # :foo bind shorthand
          | @[a-z][a-z0-9.-]* # @event shorthand
        )
        (?=\s*=|\s|/?>|$)
    """,
    re.VERBOSE | re.IGNORECASE,
)


# (relative-path, anchor-substring-in-x-for-expression)
# Adding to this list requires verifying the location is outside any
# htmx-morph region AND a comment in the template explaining why.
ALLOWLIST: set[tuple[str, str]] = {
    # base.html toast container — global, rendered once outside any
    # morphable target. dzToast is initialised at app boot and the
    # toast list is mutated via Alpine reactivity inside that scope;
    # htmx swaps never touch this region.
    ("base.html", "t in toasts"),
    # command_palette.html — Cmd+K spotlight. Rendered at the document
    # body level, opens via Alpine x-show; htmx morph targets are scoped
    # to #main-content / region containers, never the palette.
    ("fragments/command_palette.html", "(action, idx) in filtered"),
}


def _strip_jinja_comments(text: str) -> str:
    return _JINJA_COMMENT_RE.sub("", text)


def _find_violations() -> list[str]:
    """Return a list of human-readable violations."""
    violations: list[str] = []
    for path in sorted(TEMPLATE_DIR.rglob("*.html")):
        rel = path.relative_to(TEMPLATE_DIR)
        text = _strip_jinja_comments(path.read_text())
        for match in _TEMPLATE_XFOR_RE.finditer(text):
            xfor_expr = match.group(1)
            allowlisted = any(
                str(rel) == listed_path and anchor in xfor_expr
                for (listed_path, anchor) in ALLOWLIST
            )
            # Slice out the rest of the file after this <template> tag and
            # find the first element child. Whitespace + HTML comments
            # between template-open and the child are stripped imperatively
            # (linear time) before matching the tag regex — avoids the
            # exponential-backtracking shape CodeQL py/redos warned about.
            tail = _skip_leading_whitespace_and_comments(text[match.end() :])
            child = _FIRST_CHILD_TAG_RE.match(tail)
            if not child:
                continue  # ill-formed; not our problem here
            child_attrs = child.group(2) or ""
            alpine_attrs = sorted(set(_ALPINE_ATTR_RE.findall(child_attrs)))
            if not alpine_attrs:
                continue  # template x-for with non-Alpine child — fine
            line_no = text[: match.start()].count("\n") + 1
            label = (
                f'{rel}:{line_no} — `<template x-for="{xfor_expr}">` child '
                f"<{child.group(1)}> carries Alpine attrs: {alpine_attrs}"
            )
            if allowlisted:
                continue  # verified outside morphable region
            violations.append(label)
    return violations


def test_no_template_xfor_with_alpine_children_in_framework_templates() -> None:
    """ADR-0022: no `<template x-for>` whose child carries Alpine attrs.

    Each match is the #970-class shape (idiomorph evaluates bindings on
    cloned children before Alpine re-establishes scope). Two cures:

      1. Refactor to an `x-init` helper that populates children
         imperatively (canonical: `dzFilterRefSelect` in dz-alpine.js)
      2. If the region is genuinely never htmx-morphed, add to the
         ALLOWLIST in this test with a comment explaining why
    """
    violations = _find_violations()
    assert not violations, (
        "ADR-0022 violations found — `<template x-for>` with Alpine-bound "
        "children is forbidden in framework templates because idiomorph "
        "evaluates the cloned children's bindings before Alpine "
        "re-establishes the x-for scope (#970-class regression).\n\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nFixes:\n"
        "  • Refactor to an x-init helper that populates children "
        "imperatively (canonical: dzFilterRefSelect in dz-alpine.js)\n"
        "  • If the region is genuinely never htmx-morphed, add to the "
        "ALLOWLIST in this test with a comment explaining why\n"
    )


def test_allowlist_entries_still_exist() -> None:
    """ALLOWLIST entries must point at real template uses.

    A stale entry (file moved, x-for expression renamed) silently masks
    drift — you'd think you're allowlisting the toast container but
    the actual code has changed. Pin the relationship by re-finding
    each allowlist entry in the live templates.
    """
    for listed_path, anchor in ALLOWLIST:
        path = TEMPLATE_DIR / listed_path
        assert path.exists(), f"ALLOWLIST entry references non-existent file: {listed_path}"
        text = _strip_jinja_comments(path.read_text())
        found = False
        for match in _TEMPLATE_XFOR_RE.finditer(text):
            if anchor in match.group(1):
                found = True
                break
        assert found, (
            f"ALLOWLIST entry ({listed_path!r}, {anchor!r}) doesn't match any "
            "<template x-for> in the file. Either remove the stale entry "
            "or update the anchor to match the current x-for expression."
        )


def test_alpine_attr_detection() -> None:
    """Sanity: the regex catches the three Alpine-style prefixes."""
    samples = [
        ('class="foo" :value="x"', [":value"]),
        ('x-text="x.label" class="foo"', ["x-text"]),
        ('@click="open()" @click.away="close()"', ["@click", "@click.away"]),
        ('class="foo" data-static="x"', []),  # plain HTML, no Alpine
    ]
    for attrs_text, expected in samples:
        found = sorted(set(_ALPINE_ATTR_RE.findall(attrs_text)))
        assert found == sorted(expected), (
            f"For attrs {attrs_text!r}: expected {expected}, got {found}"
        )
