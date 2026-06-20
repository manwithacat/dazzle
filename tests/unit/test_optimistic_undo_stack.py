"""Tests for #959 cycle 3 — undo stack + Cmd+Z.

Cycle 3 adds a session-level undo stack (capped at 20 entries):
each successful optimistic mutation pushes an entry that knows
how to reverse itself. Cmd+Z (Ctrl+Z elsewhere) pops the most
recent entry, runs its undo function (DOM-level reversal for
remove/replace, plus a `dz:optimistic-undo` CustomEvent for
adopter-wired server-side reversal).

Browser-level behaviour (key event handling, focus, DOM state)
isn't testable without a browser harness — these tests pin the
stack contract, the keyboard handler shape, the per-verb undo
behaviour, and bundle inclusion.
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
# Stack data structure
# ---------------------------------------------------------------------------


def test_stack_declared_with_cap_constant(js: str) -> None:
    """The stack max size is named so refactors keep the cap."""
    assert "_DZ_OPTIMISTIC_UNDO_MAX = 20" in js
    assert "_dzOptimisticUndoStack = []" in js


def test_push_helper_evicts_oldest_when_full(js: str) -> None:
    """Past the cap, the oldest entry falls off — `Array.shift()`
    on the front of the queue."""
    assert "_pushOptimisticUndo" in js
    push_idx = js.find("function _pushOptimisticUndo")
    assert push_idx != -1
    block = js[push_idx : push_idx + 400]
    assert "_dzOptimisticUndoStack.length > _DZ_OPTIMISTIC_UNDO_MAX" in block
    assert "_dzOptimisticUndoStack.shift()" in block


def test_stack_exposed_as_window_global(js: str) -> None:
    """`window.dzOptimisticUndoStack` lets tests + adopters
    introspect history (e.g. show "12 actions can be undone")."""
    assert "window.dzOptimisticUndoStack" in js


# ---------------------------------------------------------------------------
# Keyboard handler
# ---------------------------------------------------------------------------


def test_global_keydown_handler_bound_once(js: str) -> None:
    """The keydown listener is registered at module level — same
    handler for every directive instance. The `_dzOptimisticUndoBound`
    sentinel prevents double-binding on hot reload / Alpine re-init."""
    assert "_dzOptimisticUndoBound" in js
    assert 'document.addEventListener("keydown"' in js


def test_handler_fires_on_cmd_or_ctrl_plus_z(js: str) -> None:
    """Cmd+Z on macOS, Ctrl+Z elsewhere. Both modifiers are checked
    so the same key combo works cross-platform."""
    assert 'e.key === "z"' in js
    assert "metaKey" in js
    assert "ctrlKey" in js


def test_handler_branches_on_shift_modifier(js: str) -> None:
    """Cycle 3 originally bailed on shiftKey to leave room for redo.
    Cycle 4 routes shiftKey into the redo branch; either way, the
    code must inspect `e.shiftKey` so the two chords are
    distinguishable."""
    assert "e.shiftKey" in js
    # Cycle 4 form — explicit shift→redo branch.
    assert "if (e.shiftKey)" in js


def test_handler_skips_when_user_is_typing(js: str) -> None:
    """Don't hijack undo while the user is editing text — the
    input's native undo handles their characters."""
    # Tag-name check or contentEditable check — both must be present.
    assert "input" in js and "textarea" in js
    assert "isContentEditable" in js


def test_handler_pops_and_runs_entry(js: str) -> None:
    """`stack.pop()` returns the most recent entry; `entry.undo()`
    runs the captured reversal."""
    handler_idx = js.find('document.addEventListener("keydown"')
    assert handler_idx != -1
    block = js[handler_idx : handler_idx + 1500]
    assert "_dzOptimisticUndoStack.pop()" in block
    assert "entry.undo()" in block


def test_handler_calls_preventDefault(js: str) -> None:
    """When the handler does pop an entry, it consumes the keypress
    so the browser's native undo doesn't also fire."""
    assert "e.preventDefault()" in js


def test_handler_swallows_undo_errors(js: str) -> None:
    """A stale undo (element gone from DOM, callback throws)
    shouldn't break subsequent presses. Wrap in try/catch."""
    handler_idx = js.find('document.addEventListener("keydown"')
    assert handler_idx != -1
    block = js[handler_idx : handler_idx + 1500]
    assert "try {" in block
    assert "catch" in block


# ---------------------------------------------------------------------------
# Push points — success path of each verb
# ---------------------------------------------------------------------------


def test_push_called_in_success_branch(js: str) -> None:
    """The push happens after `removePlaceholder()` + before
    `snapshot = null` — must be in the `if (ok)` block of
    onAfterRequest."""
    success_idx = js.find("if (ok) {")
    assert success_idx != -1
    block = js[success_idx : success_idx + 2500]
    assert "_pushOptimisticUndo" in block


def test_undo_captures_snapshot_by_closure(js: str) -> None:
    """`snapshot` is assigned to a local before the entry is created.
    Without this, `undo()` runs much later when `snapshot` has been
    cleared (or overwritten by a later mutation)."""
    success_idx = js.find("if (ok) {")
    block = js[success_idx : success_idx + 2500]
    assert "const undoSnapshot = snapshot" in block


# ---------------------------------------------------------------------------
# Per-verb undo behaviour
# ---------------------------------------------------------------------------


class TestUndoSemantics:
    def test_remove_and_replace_reinsert_via_snapshot(self, js: str) -> None:
        """Both remove and replace captured a snapshot at
        beforeRequest. The undo path uses it to put the original
        node back in the right place — same restore logic as the
        rollback path."""
        # Search for the verb-gated reinsert logic inside the undo lambda.
        success_idx = js.find("if (ok) {")
        block = js[success_idx : success_idx + 2500]
        assert 'verb === "remove" || verb === "replace"' in block
        assert "insertBefore" in block
        assert "appendChild" in block

    def test_undo_event_dispatched_for_all_verbs(self, js: str) -> None:
        """Even prepend/append (which can't be DOM-reversed by the
        framework) dispatch `dz:optimistic-undo` so the adopter can
        wire a server-side reversal endpoint."""
        success_idx = js.find("if (ok) {")
        block = js[success_idx : success_idx + 2500]
        assert '"dz:optimistic-undo"' in block

    def test_undo_event_carries_verb_and_snapshot(self, js: str) -> None:
        """Detail must include enough state for the adopter to issue
        a reversal — at minimum the verb + snapshot reference."""
        success_idx = js.find("if (ok) {")
        block = js[success_idx : success_idx + 2500]
        # In the same dispatch detail block.
        dispatch_idx = block.find('"dz:optimistic-undo"')
        dispatch_block = block[dispatch_idx : dispatch_idx + 400]
        assert "verb: verb" in dispatch_block
        assert "snapshot: undoSnapshot" in dispatch_block

    def test_undo_event_bubbles(self, js: str) -> None:
        """`bubbles: true` so a parent list container can delegate
        instead of wiring every row."""
        success_idx = js.find("if (ok) {")
        block = js[success_idx : success_idx + 2500]
        dispatch_idx = block.find('"dz:optimistic-undo"')
        dispatch_block = block[dispatch_idx : dispatch_idx + 400]
        assert "bubbles: true" in dispatch_block


# ---------------------------------------------------------------------------
# Bundle inclusion
# ---------------------------------------------------------------------------


def test_undo_present_in_dist_bundle() -> None:
    dist_js = (
        Path(__file__).resolve().parents[2] / "src/dazzle/page/runtime/static/dist/dazzle.min.js"
    )
    if not dist_js.is_file():
        pytest.skip("dist not built")
    text = dist_js.read_text()
    # Survives minification: the event name + window-level export.
    assert "dz:optimistic-undo" in text
    assert "dzOptimisticUndoStack" in text
