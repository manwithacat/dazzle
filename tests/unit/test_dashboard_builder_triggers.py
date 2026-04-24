"""Source-regression tests for dashboard-builder.js trigger helpers (#864).

The `cardHxTrigger` / `isEagerCard` helpers are Alpine methods — proper
JS unit tests would require a bundler + jsdom. These source-grep tests
pin the contract:

1. `cardHxTrigger` exists and accepts `(card, sseEnabled)`.
2. Above-fold cards get `"load"` only (no intersect trigger).
3. Below-fold cards get `"intersect once"` only (no load trigger).
4. SSE triggers are appended when `sseEnabled` is true.

Full behaviour is verified by the dashboard Playwright gates in
``tests/quality_gates/test_dashboard_gates.py``; these source tests
catch unintended regressions between Python releases without booting
a browser.
"""

from __future__ import annotations

from pathlib import Path

JS_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "runtime"
    / "static"
    / "js"
    / "dashboard-builder.js"
)


def _load() -> str:
    return JS_PATH.read_text()


class TestCardHxTrigger:
    """v0.61.1 (#864) — above-fold/below-fold trigger split."""

    def test_helper_exists(self) -> None:
        source = _load()
        assert "cardHxTrigger(card, sseEnabled)" in source
        assert "isEagerCard(card)" in source

    def test_eager_branch_uses_load_only(self) -> None:
        source = _load()
        # The helper returns "load" for eager and "intersect once" for lazy.
        assert 'this.isEagerCard(card) ? "load" : "intersect once"' in source

    def test_sse_triggers_appended(self) -> None:
        source = _load()
        assert "sse:entity.created" in source
        assert "sse:entity.updated" in source
        assert "sse:entity.deleted" in source

    def test_fold_count_default_preserves_legacy(self) -> None:
        """isEagerCard falls back to True when foldCount is 0 so legacy
        workspaces (before #864) behave the same as before."""
        source = _load()
        # Matches the guard: `if (!this.foldCount) return true;`
        assert "if (!this.foldCount) return true;" in source


class TestFoldCountHydration:
    def test_state_field_declared(self) -> None:
        source = _load()
        assert "foldCount: 0," in source

    def test_reads_fold_count_from_island(self) -> None:
        source = _load()
        # The init reads fold_count from the layout data island.
        assert "data.fold_count" in source
