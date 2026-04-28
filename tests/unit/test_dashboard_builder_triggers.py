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


class TestRehydrateOnHtmxAfterSettle:
    """#875 / #919 — re-clicking the active workspace nav link triggers
    an HTMX morph that doesn't re-run init(). The component must listen
    for htmx:afterSettle (NOT afterSwap — see #919: the morph: extension
    fires afterSwap before idiomorph commits child-node textContent, so
    the <script id="dz-workspace-layout"> island still reads as the
    previous workspace's JSON) and re-hydrate cards/catalog/state from
    the data island when the swap target contains it.
    """

    def test_helper_extracted(self) -> None:
        source = _load()
        assert "_hydrateFromLayout()" in source, (
            "init/re-entry path expected to share a _hydrateFromLayout helper"
        )

    def test_init_calls_hydrate(self) -> None:
        source = _load()
        # init() should invoke the helper rather than inlining the JSON read.
        assert "this._hydrateFromLayout();" in source

    def test_listens_for_htmx_after_settle(self) -> None:
        source = _load()
        # #919: must be afterSettle, not afterSwap — the morph extension
        # fires afterSwap before child textContent is fully committed.
        assert '"htmx:afterSettle"' in source, (
            "component must listen for htmx:afterSettle (not afterSwap) to "
            "detect re-entry morphs after idiomorph fully commits the "
            "data-island textContent"
        )
        assert '"htmx:afterSwap"' not in source, (
            "must not listen for htmx:afterSwap — fires too early under "
            "the morph extension and reads stale layout JSON (#919)"
        )

    def test_filters_swap_to_layout_island(self) -> None:
        source = _load()
        # Only re-hydrate when the swap target actually contains our island
        # — otherwise every region card swap would trigger a full reload.
        assert '"#dz-workspace-layout"' in source

    def test_destroy_removes_listener(self) -> None:
        source = _load()
        # The htmx:afterSettle listener must be torn down on destroy() to
        # avoid leaking across navigations (#797 / #795 pattern).
        assert 'removeEventListener(\n          "htmx:afterSettle"' in source or (
            'removeEventListener("htmx:afterSettle"' in source
        )

    def test_resets_save_state_on_rehydrate(self) -> None:
        source = _load()
        # The "all five state labels stack vertically" symptom = saveState
        # somewhere other than 'clean' on re-entry. Reset to clean when
        # the data island is re-read.
        # Find the body of _hydrateFromLayout: substring between its
        # signature and the next bare-method definition.
        idx = source.find("_hydrateFromLayout() {")
        assert idx >= 0, "method definition missing"
        # Bound the search to the helper body (next 1500 chars cover it).
        body = source[idx : idx + 1500]
        assert 'this.saveState = "clean";' in body
