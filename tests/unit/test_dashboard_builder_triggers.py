"""Source-regression tests for dashboard-builder.js (#864, #936, #945, #948).

Pre-#948 these tests pinned the JSON-island + reactive-cards-array
shape (`cardHxTrigger`, `_hydrateFromLayout`, `foldCount`). After
#948 cards are server-rendered HTML and the DOM is the source of
truth for layout — the helpers above don't exist, but their job is
done by Jinja interpolation in `workspace/_content.html` and by
DOM-direct manipulation in dashboard-builder.js.

The tests below pin the post-#948 contract: dashboard-builder.js no
longer carries reactive cards/catalog/foldCount, the htmx:afterSettle
bridge survives as defense-in-depth for ephemeral state, and the
template emits the correct `data-card-*` attributes for the JS to
read.
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
DZ_ALPINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "runtime"
    / "static"
    / "js"
    / "dz-alpine.js"
)
TEMPLATE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle_ui"
    / "templates"
    / "workspace"
    / "_content.html"
)


def _load_js() -> str:
    return JS_PATH.read_text()


def _load_alpine() -> str:
    return DZ_ALPINE_PATH.read_text()


def _load_template() -> str:
    return TEMPLATE_PATH.read_text()


class TestNoReactiveCardsArray:
    """#948 — the cards reactive array is gone. Cards are server-rendered
    HTML; the DOM is the source of truth for layout."""

    def test_no_cards_field_in_alpine_state(self) -> None:
        source = _load_js()
        # The component's data() must NOT declare a reactive cards array.
        # Pre-#948 it had `cards: [],` near the top of the data block.
        assert "cards: []" not in source
        assert "cards: [" not in source

    def test_no_catalog_reactive_field(self) -> None:
        source = _load_js()
        # Catalog is now a `data-card-catalog` JSON blob on the picker;
        # the JS reads it on demand via `_catalog()`. The reactive
        # field is gone.
        assert "catalog: []" not in source

    def test_no_workspace_name_reactive_field(self) -> None:
        source = _load_js()
        # workspaceName comes from `data-workspace-name` on the root.
        assert 'workspaceName: ""' not in source

    def test_no_fold_count_reactive_field(self) -> None:
        source = _load_js()
        # foldCount is gone. The eager-vs-lazy split is decided at
        # template render time and baked into each card's hx-trigger.
        assert "foldCount: 0," not in source

    def test_no_hydrate_from_layout_method(self) -> None:
        source = _load_js()
        # _hydrateFromLayout existed to read the JSON island. The
        # method definition is gone — comments may still reference it
        # historically, so we only check that the method body is
        # absent.
        assert "_hydrateFromLayout() {" not in source
        assert "this._hydrateFromLayout()" not in source

    def test_no_card_hx_trigger_helper(self) -> None:
        source = _load_js()
        # The eager/lazy split is decided server-side now.
        assert "cardHxTrigger" not in source
        assert "isEagerCard" not in source

    def test_no_drag_transform_reactive_helper(self) -> None:
        source = _load_js()
        # Pre-#948 dragTransform(cardId) returned a CSS string consumed
        # by `:style="..."`. Post-#948 we apply transforms via
        # _applyDragTransform() directly to the dragged element.
        assert "dragTransform(cardId)" not in source


class TestDomDirectHelpers:
    """The DOM-direct helpers replace the array operations of the
    pre-#948 architecture."""

    def test_helper_for_all_cards(self) -> None:
        source = _load_js()
        assert "_allCards()" in source

    def test_helper_for_card_by_id(self) -> None:
        source = _load_js()
        assert "_cardById(cardId)" in source

    def test_workspace_name_read_from_dom_attr(self) -> None:
        source = _load_js()
        # `_workspaceName()` reads the data-workspace-name attribute.
        assert "data-workspace-name" in source

    def test_catalog_read_from_dom_attr(self) -> None:
        source = _load_js()
        # `_catalog()` parses data-card-catalog when the picker opens.
        assert "data-card-catalog" in source

    def test_apply_drag_transform_targets_dom_directly(self) -> None:
        """Drag preview now mutates `cardEl.style.cssText` rather than
        reactively binding via `:style`. Same CSS shape, imperative
        application."""
        source = _load_js()
        assert "_applyDragTransform" in source
        assert "cardEl.style.cssText" in source


class TestEventDelegation:
    """Card events (drag-start, click-remove, keydown) wire via
    delegation on the grid container so dynamically-added cards work
    without re-init."""

    def test_grid_pointerdown_delegation(self) -> None:
        source = _load_js()
        assert "_onGridPointerDown" in source
        assert 'data-test-id="dz-card-drag-handle"' in source

    def test_grid_click_delegation(self) -> None:
        source = _load_js()
        assert "_onGridClick" in source
        assert 'data-test-id="dz-card-remove"' in source

    def test_grid_keydown_delegation(self) -> None:
        source = _load_js()
        assert "_onGridKeydown" in source

    def test_destroy_removes_grid_listeners(self) -> None:
        source = _load_js()
        # destroy() must clean up the grid-container delegations
        # alongside the document/window ones.
        assert 'grid.removeEventListener("pointerdown"' in source
        assert 'grid.removeEventListener("click"' in source
        assert 'grid.removeEventListener("keydown"' in source


class TestServerRenderedTemplate:
    """The template emits each card as static HTML with `data-card-*`
    attributes the JS reads on demand."""

    def test_template_iterates_workspace_regions(self) -> None:
        source = _load_template()
        # Either form (whitespace-stripped or plain) is acceptable
        assert (
            "{% for r in workspace.regions %}" in source
            or "{%- for r in workspace.regions %}" in source
        )

    def test_template_emits_data_card_attributes(self) -> None:
        source = _load_template()
        assert "data-card-id=" in source
        assert "data-card-region=" in source
        assert "data-card-col-span=" in source

    def test_template_emits_workspace_name_on_root(self) -> None:
        source = _load_template()
        assert 'data-workspace-name="{{ workspace.name }}"' in source

    def test_template_drops_json_island(self) -> None:
        source = _load_template()
        # The cycle 936 JSON-island data script is gone.
        assert 'id="dz-workspace-layout"' not in source

    def test_template_drops_x_for(self) -> None:
        source = _load_template()
        # No reactive cards iteration on the workspace template.
        assert 'x-for="card in cards"' not in source

    def test_eager_lazy_trigger_split_server_rendered(self) -> None:
        """The hx-trigger choice is baked into each card at render time
        based on `loop.index0 < (fold_count or 0)`. Post-#948 there's
        no client-side cardHxTrigger helper."""
        source = _load_template()
        assert "loop.index0 < (fold_count or 0)" in source
        assert "_trigger = 'load' if _eager else 'intersect once'" in source

    def test_sse_triggers_appended_when_workspace_has_sse_url(self) -> None:
        source = _load_template()
        assert "{% if workspace.sse_url %}" in source
        assert "sse:entity.created" in source
        assert "sse:entity.updated" in source
        assert "sse:entity.deleted" in source


class TestSameUrlRehydrate:
    """#945 → #948 — the destroy + re-init pattern survives as
    defense-in-depth. Pre-#948 it was load-bearing for the cards
    array's watcher graph; post-#948 it covers ephemeral state
    (saveState, showPicker) and re-attaches the grid-container event
    delegation listeners."""

    def test_destroy_then_init_pattern_present(self) -> None:
        source = _load_alpine()
        idx = source.index("#936 → #945 → #948")
        block = source[idx : idx + 2500]
        assert "Alpine.destroyTree(root)" in block
        assert "Alpine.initTree(root)" in block

    def test_destroy_called_before_init(self) -> None:
        source = _load_alpine()
        idx = source.index("#936 → #945 → #948")
        block = source[idx : idx + 2500]
        destroy_idx = block.index("Alpine.destroyTree(root)")
        init_idx = block.index("Alpine.initTree(root)", destroy_idx)
        assert destroy_idx < init_idx

    def test_handler_finds_root_via_data_workspace_name(self) -> None:
        """The trigger is now the `data-workspace-name` attribute on
        the workspace root (the JSON island's `#dz-workspace-layout`
        was removed in #948)."""
        source = _load_alpine()
        idx = source.index("#936 → #945 → #948")
        block = source[idx : idx + 2500]
        assert "data-workspace-name" in block

    def test_handler_drops_dz_workspace_layout_selector_call(self) -> None:
        """The pre-#948 `target.querySelector('#dz-workspace-layout')`
        selector call is gone — the JSON island was removed. The
        comment block may still reference the historical id, so we
        check for the selector-call form rather than the bare id."""
        source = _load_alpine()
        idx = source.index("#936 → #945 → #948")
        block = source[idx : idx + 2500]
        assert 'querySelector("#dz-workspace-layout")' not in block

    def test_handler_guards_missing_root(self) -> None:
        source = _load_alpine()
        idx = source.index("#936 → #945 → #948")
        block = source[idx : idx + 2500]
        assert "if (!root" in block

    def test_handler_skips_unrelated_swap_targets(self) -> None:
        """The destroy + re-init only fires when the swap target
        actually contains (or is) the workspace root. Drawer-content
        swaps and other unrelated targets must no-op."""
        source = _load_alpine()
        idx = source.index("#936 → #945 → #948")
        block = source[idx : idx + 2500]
        # The contains-check guards against unrelated swaps.
        assert "target.contains(root)" in block or "root.contains(target)" in block


class TestGlobalInitTreeBridge:
    """#924 — the global `htmx:afterSettle` listener wires
    `Alpine.initTree(target)` so newly-arrived `[x-data]` roots get
    initialised. This survives the #948 migration unchanged."""

    def test_global_listener_exists(self) -> None:
        source = _load_alpine()
        assert 'document.body.addEventListener("htmx:afterSettle"' in source

    def test_calls_alpine_init_tree(self) -> None:
        source = _load_alpine()
        assert "window.Alpine.initTree(target)" in source

    def test_uses_after_settle_not_after_swap(self) -> None:
        source = _load_alpine()
        bridge_block_idx = source.index("HTMX morph-swap → Alpine.initTree bridge")
        bridge_block = source[bridge_block_idx : bridge_block_idx + 2000]
        assert "htmx:afterSettle" in bridge_block
        assert "htmx:afterSwap" not in bridge_block

    def test_guards_missing_alpine(self) -> None:
        source = _load_alpine()
        bridge_block_idx = source.index("HTMX morph-swap → Alpine.initTree bridge")
        bridge_block = source[bridge_block_idx : bridge_block_idx + 2000]
        assert "if (window.Alpine" in bridge_block


class TestEphemeralStatePreserved:
    """The Alpine reactive surface that survives #948 — the toolbar's
    save state, the picker visibility, the drag/resize mid-flight
    state, the keyboard move/resize markers."""

    def test_save_state_field_present(self) -> None:
        source = _load_js()
        assert 'saveState: "clean"' in source

    def test_show_picker_field_present(self) -> None:
        source = _load_js()
        assert "showPicker: false" in source

    def test_drag_field_initialises_null(self) -> None:
        source = _load_js()
        assert "drag: null" in source

    def test_resize_field_initialises_null(self) -> None:
        source = _load_js()
        assert "resize: null" in source
