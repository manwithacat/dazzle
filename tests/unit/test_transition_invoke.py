"""#1319 / ADR-0032 Slice A — transition `invoke <flow>(...)` surface.

IR + parser + validator for declaring that a state-machine transition invokes a
named atomic flow. Slice A is surface-only: the binding is parsed + validated +
analyzable; the live shared-transaction wiring is Slice B.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.validator import validate_transition_invocations


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


def _appspec(dsl: str) -> ir.AppSpec:
    frag = parse_dsl(dsl, Path("t.dz"))[-1]
    return ir.AppSpec(
        name="t",
        version="0.0.0",
        domain=ir.DomainSpec(entities=list(frag.entities)),
        surfaces=[],
        atomic_flows=list(frag.atomic_flows),
    )


_ORDER_ENTITY = """\
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
      invoke {invoke}
"""

_FLOW = """\
atomic fulfil_order "Fulfil":
  permit:
    execute: role(admin)
  input order: ref Order required
  input warehouse: str(40) required
  create Shipment:
    order: input.order

entity Shipment "Shipment":
  id: uuid pk
  order: ref Order required
"""


def _errors(invoke: str) -> list[str]:
    dsl = _ORDER_ENTITY.format(invoke=invoke) + _FLOW
    errs, _ = validate_transition_invocations(_appspec(dsl))
    return errs


def test_validate_unknown_flow_errors() -> None:
    errs = _errors("nonexistent(order: self, warehouse: input.warehouse)")
    assert any("unknown atomic flow" in e for e in errs), errs


def test_validate_missing_required_binding_errors() -> None:
    # `warehouse` (required) not bound.
    errs = _errors("fulfil_order(order: self)")
    assert any("does not bind required input 'warehouse'" in e for e in errs), errs


def test_validate_unknown_binding_errors() -> None:
    errs = _errors("fulfil_order(order: self, warehouse: input.warehouse, bogus: self)")
    assert any("binds unknown input 'bogus'" in e for e in errs), errs


def test_validate_valid_invoke_clean() -> None:
    errs = _errors("fulfil_order(order: self, warehouse: input.warehouse)")
    assert errs == [], errs


def test_transition_atomic_fixture_validates_clean() -> None:
    # The shipped fixture: an on_transition invoke that parses + validates with
    # the real linker (anchors, atomic_flows populated).
    from dazzle.core.appspec_loader import load_project_appspec

    appspec = load_project_appspec(Path("fixtures/transition_atomic"))
    order = next(e for e in appspec.domain.entities if e.name == "Order")
    assert order.state_machine is not None
    t = next(tr for tr in order.state_machine.transitions if tr.to_state == "fulfilled")
    assert t.invoke_flow is not None
    assert t.invoke_flow.flow_name == "fulfil_order"

    errs, _ = validate_transition_invocations(appspec)
    assert errs == [], errs


def test_validate_rejects_invoke_on_auto_transition() -> None:
    # An `auto` (scheduled/system) transition has no user principal → reject a
    # guarded invoke at validate time (ADR-0032 Slice B).
    dsl = (
        """\
module t
app a "A"

entity Order "Order":
  id: uuid pk
  status: enum[submitted,fulfilled]=submitted
  warehouse: str(40)

  transitions:
    submitted -> fulfilled: auto after 1 days

  on_transition:
    submitted -> fulfilled:
      invoke fulfil_order(order: self, warehouse: input.warehouse)
"""
        + _FLOW
    )
    errs, _ = validate_transition_invocations(_appspec(dsl))
    assert any("auto" in e for e in errs), errs
