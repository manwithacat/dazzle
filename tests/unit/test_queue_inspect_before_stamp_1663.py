"""#1663: queue inline SM PUTs — inspect-before-stamp.

``transitions: none`` on a queue/list region forbids pile stamps.
``requires`` / ``when`` / expr guards never emit as queue buttons
even without the flag. Role-only no-input stamps stay unless none.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.ir.domain import EntitySpec
from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.state_machine import (
    StateMachineSpec,
    StateTransition,
    TransitionGuard,
)
from dazzle.http.runtime.workspace_region_computes import compute_queue

ROOT = Path(__file__).resolve().parents[2]
SURFACES = ROOT / "examples/invoice_ops/dsl/surfaces.dsl"


def _pk() -> FieldSpec:
    return FieldSpec(
        name="id",
        type=FieldType(kind=FieldTypeKind.UUID),
        modifiers=[FieldModifier.PK],
    )


def _ticket(*, transitions: list[StateTransition]) -> EntitySpec:
    return EntitySpec(
        name="Ticket",
        fields=[_pk()],
        state_machine=StateMachineSpec(
            status_field="status",
            states=["open", "closed", "rejected"],
            transitions=transitions,
        ),
    )


_SRC = """module ops
app t "T"

entity Ticket "Ticket":
  id: uuid pk

workspace desk "Desk":
  q:
    source: Ticket
    display: queue
{extra}
"""


def _parse_region_transitions(extra: str) -> object:
    return parse_dsl(_SRC.format(extra=extra), "t.dsl")[5].workspaces[0].regions[0].transitions


def test_transitions_keyword_parses() -> None:
    assert _parse_region_transitions("    transitions: none") == "none"
    assert _parse_region_transitions("    transitions: inline") == "inline"
    assert _parse_region_transitions("") is None


def test_transitions_invalid_value_rejected() -> None:
    with pytest.raises(ParseError, match="transitions"):
        _parse_region_transitions("    transitions: sideways")


def test_requires_field_never_emits_as_queue_inline() -> None:
    entity = _ticket(
        transitions=[
            StateTransition(
                from_state="open",
                to_state="closed",
                guards=[TransitionGuard(requires_role="agent")],
            ),
            StateTransition(
                from_state="open",
                to_state="rejected",
                guards=[
                    TransitionGuard(requires_role="agent", requires_field="rejection_reason"),
                ],
            ),
        ]
    )
    trans, status, endpoint = compute_queue(entity, "Ticket")
    assert status == "status"
    assert endpoint == "/tickets"
    assert [t["to_state"] for t in trans] == ["closed"]
    assert "rejected" not in {t["to_state"] for t in trans}


def test_role_only_ack_stays_inline() -> None:
    entity = _ticket(
        transitions=[
            StateTransition(
                from_state="open",
                to_state="closed",
                guards=[TransitionGuard(requires_role="agent")],
            ),
        ]
    )
    trans, _, _ = compute_queue(entity, "Ticket")
    assert [t["to_state"] for t in trans] == ["closed"]


def test_awaiting_approval_declares_transitions_none() -> None:
    text = SURFACES.read_text()
    desk = text.index('workspace approval_desk "Approval Desk":')
    start = text.index("\n  awaiting_approval:", desk)
    rest = text[start + 1 :]
    nxt = rest.find("\n  live_conversation:")
    block = rest[:nxt]
    assert "display: queue" in block
    assert "transitions: none" in block
    assert "action: invoice_detail" in block
