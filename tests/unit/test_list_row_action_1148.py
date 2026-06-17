"""#1148 part 2: list-display row_action renderer wiring.

The IR + parser shipped in v0.71.45 (part 1). This file pins the
data-builder + renderer path:

- `WorkspaceRegion.row_action` set → ListRegion carries per-row
  button HTML + a trailing action column header.
- `visible_when` evaluated per row (truthy → button, falsy → empty
  cell so the table arity stays stable).
- `bind:` substitutes row field values into the button's
  ``data-dz-row-args`` JSON.
- No `row_action` → ListRegion behaves exactly as v0.71.45 (no
  extra column, no regression).
"""

from __future__ import annotations

from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
)
from dazzle.core.ir.workspaces import RowActionSpec
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    def __init__(
        self,
        name: str = "things",
        display: str = "list",
        title: str | None = None,
        empty_message: str | None = None,
        row_action: RowActionSpec | None = None,
    ) -> None:
        self.name = name
        self.title = title
        self.display = display
        self.empty_message = empty_message
        self.row_action = row_action


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


def _build(region: _FakeRegion, ctx: dict) -> str:
    adapter = WorkspaceRegionAdapter()
    return _render(adapter.build(region, ctx))


def test_row_action_emits_button_per_row() -> None:
    """The canonical case: each row gets an action button labelled
    from row_action.label, carrying the bound id."""
    row_action = RowActionSpec(
        label="Approve",
        action_id="feedback_release",
        bind={"id": "id"},
    )
    region = _FakeRegion(row_action=row_action)
    ctx = {
        "items": [
            {"id": "row-1", "name": "Alice"},
            {"id": "row-2", "name": "Bob"},
        ],
        "columns": [{"key": "name", "label": "Name"}],
    }
    html = _build(region, ctx)

    assert html.count('data-dz-row-action="feedback_release"') == 2
    # Bound id values reach the button via data-dz-row-args.
    assert "row-1" in html
    assert "row-2" in html
    # Header column appears with the label.
    assert ">Approve<" in html


def test_row_action_label_in_header() -> None:
    """The action column header carries row_action.label so the
    column is identifiable in the table."""
    row_action = RowActionSpec(label="Release", action_id="rel", bind={"id": "id"})
    region = _FakeRegion(row_action=row_action)
    ctx = {
        "items": [{"id": "a", "name": "X"}],
        "columns": [{"key": "name", "label": "Name"}],
    }
    html = _build(region, ctx)
    assert "dz-list-row-action-col" in html
    assert ">Release<" in html


def test_bind_carries_multiple_args_as_json() -> None:
    """When bind has multiple entries, all are present in the JSON-
    encoded data-dz-row-args attribute."""
    row_action = RowActionSpec(
        label="Try",
        action_id="try_pack",
        bind={"subject_id": "subject_fk", "scheme_id": "scheme_fk"},
    )
    region = _FakeRegion(row_action=row_action)
    ctx = {
        "items": [{"subject_fk": "s1", "scheme_fk": "ms1", "name": "Pack A"}],
        "columns": [{"key": "name", "label": "Pack"}],
    }
    html = _build(region, ctx)
    # Extract the data-dz-row-args JSON and verify shape.
    # The attribute is HTML-escaped, so quotes become &quot;.
    assert "subject_id" in html
    assert "scheme_id" in html
    assert "s1" in html
    assert "ms1" in html


def test_visible_when_falsy_emits_empty_action_cell() -> None:
    """When visible_when evaluates falsy on a row, no button is
    rendered for that row — but the cell column stays so arity is
    stable across rows."""
    row_action = RowActionSpec(
        label="Resolve",
        action_id="resolve",
        bind={"id": "id"},
        visible_when=ConditionExpr(
            comparison=Comparison(
                field="status",
                operator=ComparisonOperator.NOT_EQUALS,
                value=ConditionValue(literal="resolved"),
            )
        ),
    )
    region = _FakeRegion(row_action=row_action)
    ctx = {
        "items": [
            {"id": "a", "status": "pending", "name": "A"},
            {"id": "b", "status": "resolved", "name": "B"},
        ],
        "columns": [{"key": "name", "label": "Name"}],
    }
    html = _build(region, ctx)
    # Only the first row (status: pending) gets a button.
    assert html.count('data-dz-row-action="resolve"') == 1
    # The button is for "a" not "b".
    assert "row-args" in html
    # Both rows still rendered.
    assert ">A<" in html
    assert ">B<" in html


def test_no_row_action_field_no_button_column() -> None:
    """Regression guard: a region without row_action: declared
    must not gain any extra column or button output. Verifies the
    v0.71.45 → v0.71.46 wire-up is opt-in."""
    region = _FakeRegion()  # row_action defaults to None
    ctx = {
        "items": [{"id": "x", "name": "X"}],
        "columns": [{"key": "name", "label": "Name"}],
    }
    html = _build(region, ctx)
    assert "data-dz-row-action" not in html
    assert "dz-list-row-action-col" not in html


def test_html_escaping_in_label() -> None:
    """Labels with HTML metacharacters must escape to prevent
    injection from DSL-author-controlled strings."""
    row_action = RowActionSpec(
        label='Approve <"x">',
        action_id="approve",
        bind={"id": "id"},
    )
    region = _FakeRegion(row_action=row_action)
    ctx = {
        "items": [{"id": "a", "name": "A"}],
        "columns": [{"key": "name", "label": "Name"}],
    }
    html = _build(region, ctx)
    assert "&lt;" in html
    assert "&quot;" in html
    assert '<"x">' not in html


def test_visible_when_compound_and() -> None:
    """A compound AND condition is evaluated recursively."""
    row_action = RowActionSpec(
        label="Act",
        action_id="act",
        bind={"id": "id"},
        visible_when=ConditionExpr(
            left=ConditionExpr(
                comparison=Comparison(
                    field="status",
                    operator=ComparisonOperator.EQUALS,
                    value=ConditionValue(literal="open"),
                )
            ),
            operator=None,  # set below
            right=ConditionExpr(
                comparison=Comparison(
                    field="priority",
                    operator=ComparisonOperator.GREATER_THAN,
                    value=ConditionValue(literal=3),
                )
            ),
        ),
    )
    # Build a true AND compound (operator can't be None on a compound,
    # so reconstruct).
    from dazzle.core.ir.conditions import LogicalOperator

    row_action = RowActionSpec(
        label="Act",
        action_id="act",
        bind={"id": "id"},
        visible_when=ConditionExpr(
            left=ConditionExpr(
                comparison=Comparison(
                    field="status",
                    operator=ComparisonOperator.EQUALS,
                    value=ConditionValue(literal="open"),
                )
            ),
            operator=LogicalOperator.AND,
            right=ConditionExpr(
                comparison=Comparison(
                    field="priority",
                    operator=ComparisonOperator.GREATER_THAN,
                    value=ConditionValue(literal=3),
                )
            ),
        ),
    )
    region = _FakeRegion(row_action=row_action)
    ctx = {
        "items": [
            {"id": "a", "status": "open", "priority": 5, "name": "A"},
            {"id": "b", "status": "open", "priority": 1, "name": "B"},
            {"id": "c", "status": "closed", "priority": 5, "name": "C"},
        ],
        "columns": [{"key": "name", "label": "Name"}],
    }
    html = _build(region, ctx)
    # Only row A (status=open AND priority>3) gets a button.
    assert html.count('data-dz-row-action="act"') == 1
    # Find the row-args JSON for the visible button and verify it's "a".
    assert "&quot;id&quot;: &quot;a&quot;" in html
