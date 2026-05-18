"""#1148: typed ``row_action:`` block on row-oriented regions.

Per-row click-to-POST action that resolves against the project's
declared surface actions. Closes the "every workflow surface needs
a custom Python route for its primary per-row action" gap that
AegisMark/Manuscript review/Fastmark all worked around.

These tests pin the IR + parser surface. Renderer plumbing per
display mode (list, cohort_strip, day_timeline, status_list)
lands in follow-up commits — the parser locks the design shape
first so projects can author DSL ahead of full renderer support.
"""

from __future__ import annotations

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir import RowActionSpec


def _parse(body: str) -> object:
    """Wrap a region body in module/app/entity/workspace boilerplate
    and return the parsed RowActionSpec (or raise ParseError).
    """
    src = f"""module ops
app demo_app "Demo"

entity Item "Item":
  id: uuid pk
  status: str(50)
  priority: int

workspace dash "Dash":
  things:
    source: Item
    display: list
    row_action:
{body}
"""
    result = parse_dsl(src, "test.dsl")
    fragment = result[5]
    ws = fragment.workspaces[0]
    region = ws.regions[0]
    return region.row_action


def test_parses_minimal_row_action() -> None:
    spec = _parse(
        """      label: "Approve"
      action_id: approve
"""
    )
    assert isinstance(spec, RowActionSpec)
    assert spec.label == "Approve"
    assert spec.action_id == "approve"
    assert spec.bind == {}
    assert spec.visible_when is None
    assert spec.confirm is None


def test_parses_bind_block() -> None:
    spec = _parse(
        """      label: "Approve"
      action_id: approve
      bind:
        id: id
        target_status: priority
"""
    )
    assert spec is not None
    assert spec.bind == {"id": "id", "target_status": "priority"}


def test_parses_visible_when() -> None:
    spec = _parse(
        """      label: "Resolve"
      action_id: resolve
      visible_when: status != resolved
"""
    )
    assert spec is not None
    assert spec.visible_when is not None  # ConditionExpr parsed


def test_parses_confirm_block() -> None:
    spec = _parse(
        """      label: "Release"
      action_id: release
      confirm:
        title: "Release to school?"
        caption: "Audit trail will be visible"
        required: true
"""
    )
    assert spec is not None
    assert spec.confirm is not None
    assert spec.confirm.title == "Release to school?"
    assert spec.confirm.caption == "Audit trail will be visible"
    assert spec.confirm.required is True


def test_confirm_required_defaults_true() -> None:
    spec = _parse(
        """      label: "Release"
      action_id: release
      confirm:
        title: "Release?"
"""
    )
    assert spec.confirm is not None
    assert spec.confirm.required is True


def test_full_shape() -> None:
    """The canonical AegisMark example from the issue."""
    spec = _parse(
        """      label: "Approve & release"
      action_id: feedback_release
      bind:
        id: id
      visible_when: status != released
      confirm:
        title: "Release to school?"
        caption: "School admins see the audit trail"
"""
    )
    assert spec.label == "Approve & release"
    assert spec.action_id == "feedback_release"
    assert spec.bind == {"id": "id"}
    assert spec.visible_when is not None
    assert spec.confirm is not None
    assert spec.confirm.title == "Release to school?"


def test_missing_label_rejected() -> None:
    with pytest.raises(ParseError, match="label.*action_id|action_id.*label"):
        _parse(
            """      action_id: approve
"""
        )


def test_missing_action_id_rejected() -> None:
    with pytest.raises(ParseError, match="label.*action_id|action_id.*label"):
        _parse(
            """      label: "Approve"
"""
        )


def test_unknown_key_rejected() -> None:
    with pytest.raises(ParseError, match="Unknown row_action key"):
        _parse(
            """      label: "Approve"
      action_id: approve
      bogus_field: whatever
"""
        )


def test_confirm_without_title_rejected() -> None:
    with pytest.raises(ParseError, match="confirm requires a `title:`"):
        _parse(
            """      label: "Release"
      action_id: release
      confirm:
        caption: "no title here"
"""
        )


def test_region_without_row_action_has_none() -> None:
    """A region that doesn't declare row_action: must have row_action=None
    (regression guard — the field is optional, no default RowActionSpec)."""
    src = """module ops
app demo_app "Demo"

entity Thing "Thing":
  id: uuid pk

workspace dash "Dash":
  things:
    source: Thing
    display: list
"""
    result = parse_dsl(src, "test.dsl")
    region = result[5].workspaces[0].regions[0]
    assert region.row_action is None
