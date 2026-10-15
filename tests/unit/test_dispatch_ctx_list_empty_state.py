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

from typing import Any

import pytest

from tests.unit.helpers.list_surface import contact_table, list_ctx, render_list

_FRAMEWORK_DEFAULT = "Items will appear here when they are added."


def test_dispatch_ctx_threads_typed_empty_variants() -> None:
    """All four empty-state fields plus `empty_kind` reach the adapter."""
    ctx = list_ctx(
        contact_table(
            empty_message="Generic",
            empty_collection="Add your first contact",
            empty_filtered="No matches",
            empty_forbidden="Not allowed",
            empty_kind="filtered",
        )
    )
    assert {k: ctx[k] for k in ("empty_message", "empty_collection", "empty_filtered")} == {
        "empty_message": "Generic",
        "empty_collection": "Add your first contact",
        "empty_filtered": "No matches",
    }
    assert (ctx["empty_forbidden"], ctx["empty_kind"]) == ("Not allowed", "filtered")


def test_dispatch_ctx_defaults_empty_kind_to_collection() -> None:
    assert list_ctx(contact_table())["empty_kind"] == "collection"


@pytest.mark.parametrize(
    ("table", "ctx_overrides", "present", "absent"),
    [
        pytest.param(
            {"empty_collection": "Add your first contact.", "empty_kind": "collection"},
            {},
            ["Add your first contact."],
            [_FRAMEWORK_DEFAULT],
            id="collection_copy_wins",
        ),
        pytest.param(
            {"empty_filtered": "No contacts match your search.", "empty_kind": "filtered"},
            {},
            ["No matches", "No contacts match your search."],
            [],
            id="filtered_uses_no_matches_title",
        ),
        pytest.param(
            {"empty_forbidden": "You lack permission.", "empty_kind": "forbidden"},
            {},
            ["Not available", "You lack permission."],
            [],
            id="forbidden_uses_not_available_title",
        ),
        pytest.param(
            {"empty_message": "No contacts yet.", "empty_collection": ""},
            {},
            ["No contacts yet."],
            [],
            id="blank_typed_variant_falls_back_to_empty_message",
        ),
        pytest.param(
            {"empty_message": ""},
            {},
            ["No items found."],
            [_FRAMEWORK_DEFAULT],
            id="blank_everything_uses_dispatch_default",
        ),
        pytest.param(
            {},
            {"empty_message": "", "empty_collection": ""},
            [_FRAMEWORK_DEFAULT],
            [],
            id="adapter_framework_default_when_ctx_has_no_copy",
        ),
        pytest.param(
            {"empty_collection": "Unknown kind still shows collection copy."},
            {"empty_kind": "not_a_kind"},
            ["Unknown kind still shows collection copy."],
            ["No matches", "Not available"],
            id="unknown_kind_treated_as_collection",
        ),
    ],
)
def test_empty_list_renders_typed_copy(
    table: dict[str, Any], ctx_overrides: dict[str, Any], present: list[str], absent: list[str]
) -> None:
    ctx = list_ctx(contact_table(**table))
    ctx.update(ctx_overrides)
    html = render_list(ctx)
    for fragment in present:
        assert fragment in html
    for fragment in absent:
        assert fragment not in html
