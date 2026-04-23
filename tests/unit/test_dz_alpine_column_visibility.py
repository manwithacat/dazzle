"""
Structural ratchets for dzTable column-visibility logic (#853).

The bug: hiddenColumns is loaded from localStorage on init and applied
by setting `style.display="none"` on `[data-dz-col]` cells. If the
column set changed between page loads (schema change, persona swap,
table id reused), stale entries silently hid visible columns —
manifest as "headers render but cells are empty" because the cells
exist with `display:none`.

This file pins the structural fix without a JS test runner: the prune
helper must exist + be called from init, and a reset escape hatch
must be present.
"""

from __future__ import annotations

from pathlib import Path

JS_FILE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "runtime"
    / "static"
    / "js"
    / "dz-alpine.js"
)


class TestColumnVisibilityPrune:
    def test_prune_helper_exists(self) -> None:
        """_pruneStaleHiddenColumns must be defined on the dzTable component."""
        content = JS_FILE.read_text()
        assert "_pruneStaleHiddenColumns()" in content, (
            "dzTable._pruneStaleHiddenColumns helper is missing — #853 regression. "
            "Without it, stale localStorage hiddenColumns entries can hide "
            "current columns invisibly."
        )

    def test_prune_called_in_init(self) -> None:
        """The init() lifecycle hook must call the prune helper."""
        content = JS_FILE.read_text()
        # Walk the init() body. The prune call must precede applyColumnVisibility
        # so the cleanup happens before the first style write.
        init_idx = content.find("init() {")
        apply_idx = content.find("this.applyColumnVisibility()", init_idx)
        prune_idx = content.find("this._pruneStaleHiddenColumns()", init_idx)
        assert init_idx >= 0
        assert prune_idx >= 0, "init() no longer calls _pruneStaleHiddenColumns — #853 regression."
        assert prune_idx < apply_idx, (
            "_pruneStaleHiddenColumns must run BEFORE applyColumnVisibility "
            "in init() so we don't hide cells we're about to clean."
        )

    def test_prune_persists_cleaned_list(self) -> None:
        """Pruned localStorage must be written back so the cleanup is one-shot."""
        content = JS_FILE.read_text()
        # Find the helper *definition* (the second occurrence — the first
        # is the call inside init()).
        first_idx = content.find("_pruneStaleHiddenColumns()")
        def_idx = content.find("_pruneStaleHiddenColumns()", first_idx + 1)
        assert def_idx >= 0, "Could not locate _pruneStaleHiddenColumns definition"
        window = content[def_idx : def_idx + 1500]
        assert "localStorage.setItem" in window, (
            "Pruned hiddenColumns list isn't persisted — same prune work would "
            "repeat on every page load."
        )

    def test_reset_escape_hatch_exists(self) -> None:
        """Users need a way to clear all hidden columns when stuck."""
        content = JS_FILE.read_text()
        assert "resetColumnVisibility()" in content, (
            "dzTable.resetColumnVisibility helper is missing — #853 follow-on. "
            "Wire to a 'Show all columns' menu entry so users have an escape "
            "hatch from accidentally hiding everything."
        )
        # Must also clear localStorage, not just the in-memory list.
        reset_idx = content.find("resetColumnVisibility()")
        window = content[reset_idx : reset_idx + 800]
        assert "localStorage.removeItem" in window, (
            "resetColumnVisibility must clear localStorage too, otherwise "
            "the next page load reverts to the hidden state."
        )
