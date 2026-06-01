"""#1228 Phase 3c slice 3c.i — parser + validator for `atomic` block.

The new top-level construct declares a multi-entity creation operation
that the runtime will execute in a single DB transaction. This slice
ships IR + parser + validator only; the runtime + route generation
lands in 3c.ii.

Note: the DSL keyword is ``atomic`` (not ``flow`` from the original
proposal) because ``flow`` already names the E2E test construct.

These tests pin:

1. ``atomic <name> "Label":`` parses into AtomicFlowSpec with inputs +
   creates + permit_execute populated.
2. ``input X: <type> required`` reuses the existing type-spec grammar.
3. RHS forms parse correctly: ``input.X`` → INPUT_REF, ``above.E.id``
   → ABOVE_REF, literals → LITERAL.
4. validate_atomic_flows catches: unknown create-target entity, unknown
   assignment field, forward above-ref, undeclared input-ref, missing
   permit, duplicate input, duplicate create target, above-ref to a
   non-id field.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.validator import validate_atomic_flows


def _parse_fragment(dsl: str):
    return parse_dsl(dsl, Path("test.dz"))[-1]


def _appspec(dsl: str) -> ir.AppSpec:
    """Build a minimal AppSpec direct from a parsed fragment.

    Skips the linker — validate_atomic_flows only needs domain.entities
    + atomic_flows populated, and this avoids the linker plumbing for
    the unit test.
    """
    fragment = _parse_fragment(dsl)
    return ir.AppSpec(
        name="test",
        version="0.0.0",
        domain=ir.DomainSpec(entities=list(fragment.entities)),
        surfaces=[],
        atomic_flows=list(fragment.atomic_flows),
    )


def _base_entities() -> str:
    return """\
module test.core
app a "A"

entity Person "Person":
  id: uuid pk
  legal_name: str(200) required
  email: email

entity Employment "Employment":
  id: uuid pk
  person: ref Person required
  role: ref Role required

entity Role "Role":
  id: uuid pk
  title: str(120) required
"""


class TestAtomicFlowParser:
    def test_basic_parses(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "Onboard Starter":
  intent: "Atomically create Person + Employment"
  permit:
    execute: role(hr_admin)
  on_failure: rollback_all

  input legal_name: str(200) required
  input role_id: uuid required

  create Person:
    legal_name: input.legal_name

  create Employment:
    person: above.Person.id
    role: input.role_id
"""
        )
        frag = _parse_fragment(dsl)
        assert len(frag.atomic_flows) == 1
        af = frag.atomic_flows[0]
        assert af.name == "onboard"
        assert af.label == "Onboard Starter"
        assert af.intent == "Atomically create Person + Employment"
        assert af.permit_execute == ["hr_admin"]
        assert af.on_failure == ir.FlowFailureMode.ROLLBACK_ALL
        assert [(i.name, i.required) for i in af.inputs] == [
            ("legal_name", True),
            ("role_id", True),
        ]
        assert [s.entity for s in af.steps] == ["Person", "Employment"]

    def test_audit_defaults_to_async(self) -> None:
        # #1317 — no `audit:` line → ASYNC (the shipped slice-1e behaviour).
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  input legal_name: str(200) required
  create Person:
    legal_name: input.legal_name
"""
        )
        af = _parse_fragment(dsl).atomic_flows[0]
        assert af.audit_mode == ir.FlowAuditMode.ASYNC

    def test_audit_strict_parses(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  audit: strict
  input legal_name: str(200) required
  create Person:
    legal_name: input.legal_name
"""
        )
        af = _parse_fragment(dsl).atomic_flows[0]
        assert af.audit_mode == ir.FlowAuditMode.STRICT

    def test_audit_async_explicit_parses(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  audit: async
  input legal_name: str(200) required
  create Person:
    legal_name: input.legal_name
"""
        )
        af = _parse_fragment(dsl).atomic_flows[0]
        assert af.audit_mode == ir.FlowAuditMode.ASYNC

    def test_audit_invalid_value_errors(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  audit: bogus
  input legal_name: str(200) required
  create Person:
    legal_name: input.legal_name
"""
        )
        with pytest.raises(ParseError, match="audit"):
            _parse_fragment(dsl)

    def test_input_ref_assignment(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  input legal_name: str(200) required
  create Person:
    legal_name: input.legal_name
"""
        )
        frag = _parse_fragment(dsl)
        v = frag.atomic_flows[0].steps[0].assignments["legal_name"]
        assert v.kind == ir.FlowFieldValueKind.INPUT_REF
        assert v.input_name == "legal_name"

    def test_above_ref_assignment(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  create Person:
    legal_name: "hardcoded"
  create Employment:
    person: above.Person.id
"""
        )
        frag = _parse_fragment(dsl)
        v = frag.atomic_flows[0].steps[1].assignments["person"]
        assert v.kind == ir.FlowFieldValueKind.ABOVE_REF
        assert v.above_entity == "Person"
        assert v.above_field == "id"

    def test_literal_string_assignment(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  create Person:
    legal_name: "Alice"
"""
        )
        frag = _parse_fragment(dsl)
        v = frag.atomic_flows[0].steps[0].assignments["legal_name"]
        assert v.kind == ir.FlowFieldValueKind.LITERAL
        assert v.literal == "Alice"

    def test_literal_bare_identifier_assignment(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  create Person:
    legal_name: alice
"""
        )
        frag = _parse_fragment(dsl)
        v = frag.atomic_flows[0].steps[0].assignments["legal_name"]
        assert v.kind == ir.FlowFieldValueKind.LITERAL
        assert v.literal == "alice"

    def test_multiple_permit_roles(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(hr_admin, super_admin)
  create Person:
    legal_name: "x"
"""
        )
        frag = _parse_fragment(dsl)
        assert frag.atomic_flows[0].permit_execute == ["hr_admin", "super_admin"]

    def test_invariant_count_parses(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  input role_id: uuid required
  create Person:
    legal_name: "x"
  invariant: count(Employment where person = input.role_id) >= 1
"""
        )
        af = _parse_fragment(dsl).atomic_flows[0]
        assert len(af.invariants) == 1
        inv = af.invariants[0]
        assert inv.agg_fn == ir.FlowAggregateFn.COUNT
        assert inv.entity == "Employment"
        assert inv.field is None
        assert inv.op == ir.CompOp.GTE
        assert inv.rhs.literal == 1
        # raw filter captured for the linker: column `person` = input `role_id`
        assert inv.raw_filter == (("person", "input", "role_id"),)

    def test_invariant_sum_with_literal_rhs(self) -> None:
        dsl = (
            _base_entities()
            + """
entity Transaction "Transaction":
  id: uuid pk

entity Posting "Posting":
  id: uuid pk
  transaction: ref Transaction required
  amount: decimal(12,2) required

atomic post "X":
  permit:
    execute: role(admin)
  input txn: uuid required
  create Person:
    legal_name: "x"
  invariant: sum(Posting.amount where transaction = input.txn) = 0
"""
        )
        af = _parse_fragment(dsl).atomic_flows[0]
        assert len(af.invariants) == 1
        inv = af.invariants[0]
        assert inv.agg_fn == ir.FlowAggregateFn.SUM
        assert inv.entity == "Posting"
        assert inv.field == "amount"
        assert inv.op == ir.CompOp.EQ
        assert inv.rhs.literal == 0
        assert inv.raw_filter == (("transaction", "input", "txn"),)

    def test_invariant_anchor_input_rhs(self) -> None:
        dsl = (
            _base_entities()
            + """
entity Budget "Budget":
  id: uuid pk
  total: decimal(12,2) required

entity Allocation "Allocation":
  id: uuid pk
  budget: ref Budget required
  amount: decimal(12,2) required

atomic allocate "X":
  permit:
    execute: role(admin)
  input budget: uuid required
  create Person:
    legal_name: "x"
  invariant: sum(Allocation.amount where budget = input.budget) <= input.budget.total
"""
        )
        af = _parse_fragment(dsl).atomic_flows[0]
        inv = af.invariants[0]
        assert inv.agg_fn == ir.FlowAggregateFn.SUM
        assert inv.entity == "Allocation"
        assert inv.field == "amount"
        assert inv.op == ir.CompOp.LTE
        assert inv.rhs.literal is None
        assert inv.rhs.anchor_input == "budget"
        assert inv.rhs.anchor_field == "total"
        assert inv.raw_filter == (("budget", "input", "budget"),)

    def test_invariant_bad_aggregate_errors(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  input role_id: uuid required
  create Person:
    legal_name: "x"
  invariant: avg(Employment where person = input.role_id) >= 1
"""
        )
        with pytest.raises(ParseError, match="sum"):
            _parse_fragment(dsl)

    def test_update_step_parses(self) -> None:
        """#1313: `update <Entity>(<target>):` parses into a FlowUpdate with a
        row-selector target + assignments, preserving declaration order."""
        dsl = (
            _base_entities()
            + """
atomic reassign "Reassign":
  permit:
    execute: role(admin)
  input person_id: uuid required
  input new_email: email required
  update Person(input.person_id):
    email: input.new_email
  create Employment:
    person: above.Person.id
"""
        )
        frag = _parse_fragment(dsl)
        steps = frag.atomic_flows[0].steps
        assert [type(s).__name__ for s in steps] == ["FlowUpdate", "FlowCreate"]
        upd = steps[0]
        assert isinstance(upd, ir.FlowUpdate)
        assert upd.entity == "Person"
        assert upd.kind == "update"
        assert upd.target.kind == ir.FlowFieldValueKind.INPUT_REF
        assert upd.target.input_name == "person_id"
        assert upd.assignments["email"].kind == ir.FlowFieldValueKind.INPUT_REF
        assert upd.assignments["email"].input_name == "new_email"


class TestAtomicFlowValidator:
    def test_valid_flow_no_errors(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  input legal_name: str(200) required
  create Person:
    legal_name: input.legal_name
  create Employment:
    person: above.Person.id
    role: above.Role.id
  create Role:
    title: "Dev"
"""
        )
        # NB: above.Role.id from Employment is a forward ref since Role
        # is declared *after* Employment in this DSL — should error.
        appspec = _appspec(dsl)
        errors, _ = validate_atomic_flows(appspec)
        assert any("'Role' is not created earlier in this flow" in e for e in errors)

    def test_unknown_create_target_errors(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  create Unknown:
    foo: "x"
"""
        )
        appspec = _appspec(dsl)
        errors, _ = validate_atomic_flows(appspec)
        assert any("unknown entity 'Unknown'" in e for e in errors)

    def test_unknown_assignment_field_errors(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  create Person:
    not_a_field: "x"
"""
        )
        appspec = _appspec(dsl)
        errors, _ = validate_atomic_flows(appspec)
        assert any("unknown field 'not_a_field'" in e for e in errors)

    def test_undeclared_input_ref_errors(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  create Person:
    legal_name: input.never_declared
"""
        )
        appspec = _appspec(dsl)
        errors, _ = validate_atomic_flows(appspec)
        assert any("undeclared input 'never_declared'" in e for e in errors)

    def test_missing_permit_errors(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  create Person:
    legal_name: "x"
"""
        )
        appspec = _appspec(dsl)
        errors, _ = validate_atomic_flows(appspec)
        assert any("must declare `permit: execute: role(...)`" in e for e in errors)

    def test_no_creates_errors(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
"""
        )
        appspec = _appspec(dsl)
        errors, _ = validate_atomic_flows(appspec)
        assert any("must declare at least one `create` or `update` step" in e for e in errors)

    def test_duplicate_input_errors(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  input foo: str(50) required
  input foo: str(50) required
  create Person:
    legal_name: input.foo
"""
        )
        appspec = _appspec(dsl)
        errors, _ = validate_atomic_flows(appspec)
        assert any("duplicate input 'foo'" in e for e in errors)

    def test_duplicate_create_target_errors(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  create Person:
    legal_name: "a"
  create Person:
    legal_name: "b"
"""
        )
        appspec = _appspec(dsl)
        errors, _ = validate_atomic_flows(appspec)
        assert any("appears more than once" in e for e in errors)

    def test_above_ref_to_non_id_field_errors(self) -> None:
        dsl = (
            _base_entities()
            + """
atomic onboard "X":
  permit:
    execute: role(admin)
  create Person:
    legal_name: "a"
  create Employment:
    person: above.Person.legal_name
"""
        )
        appspec = _appspec(dsl)
        errors, _ = validate_atomic_flows(appspec)
        assert any("only '.id' is supported" in e for e in errors)

    def test_update_target_undeclared_input_errors(self) -> None:
        """#1313: an update's target row-selector must resolve to a declared
        input (or an earlier-created above-ref)."""
        dsl = (
            _base_entities()
            + """
atomic change "X":
  permit:
    execute: role(admin)
  update Person(input.never_declared):
    legal_name: "x"
"""
        )
        appspec = _appspec(dsl)
        errors, _ = validate_atomic_flows(appspec)
        assert any("undeclared input 'never_declared'" in e and "target" in e for e in errors)

    def test_update_unknown_field_errors(self) -> None:
        """#1313: update assignments are field-checked like creates."""
        dsl = (
            _base_entities()
            + """
atomic change "X":
  permit:
    execute: role(admin)
  input pid: uuid required
  update Person(input.pid):
    not_a_field: "x"
"""
        )
        appspec = _appspec(dsl)
        errors, _ = validate_atomic_flows(appspec)
        assert any("unknown field 'not_a_field'" in e for e in errors)
