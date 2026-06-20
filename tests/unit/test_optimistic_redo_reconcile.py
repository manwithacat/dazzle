"""Tests for #959 cycle 4 — redo stack + reconciliation hook.

Cycle 3 shipped undo with Cmd+Z. Cycle 4 closes the issue with:

- Redo stack: Shift+Cmd+Z replays a popped undo entry.
- New mutation push clears the redo stack (standard editor
  convention — divergent history).
- `dz:optimistic-reconcile` event fires on every successful
  optimistic mutation so adopters can merge state between
  placeholder and server response (focus, scroll, custom attrs).

Browser-level behaviour (key dispatch, focus, htmx swap timing)
isn't testable without a browser harness — these tests pin the
contract via string checks on the bundled JS.
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
# Redo stack data structure
# ---------------------------------------------------------------------------


def test_redo_stack_declared(js: str) -> None:
    """The redo stack is module-level just like the undo stack."""
    assert "_dzOptimisticRedoStack = []" in js


def test_redo_stack_exposed_as_window_global(js: str) -> None:
    """Same exposure pattern as the undo stack — adopters can show
    "X actions can be redone" indicators."""
    assert "window.dzOptimisticRedoStack" in js


def test_new_mutation_clears_redo_stack(js: str) -> None:
    """Standard editor convention: when the user takes a new action,
    the redo branch is no longer reachable. `_pushOptimisticUndo`
    clears the redo stack on every push."""
    push_idx = js.find("function _pushOptimisticUndo")
    assert push_idx != -1
    block = js[push_idx : push_idx + 600]
    assert "_dzOptimisticRedoStack.length = 0" in block


# ---------------------------------------------------------------------------
# Keyboard handler — redo branch
# ---------------------------------------------------------------------------


def test_handler_recognises_shift_modifier(js: str) -> None:
    """Cycle-3 specifically rejected `e.shiftKey` to leave room for
    redo. Cycle 4 reverses that: shift+modifier+z is now the redo
    chord, so the early-return on shift is gone."""
    handler_idx = js.find('document.addEventListener("keydown"')
    assert handler_idx != -1
    block = js[handler_idx : handler_idx + 2500]
    # Must NOT bail out on shiftKey early
    assert "e.shiftKey" in block
    assert "if (e.shiftKey) {" in block


def test_redo_pops_from_redo_pushes_to_undo(js: str) -> None:
    """Redo is the inverse of undo. After running, the entry goes
    back onto the undo stack so the user can undo their redo."""
    handler_idx = js.find('document.addEventListener("keydown"')
    assert handler_idx != -1
    block = js[handler_idx : handler_idx + 2500]
    redo_idx = block.find("if (e.shiftKey) {")
    assert redo_idx != -1
    redo_branch = block[redo_idx : redo_idx + 800]
    assert "_dzOptimisticRedoStack.pop()" in redo_branch
    assert "_dzOptimisticUndoStack.push(entry)" in redo_branch


def test_undo_path_pushes_to_redo(js: str) -> None:
    """Inverse of the above — undo pops from undo, runs, pushes to
    redo. Without this, Shift+Cmd+Z would always find an empty
    redo stack."""
    handler_idx = js.find('document.addEventListener("keydown"')
    block = js[handler_idx : handler_idx + 2500]
    # The undo branch is at the end of the handler.
    undo_idx = block.rfind("_dzOptimisticUndoStack.pop()")
    assert undo_idx != -1
    undo_branch = block[undo_idx : undo_idx + 400]
    assert "_dzOptimisticRedoStack.push(entry)" in undo_branch


def test_redo_swallows_errors(js: str) -> None:
    """Stale redo (entry's element gone from DOM) shouldn't break
    later presses. Same try/catch pattern as undo."""
    handler_idx = js.find('document.addEventListener("keydown"')
    block = js[handler_idx : handler_idx + 2500]
    # Both branches need try/catch.
    assert block.count("try {") >= 2
    assert block.count("catch") >= 2


# ---------------------------------------------------------------------------
# Per-entry redo() function
# ---------------------------------------------------------------------------


def test_entry_carries_redo_function(js: str) -> None:
    """Each undo entry must include a `redo()` so the keyboard
    handler can replay the original mutation."""
    success_idx = js.find("if (ok) {")
    assert success_idx != -1
    block = js[success_idx : success_idx + 4000]
    assert "redo: ()" in block


def test_redo_for_remove_replace_drops_restored_node(js: str) -> None:
    """For DOM-reversible verbs, redo undoes the undo: removes the
    node that was just re-inserted."""
    success_idx = js.find("if (ok) {")
    block = js[success_idx : success_idx + 4000]
    redo_idx = block.find("redo: ()")
    redo_block = block[redo_idx : redo_idx + 800]
    assert 'verb === "remove" || verb === "replace"' in redo_block
    assert "removeChild" in redo_block


def test_redo_dispatches_event(js: str) -> None:
    """Redo always dispatches `dz:optimistic-redo` so adopters can
    re-fire the server-side action (e.g. re-POST to delete after
    they undid it)."""
    success_idx = js.find("if (ok) {")
    block = js[success_idx : success_idx + 4000]
    assert '"dz:optimistic-redo"' in block


def test_redo_event_carries_verb_and_snapshot(js: str) -> None:
    """Same detail shape as undo — adopter handlers can branch on
    verb without having to rebuild context."""
    success_idx = js.find("if (ok) {")
    block = js[success_idx : success_idx + 4000]
    redo_dispatch_idx = block.find('"dz:optimistic-redo"')
    redo_block = block[redo_dispatch_idx : redo_dispatch_idx + 400]
    assert "verb: verb" in redo_block
    assert "snapshot: undoSnapshot" in redo_block
    assert "bubbles: true" in redo_block


# ---------------------------------------------------------------------------
# Reconciliation hook
# ---------------------------------------------------------------------------


def test_reconcile_event_fires_on_success(js: str) -> None:
    """Every successful optimistic mutation must dispatch
    `dz:optimistic-reconcile` so adopters can merge state between
    placeholder and server response (focus, scroll, custom attrs)."""
    success_idx = js.find("if (ok) {")
    assert success_idx != -1
    block = js[success_idx : success_idx + 4500]
    assert '"dz:optimistic-reconcile"' in block


def test_reconcile_event_carries_verb_and_xhr(js: str) -> None:
    """The xhr reference lets adopters inspect the response body
    (e.g. extract data attributes from the inserted markup) before
    deciding what to merge."""
    success_idx = js.find("if (ok) {")
    block = js[success_idx : success_idx + 4500]
    reconcile_idx = block.find('"dz:optimistic-reconcile"')
    reconcile_block = block[reconcile_idx : reconcile_idx + 400]
    assert "verb: verb" in reconcile_block
    assert "xhr: xhr" in reconcile_block
    assert "bubbles: true" in reconcile_block


def test_reconcile_event_does_not_fire_on_error(js: str) -> None:
    """Error path runs `restore()` instead of dispatching
    reconcile — adopter handlers shouldn't have to filter on success
    themselves."""
    # The reconcile dispatch is INSIDE `if (ok) {` not after it.
    success_idx = js.find("if (ok) {")
    error_idx = js.find('restore("response-error")', success_idx)
    reconcile_idx = js.find('"dz:optimistic-reconcile"', success_idx)
    assert reconcile_idx > 0
    assert reconcile_idx < error_idx, "reconcile must be inside the success branch"


# ---------------------------------------------------------------------------
# Bundle inclusion
# ---------------------------------------------------------------------------


def test_redo_present_in_dist_bundle() -> None:
    dist_js = (
        Path(__file__).resolve().parents[2] / "src/dazzle/page/runtime/static/dist/dazzle.min.js"
    )
    if not dist_js.is_file():
        pytest.skip("dist not built")
    text = dist_js.read_text()
    assert "dz:optimistic-redo" in text
    assert "dz:optimistic-reconcile" in text
    assert "dzOptimisticRedoStack" in text
