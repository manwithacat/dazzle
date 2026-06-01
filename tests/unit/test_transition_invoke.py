"""#1319 / ADR-0032 Slice A — transition `invoke <flow>(...)` surface.

IR + parser + validator for declaring that a state-machine transition invokes a
named atomic flow. Slice A is surface-only: the binding is parsed + validated +
analyzable; the live shared-transaction wiring is Slice B.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl


def test_invoke_flow_ir() -> None:
    b = ir.InvokeBinding(flow_input="order", source_kind=ir.InvokeSourceKind.SELF)
    spec = ir.InvokeFlowSpec(flow_name="fulfil_order", bindings=[b])
    assert spec.flow_name == "fulfil_order"
    assert spec.bindings[0].source_kind == ir.InvokeSourceKind.SELF
    assert spec.bindings[0].flow_input == "order"
    # A transition with no invoke leaves the field None.
    t = ir.StateTransition(from_state="a", to_state="b")
    assert t.invoke_flow is None


def _parse_entity(dsl: str) -> ir.EntitySpec:
    frag = parse_dsl(dsl, Path("t.dz"))[-1]
    return frag.entities[0]


def test_parse_transition_invoke() -> None:
    dsl = """\
module t
app a "A"

entity Order "Order":
  id: uuid pk
  status: enum[submitted,fulfilled]=submitted
  warehouse: str(40)

  transitions:
    submitted -> fulfilled: role(admin)

  on_transition:
    submitted -> fulfilled:
      invoke fulfil_order(order: self, warehouse: input.warehouse)
"""
    entity = _parse_entity(dsl)
    sm = entity.state_machine
    assert sm is not None
    t = next(tr for tr in sm.transitions if tr.to_state == "fulfilled")
    assert t.invoke_flow is not None
    assert t.invoke_flow.flow_name == "fulfil_order"
    kinds = [(b.flow_input, b.source_kind, b.source_name) for b in t.invoke_flow.bindings]
    assert kinds == [
        ("order", ir.InvokeSourceKind.SELF, None),
        ("warehouse", ir.InvokeSourceKind.INPUT, "warehouse"),
    ]
