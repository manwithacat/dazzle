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
    """#875 / #919 / #936 — re-clicking a workspace nav link triggers an
    HTMX morph. As of #936, the per-component htmx:afterSettle listener
    has been removed: it captured `this` at init time and went stale
    whenever idiomorph re-created the workspace root, leaving cards
    permanently empty after a same-URL sidebar re-click. The global
    handler in dz-alpine.js now drives re-hydration through
    `Alpine.$data(root)` so it always finds the live instance.
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

    def test_no_per_component_after_settle_listener(self) -> None:
        """#936: the per-component listener was removed. Re-hydration is
        now driven by the global handler in dz-alpine.js, which looks up
        the live Alpine instance fresh on every settle."""
        source = _load()
        assert "htmx:afterSettle" not in source, (
            "dashboard-builder must NOT register its own afterSettle "
            "listener — captured `this` went stale on same-URL morph "
            "(#936). The global handler in dz-alpine.js owns this."
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


DZ_ALPINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "runtime"
    / "static"
    / "js"
    / "dz-alpine.js"
)


class TestGlobalInitTreeBridge:
    """#924: the per-component htmx:afterSettle listener (#919) only re-
    hydrates when the SAME dzDashboardBuilder Alpine instance survives the
    morph swap. When the user navigates between *different* workspaces via
    the sidebar, idiomorph replaces the `<div x-data="dzDashboardBuilder()">`
    element entirely and Alpine never initializes the new one — so the
    new x-for renders nothing and the JSON layout island shows as raw
    text. The fix is a global htmx:afterSettle listener in dz-alpine.js
    that calls Alpine.initTree(target) on every swap so any new x-data
    elements get initialized."""

    def _load_alpine(self) -> str:
        return DZ_ALPINE_PATH.read_text()

    def test_global_listener_exists(self) -> None:
        source = self._load_alpine()
        assert 'document.body.addEventListener("htmx:afterSettle"' in source

    def test_calls_alpine_init_tree(self) -> None:
        source = self._load_alpine()
        assert "window.Alpine.initTree(target)" in source

    def test_listener_is_outside_alpine_init_block(self) -> None:
        """The listener must be a module-level registration, not nested
        inside the alpine:init handler — alpine:init only fires once,
        but this listener must fire for every htmx swap."""
        source = self._load_alpine()
        listener_idx = source.index('document.body.addEventListener("htmx:afterSettle"')
        last_alpine_init_close = source.rindex("  }));\n});\n")
        assert listener_idx > last_alpine_init_close, (
            "the global htmx:afterSettle listener must live AFTER the "
            "alpine:init block closes — otherwise it never registers"
        )

    def test_uses_after_settle_not_after_swap(self) -> None:
        """Same #919 reasoning — afterSwap fires before idiomorph commits
        child textContent under the morph extension."""
        source = self._load_alpine()
        # The bridge listener uses afterSettle. (Other afterSwap mentions
        # may exist elsewhere, so we only assert the bridge uses settle.)
        bridge_block_idx = source.index("HTMX morph-swap → Alpine.initTree bridge")
        bridge_block = source[bridge_block_idx : bridge_block_idx + 2000]
        assert "htmx:afterSettle" in bridge_block
        assert "htmx:afterSwap" not in bridge_block

    def test_guards_missing_alpine(self) -> None:
        """If Alpine isn't loaded yet (race during boot), the listener
        must no-op rather than throw."""
        source = self._load_alpine()
        bridge_block_idx = source.index("HTMX morph-swap → Alpine.initTree bridge")
        bridge_block = source[bridge_block_idx : bridge_block_idx + 2000]
        assert "if (window.Alpine" in bridge_block


class TestSameUrlRehydrate:
    """#936 — sidebar re-click on the active workspace link must restore
    cards. The global afterSettle handler in dz-alpine.js looks up the
    live dzDashboardBuilder Alpine instance via `Alpine.$data(root)` and
    calls `_hydrateFromLayout()` on it. The previous per-component
    listener captured `this` at init time and pointed at a dead Alpine
    proxy after same-URL morph, so cards collapsed to empty even though
    the JSON island had fresh data."""

    def _load_alpine(self) -> str:
        return DZ_ALPINE_PATH.read_text()

    def test_handler_filters_to_workspace_layout_island(self) -> None:
        source = self._load_alpine()
        # The handler skips when the swap target has no workspace layout
        # island — a region card swap shouldn't re-hydrate the dashboard.
        assert '"#dz-workspace-layout"' in source

    def test_handler_uses_alpine_data_lookup(self) -> None:
        """`Alpine.$data(root)` always returns the live proxy, even after
        idiomorph re-creates the element. Capturing `this` at init time
        (the previous approach) went stale on same-URL morph."""
        source = self._load_alpine()
        assert "Alpine.$data(root)" in source

    def test_handler_calls_hydrate_on_live_instance(self) -> None:
        source = self._load_alpine()
        assert "_hydrateFromLayout()" in source, (
            "global handler must invoke _hydrateFromLayout() on the "
            "live Alpine instance to populate cards after same-URL morph"
        )

    def test_handler_finds_dashboard_root_via_x_data_attr(self) -> None:
        """Selector targets the workspace's x-data root, not any random
        Alpine root in the swapped subtree."""
        source = self._load_alpine()
        assert '[x-data*="dzDashboardBuilder"]' in source

    def test_handler_guards_missing_alpine_data(self) -> None:
        """During boot (Alpine not yet loaded) or when no dashboard root
        is present (e.g. non-workspace pages), the handler must no-op
        rather than throw."""
        source = self._load_alpine()
        # Bound the search to the post-#936 block we just added.
        idx = source.index("#936:")
        block = source[idx : idx + 2500]
        assert "if (!root" in block
        assert "Alpine.$data" in block
