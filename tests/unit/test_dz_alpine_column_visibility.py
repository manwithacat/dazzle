"""
Structural ratchets for column-visibility stale-key pruning (#853).

The bug: the hidden-column set is loaded from localStorage on init and
applied by setting `style.display` on `[data-dz-col]` cells. If the
column set changed between page loads (schema change, persona swap,
table id reused), stale entries silently hid current columns —
manifest as "headers render but cells are empty".

The fix originally lived in dzTable (deleted in convergence C3); it now
lives in the HM grid extension `dz-grid-cols.js`, which Dazzle consumes
from `packages/hatchi-maxchi/controllers/`. This file pins the structure
without a JS test runner: prune must exist, run at init BEFORE the first
style write, skip not-yet-rendered tables, and the reset escape hatch
must clear storage. Behavioural coverage lives in the HM gallery
two-engine tests (`packages/hatchi-maxchi/tests/test_behaviour.py`).
"""

from __future__ import annotations

from pathlib import Path

JS_FILE = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "hatchi-maxchi"
    / "controllers"
    / "dz-grid-cols.js"
)


class TestColumnVisibilityPrune:
    def test_prune_helper_exists(self) -> None:
        """The prune helper must be defined in the extension."""
        content = JS_FILE.read_text()
        assert "function prune(" in content, (
            "dz-grid-cols.js prune() is missing — #853 regression. Without it, "
            "stale localStorage hidden-column entries can hide current columns "
            "invisibly."
        )

    def test_prune_called_in_init(self) -> None:
        """Init must prune BEFORE the first style write (apply)."""
        content = JS_FILE.read_text()
        init_idx = content.find("// Init:")
        assert init_idx >= 0, "the init block marker comment is gone"
        prune_idx = content.find("prune(grids[g])", init_idx)
        apply_idx = content.find("apply(grids[g])", init_idx)
        assert prune_idx >= 0, "init no longer calls prune() — #853 regression"
        assert apply_idx >= 0, "init must call apply()"
        assert prune_idx < apply_idx, (
            "prune must run BEFORE apply so we don't hide cells we're about to clean"
        )

    def test_prune_skips_unrendered_tables(self) -> None:
        """An empty / not-yet-hydrated table must NOT wipe the preference —
        prune only judges staleness against a rendered column set."""
        content = JS_FILE.read_text()
        assert "if (!cells.length) return;" in content

    def test_prune_persists_cleaned_list(self) -> None:
        """The cleaned set is written back (one-shot cleanup), and only when
        something was actually dropped."""
        content = JS_FILE.read_text()
        assert "if (cleaned.length !== hidden.length) writeHidden(root, cleaned);" in content

    def test_reset_escape_hatch_exists(self) -> None:
        """Users need a way out after hiding everything: the menu's reset
        seam must exist and must clear STORAGE, not just re-show cells
        (otherwise the next page load reverts to the hidden state)."""
        content = JS_FILE.read_text()
        assert "data-dz-grid-cols-reset" in content, (
            "the reset seam is missing — #853 follow-on escape hatch"
        )
        # last occurrence = the delegated click handler (the first is the
        # contract comment in the file header)
        reset_idx = content.rfind("data-dz-grid-cols-reset")
        window = content[reset_idx : reset_idx + 800]
        assert "localStorage.removeItem" in window
