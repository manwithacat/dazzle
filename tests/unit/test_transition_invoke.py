"""#1319 / ADR-0032 Slice A — transition `invoke <flow>(...)` surface.

IR + parser + validator for declaring that a state-machine transition invokes a
named atomic flow. Slice A is surface-only: the binding is parsed + validated +
analyzable; the live shared-transaction wiring is Slice B.
"""

from __future__ import annotations

from dazzle.core import ir


def test_invoke_flow_ir() -> None:
    b = ir.InvokeBinding(flow_input="order", source_kind=ir.InvokeSourceKind.SELF)
    spec = ir.InvokeFlowSpec(flow_name="fulfil_order", bindings=[b])
    assert spec.flow_name == "fulfil_order"
    assert spec.bindings[0].source_kind == ir.InvokeSourceKind.SELF
    assert spec.bindings[0].flow_input == "order"
    # A transition with no invoke leaves the field None.
    t = ir.StateTransition(from_state="a", to_state="b")
    assert t.invoke_flow is None
