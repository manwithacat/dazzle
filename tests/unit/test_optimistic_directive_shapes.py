"""Tests for #959 cycle 2 — prepend / append / replace shapes.

Cycle 1 shipped `remove`. Cycle 2 unifies all four shapes under
the same directive: `remove`, `prepend`, `append`, `replace`.
The new shapes need a placeholder element (sourced from
`x-optimistic-template` or a generic loading div) and `replace`
combines the cycle-1 snapshot pattern with placeholder insertion.

Browser-level behaviour (htmx event sequencing, DOM mutation
ordering) isn't testable without a browser harness — these pin
the registration path, the verb-set, the placeholder builder,
and the dispatch contracts via string checks on the bundled JS.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DZ_ALPINE_JS = (
    Path(__file__).resolve().parents[2] / "src/dazzle/page/runtime/static/js/dz-alpine.js"
)


@pytest.fixture(scope="module")
def js() -> str:
    return DZ_ALPINE_JS.read_text()


# ---------------------------------------------------------------------------
# Verb set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verb", ["remove", "prepend", "append", "replace"])
def test_verb_in_known_set(js: str, verb: str) -> None:
    """Each cycle-2 verb must be recognised — drift would silently
    log an "unknown shape" warning and no-op."""
    # Verbs appear inside the KNOWN_VERBS Set literal.
    set_idx = js.find("KNOWN_VERBS = new Set([")
    assert set_idx != -1, "KNOWN_VERBS Set declaration missing"
    # Read forward to the closing bracket of the array literal.
    end_idx = js.find("]", set_idx)
    assert end_idx > set_idx
    set_block = js[set_idx:end_idx]
    assert f'"{verb}"' in set_block


def test_unknown_verb_warns_with_known_list(js: str) -> None:
    """Future readers should see the list of accepted verbs in the
    warning so they can correct typos quickly."""
    assert "not recognised" in js
    assert "Known shapes" in js


# ---------------------------------------------------------------------------
# Placeholder builder
# ---------------------------------------------------------------------------


def test_placeholder_builder_present(js: str) -> None:
    """All three new shapes need a placeholder; the builder is
    shared across them."""
    assert "buildPlaceholder" in js


def test_placeholder_uses_template_attribute(js: str) -> None:
    """`x-optimistic-template="<id>"` opts into a custom placeholder.
    The builder reads the attribute and clones the referenced
    `<template>` content."""
    assert "x-optimistic-template" in js
    assert "tpl.content" in js
    assert "cloneNode" in js


def test_placeholder_falls_back_to_generic_div(js: str) -> None:
    """Without a template attribute, the builder synthesises a
    generic loading div — adopters get a working primitive even
    without authoring a placeholder template."""
    assert "dz-optimistic-placeholder" in js
    assert "aria-busy" in js  # screenreader cue while pending


def test_placeholder_marked_with_data_attribute(js: str) -> None:
    """The `data-dz-optimistic-placeholder` attribute lets adopters
    style placeholders independently and lets the directive find
    its own placeholders for cleanup."""
    assert "data-dz-optimistic-placeholder" in js


# ---------------------------------------------------------------------------
# Per-verb DOM operations
# ---------------------------------------------------------------------------


class TestPrepend:
    def test_uses_insertBefore_at_firstChild(self, js: str) -> None:
        """Prepend = `target.insertBefore(placeholder, target.firstChild)`
        — the standard DOM idiom for "insert at start of children"."""
        # Find the prepend branch
        idx = js.find('verb === "prepend"')
        assert idx != -1
        block = js[idx : idx + 400]
        assert "insertBefore" in block
        assert "firstChild" in block


class TestAppend:
    def test_uses_appendChild(self, js: str) -> None:
        idx = js.find('verb === "append"')
        assert idx != -1
        block = js[idx : idx + 300]
        assert "appendChild(placeholder)" in block


class TestReplace:
    def test_snapshots_original_before_replace(self, js: str) -> None:
        """Replace must capture the original node's parent +
        nextSibling so it can be restored on rollback (same shape
        as remove's snapshot)."""
        idx = js.find('verb === "replace"')
        assert idx != -1
        block = js[idx : idx + 600]
        assert "snapshot = {" in block
        assert "nextSibling" in block

    def test_uses_replaceChild_for_swap(self, js: str) -> None:
        """`parent.replaceChild(placeholder, target)` is the atomic
        swap — alternative `removeChild` + `insertBefore` is two
        operations and risks a layout flicker between them."""
        idx = js.find('verb === "replace"')
        assert idx != -1
        block = js[idx : idx + 600]
        assert "replaceChild" in block


# ---------------------------------------------------------------------------
# Cycle-2 rollback — extends cycle-1 contract
# ---------------------------------------------------------------------------


class TestRollback:
    def test_remove_placeholder_helper_present(self, js: str) -> None:
        """Cleanup function shared across success + rollback paths.
        Defensive: only acts if placeholder + parent both exist."""
        assert "removePlaceholder" in js

    def test_rollback_carries_verb_in_event_detail(self, js: str) -> None:
        """The CustomEvent.detail should include the verb so adopter
        recovery hooks can branch on what was attempted."""
        idx = js.find('"dz:optimistic-rollback"')
        assert idx != -1
        block = js[idx : idx + 400]
        assert "verb: verb" in block

    def test_success_path_clears_placeholder_and_snapshot(self, js: str) -> None:
        """Stale state risk: a later event firing on the same element
        could re-trigger restore() with a stale snapshot. After a
        successful response, both placeholder and snapshot must be
        cleared."""
        # Cycle-3 + cycle-4 expanded the success branch substantially
        # (undo entry construction + reconcile dispatch). Widen the
        # window further; the closing `snapshot = null` lives near the
        # end of the success branch.
        idx = js.find("if (ok) {")
        assert idx != -1
        block = js[idx : idx + 5000]
        assert "removePlaceholder()" in block
        assert "snapshot = null" in block


# ---------------------------------------------------------------------------
# Cycle-1 contract — must still hold after the cycle-2 refactor
# ---------------------------------------------------------------------------


class TestCycle1ContractIntact:
    def test_remove_still_works(self, js: str) -> None:
        """The cycle-1 remove handler stays intact — string-test
        the inner branch."""
        idx = js.find('verb === "remove"')
        assert idx != -1
        block = js[idx : idx + 400]
        assert "removeChild(target)" in block

    def test_event_subscription_set_unchanged(self, js: str) -> None:
        """All three htmx lifecycle events must still be subscribed —
        cycle 2 just adds shape variation, not new lifecycle phases."""
        assert 'addEventListener("htmx:before:request"' in js
        assert 'addEventListener("htmx:after:request"' in js
        assert 'addEventListener("htmx:error"' in js

    def test_target_filter_intact(self, js: str) -> None:
        """ev.target !== el guard must still gate every handler so
        bubbled child events don't trigger the wrong rollback."""
        # Count occurrences — should be at least 3 (one per handler).
        assert js.count("ev.target !== el") >= 3


# ---------------------------------------------------------------------------
# Bundle inclusion
# ---------------------------------------------------------------------------


def test_present_in_dist_bundle() -> None:
    dist_js = (
        Path(__file__).resolve().parents[2] / "src/dazzle/page/runtime/static/dist/dazzle.min.js"
    )
    if not dist_js.is_file():
        pytest.skip("dist not built")
    text = dist_js.read_text()
    # All four verbs must survive minification (string literals
    # aren't mangled).
    for verb in ("remove", "prepend", "append", "replace"):
        assert f'"{verb}"' in text or f"'{verb}'" in text
    assert "data-dz-optimistic-placeholder" in text
