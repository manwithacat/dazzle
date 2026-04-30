"""Tests for #970 — filter dropdown ref-entity branch must not use `<template x-for>`.

Background: `fragments/filter_bar.html` previously rendered the ref-entity
filter's `<option>` list via `<template x-for="opt in options">` with
`:value="opt.value" x-text="opt.label"` bindings. Idiomorph's
attribute-morph loop evaluated those bindings on cloned `<option>`
elements before Alpine re-established the x-for scope, throwing
`Alpine Expression Error: opt is not defined` once per option per morph
(300 such errors in a 5-min site-fuzz on AegisMark).

Fix: drop the x-for. Append plain `<option>` elements via direct DOM
manipulation in `x-init`. The morph then sees ordinary DOM nodes with no
Alpine attributes — nothing for idiomorph to evaluate prematurely.

Same bug class as #963 / #964 / #968 (Alpine bindings vs htmx morph
timing). The fix pattern is "remove Alpine bindings from elements that
will be morphed."
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FILTER_BAR = REPO_ROOT / "src" / "dazzle_ui" / "templates" / "fragments" / "filter_bar.html"


_JINJA_COMMENT_RE = __import__("re").compile(r"\{#.*?#\}", __import__("re").DOTALL)


def _strip_jinja_comments(text: str) -> str:
    """Remove Jinja `{# ... #}` blocks so historical-context comments
    don't trip drift gates that look for forbidden patterns."""
    return _JINJA_COMMENT_RE.sub("", text)


def test_no_template_xfor_in_ref_entity_branch() -> None:
    """The ref-entity filter branch must not use `<template x-for>`."""
    html = _strip_jinja_comments(FILTER_BAR.read_text())
    # Find the ref-entity filter block (the first {% if %} branch).
    ref_branch_start = html.find("filter_ref_entity")
    assert ref_branch_start >= 0, "missing ref-entity filter branch"
    next_elif = html.find("{% elif", ref_branch_start)
    assert next_elif > ref_branch_start
    ref_branch = html[ref_branch_start:next_elif]
    assert "x-for=" not in ref_branch, (
        "Ref-entity filter branch contains `x-for=` — this re-introduces "
        "#970. Use direct DOM manipulation in x-init instead (see the "
        "comment in filter_bar.html for context)."
    )
    assert "<template" not in ref_branch, (
        "Ref-entity filter branch contains `<template>` — Alpine "
        "templates inside htmx-morphed regions trigger the #970 bug "
        "class. Use plain DOM manipulation."
    )


def test_ref_entity_delegates_to_helper_via_xinit() -> None:
    """Population logic lives in dzFilterRefSelect helper (in dz-alpine.js),
    not inline in x-init. Keeps the template free of JS that mixes Jinja
    interpolation with logic — the #966 / #968 bug class."""
    html = _strip_jinja_comments(FILTER_BAR.read_text())
    ref_branch_start = html.find("filter_ref_entity")
    next_elif = html.find("{% elif", ref_branch_start)
    ref_branch = html[ref_branch_start:next_elif]
    assert "dzFilterRefSelect" in ref_branch, (
        "Ref-entity filter branch must invoke `dzFilterRefSelect($el)` "
        "from x-init — the population logic moved to dz-alpine.js (#970)."
    )
    # The selected value and ref API endpoint must travel via data-*
    # attrs, not inline tojson interpolation in JS.
    assert "data-ref-api" in ref_branch, "data-ref-api attribute missing"
    assert "data-selected-value" in ref_branch, "data-selected-value attribute missing"


def test_helper_function_present_in_dz_alpine_js() -> None:
    """The `dzFilterRefSelect` helper must exist in dz-alpine.js."""
    dz_alpine = REPO_ROOT / "src" / "dazzle_ui" / "runtime" / "static" / "js" / "dz-alpine.js"
    js = dz_alpine.read_text()
    assert "window.dzFilterRefSelect" in js or "dz.filterRefSelect" in js, (
        "Missing dzFilterRefSelect helper in dz-alpine.js — needed by "
        "filter_bar.html ref-entity x-init (#970)."
    )
    assert "createElement" in js and "appendChild" in js, (
        "dz-alpine.js helper must populate options via direct DOM "
        "manipulation (createElement + appendChild) so options stay free "
        "of Alpine bindings idiomorph would morph prematurely (#970)."
    )
