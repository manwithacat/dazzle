"""Issue #1029 phase 4 (v0.66.136): regression tests for the LIST
adapter's typed empty-state messages (#807).

Pre-fix, every empty list rendered the generic "No items yet — Items
will appear here when they are added." regardless of whether the
DSL declared `empty_collection`, `empty_filtered`, or `empty_forbidden`
copy. Fix: thread all four typed variants through the dispatch ctx;
adapter picks based on `empty_kind` ("collection" | "filtered" |
"forbidden") with priority kind-specific → generic → framework
default."""

from __future__ import annotations

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import (
    FragmentSurfaceAdapter,
    _pick_empty_state,
)
from dazzle.render.context import ColumnContext, TableContext
from dazzle.render.fragment import FragmentRenderer


class _Surface:
    name = "contact_list"
    title = "Contacts"
    mode = SurfaceMode.LIST
    entity_ref = "Contact"


class _RC:
    def __init__(self, table: TableContext) -> None:
        self.table = table
        self.form = None
        self.detail = None


def _table(**overrides) -> TableContext:
    base: dict = {
        "entity_name": "Contact",
        "title": "Contacts",
        "columns": [ColumnContext(key="name", label="Name")],
        "api_endpoint": "/api/contacts",
        "rows": [],
        "total": 0,
        "empty_message": "No contacts yet",
    }
    base.update(overrides)
    return TableContext(**base)


def _render_list(ctx: dict) -> str:
    adapter = FragmentSurfaceAdapter()
    return FragmentRenderer().render(adapter._build_list(_Surface(), ctx))


# ── Dispatch ctx threading ──


def test_dispatch_ctx_threads_typed_empty_variants() -> None:
    """All four empty-state fields plus `empty_kind` are exposed
    to the adapter."""
    table = _table(
        empty_message="Generic",
        empty_collection="Add your first contact",
        empty_filtered="No matches",
        empty_forbidden="Not allowed",
        empty_kind="filtered",
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    assert ctx["empty_message"] == "Generic"
    assert ctx["empty_collection"] == "Add your first contact"
    assert ctx["empty_filtered"] == "No matches"
    assert ctx["empty_forbidden"] == "Not allowed"
    assert ctx["empty_kind"] == "filtered"


def test_dispatch_ctx_defaults_empty_kind_to_collection() -> None:
    """Unset `empty_kind` defaults to `"collection"` per the
    framework convention."""
    ctx = _build_dispatch_ctx(_RC(_table()), object())
    assert ctx["empty_kind"] == "collection"


# ── _pick_empty_state helper ──


def test_pick_empty_state_collection_variant_preferred() -> None:
    """`empty_kind="collection"` + non-empty `empty_collection` →
    that string used in the description; title is "No items yet"."""
    ctx = {
        "empty_kind": "collection",
        "empty_collection": "Add your first task",
        "empty_message": "Generic",
    }
    title, description = _pick_empty_state(ctx)
    assert title == "No items yet"
    assert description == "Add your first task"


def test_pick_empty_state_filtered_variant_uses_no_matches_title() -> None:
    """`empty_kind="filtered"` → title "No matches", description
    from `empty_filtered`."""
    ctx = {
        "empty_kind": "filtered",
        "empty_filtered": "Try a different search term",
        "empty_message": "Generic",
    }
    title, description = _pick_empty_state(ctx)
    assert title == "No matches"
    assert description == "Try a different search term"


def test_pick_empty_state_forbidden_variant_uses_not_available_title() -> None:
    """`empty_kind="forbidden"` → title "Not available", description
    from `empty_forbidden`."""
    ctx = {
        "empty_kind": "forbidden",
        "empty_forbidden": "You don't have permission to see these records.",
        "empty_message": "Generic",
    }
    title, description = _pick_empty_state(ctx)
    assert title == "Not available"
    assert "permission" in description


def test_pick_empty_state_falls_back_to_empty_message_when_typed_unset() -> None:
    """Typed variant blank → fall through to the generic
    `empty_message` field."""
    ctx = {
        "empty_kind": "collection",
        "empty_collection": "",
        "empty_message": "Custom DSL message",
    }
    title, description = _pick_empty_state(ctx)
    assert description == "Custom DSL message"


def test_pick_empty_state_falls_back_to_framework_default() -> None:
    """All variants and the generic message blank → framework default."""
    ctx = {"empty_kind": "collection"}
    title, description = _pick_empty_state(ctx)
    assert description == "Items will appear here when they are added."


def test_pick_empty_state_unknown_kind_treated_as_collection() -> None:
    """Defensive: unknown `empty_kind` value (e.g. typo, future
    extension) treated as collection — same default title."""
    ctx = {"empty_kind": "loading", "empty_collection": "still loading…"}
    title, description = _pick_empty_state(ctx)
    assert title == "No items yet"


# ── End-to-end render ──


def test_list_renders_empty_collection_when_no_items_and_collection_set() -> None:
    """The custom DSL empty copy from `empty:` block reaches the
    rendered EmptyState description."""
    table = _table(
        empty_collection="No contacts yet. Add a contact to get started.",
        empty_kind="collection",
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "No contacts yet. Add a contact to get started." in html
    assert "Items will appear here when they are added." not in html


def test_list_renders_empty_filtered_with_no_matches_title() -> None:
    """`empty_kind="filtered"` produces a "No matches" heading + the
    custom filtered copy."""
    table = _table(
        empty_filtered="No contacts match your search.",
        empty_kind="filtered",
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "No matches" in html
    assert "No contacts match your search." in html


def test_list_renders_empty_message_when_no_typed_variant_set() -> None:
    """Surface only declared the generic `empty:` form (no typed
    variants) — adapter falls back to `empty_message`."""
    table = _table(empty_message="No contacts yet.")
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "No contacts yet." in html


def test_list_renders_dispatch_default_empty_message() -> None:
    """Total fallback: blank empty_message + no typed variants →
    dispatch ctx default `"No items found."` reaches the adapter
    (the adapter's own framework default is shadowed by the dispatch
    default — fine, both are sensible empty copy)."""
    table = TableContext(
        entity_name="X",
        title="X",
        columns=[ColumnContext(key="name", label="Name")],
        api_endpoint="/api/x",
        rows=[],
        total=0,
        empty_message="",
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "No items found." in html
