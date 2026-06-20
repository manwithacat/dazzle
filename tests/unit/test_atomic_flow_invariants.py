import tempfile
from pathlib import Path

from dazzle.core import ir
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import validate_atomic_flows
from dazzle.http.runtime.atomic_flow_invariants import build_invariant_sql

_BASE = """\
module test

app test "Test"

entity Transaction "Transaction":
  id: uuid pk
  ref: str(40) required

entity Posting "Posting":
  id: uuid pk
  transaction: ref Transaction required
  amount: int required
  label: str(40)
"""


def _link(extra: str) -> ir.AppSpec:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(_BASE + extra)
        tmp = Path(f.name)
    return build_appspec(parse_modules([tmp]), root_module_name="test", known_renderers=None)


def _flow_invariant_errors(appspec: ir.AppSpec) -> list[str]:
    """Validator errors that mention an invariant (filters out step-level noise)."""
    errors, _ = validate_atomic_flows(appspec)
    return [e for e in errors if "invariant" in e]


def test_linker_derives_invariant_anchor():
    appspec = _link(
        """
atomic post "Post":
  permit:
    execute: role(admin)
  input txn: ref Transaction required
  create Posting:
    transaction: input.txn
    amount: 0
  invariant: sum(Posting.amount where transaction = input.txn) = 0
"""
    )
    inv = appspec.atomic_flows[0].invariants[0]
    assert inv.anchor_entity == "Transaction"
    assert inv.anchor_input == "txn"


def test_linker_leaves_unanchored_none():
    appspec = _link(
        """
atomic post "Post":
  permit:
    execute: role(admin)
  input txn: ref Transaction required
  create Posting:
    transaction: input.txn
    amount: 0
  invariant: sum(Posting.amount where amount = 0) = 0
"""
    )
    inv = appspec.atomic_flows[0].invariants[0]
    assert inv.anchor_entity is None
    assert inv.anchor_input is None


def test_flow_invariant_ir_roundtrips():
    inv = ir.FlowInvariant(
        agg_fn=ir.FlowAggregateFn.SUM,
        entity="Posting",
        field="amount",
        anchor_entity=None,
        anchor_input=None,
        op=ir.CompOp.EQ,
        rhs=ir.InvariantRhs(literal=0),
    )
    assert inv.agg_fn == ir.FlowAggregateFn.SUM
    assert inv.rhs.literal == 0
    flow = ir.AtomicFlowSpec(
        name="f",
        label="F",
        permit_execute=["a"],
        inputs=[],
        steps=[],
    )
    assert flow.invariants == []


def test_validate_rejects_unanchored_invariant():
    # No `<fk> = input.<x>` term ⇒ linker leaves anchor None ⇒ rejected.
    appspec = _link(
        """
atomic post "Post":
  permit:
    execute: role(admin)
  input txn: ref Transaction required
  create Posting:
    transaction: input.txn
    amount: 0
  invariant: sum(Posting.amount where amount = 0) = 0
"""
    )
    errs = _flow_invariant_errors(appspec)
    assert any("unanchored" in e for e in errs), errs


def test_validate_rejects_sum_nonnumeric_field():
    appspec = _link(
        """
atomic post "Post":
  permit:
    execute: role(admin)
  input txn: ref Transaction required
  create Posting:
    transaction: input.txn
    amount: 0
  invariant: sum(Posting.label where transaction = input.txn) = 0
"""
    )
    errs = _flow_invariant_errors(appspec)
    assert any("numeric" in e for e in errs), errs


# ---------------------------------------------------------------------------
# #1318 Task 6 — pure aggregate SQL builder (build_invariant_sql)
# ---------------------------------------------------------------------------


def test_build_invariant_sql_sum_with_where():
    sql, params = build_invariant_sql(
        ir.FlowAggregateFn.SUM, "Posting", "amount", [("transaction", "abc")]
    )
    assert sql == ('SELECT COALESCE(SUM("amount"), 0) FROM "Posting" WHERE "transaction" = %s')
    assert params == ["abc"]


def test_build_invariant_sql_sum_multiple_where_terms():
    sql, params = build_invariant_sql(
        ir.FlowAggregateFn.SUM, "Posting", "amount", [("transaction", "t"), ("kind", "debit")]
    )
    assert sql == (
        'SELECT COALESCE(SUM("amount"), 0) FROM "Posting" WHERE "transaction" = %s AND "kind" = %s'
    )
    assert params == ["t", "debit"]


def test_build_invariant_sql_count():
    sql, params = build_invariant_sql(
        ir.FlowAggregateFn.COUNT, "Posting", None, [("transaction", "t")]
    )
    assert sql == 'SELECT COUNT(*) FROM "Posting" WHERE "transaction" = %s'
    assert params == ["t"]


def test_build_invariant_sql_no_where_terms():
    sql, params = build_invariant_sql(ir.FlowAggregateFn.COUNT, "Posting", None, [])
    assert sql == 'SELECT COUNT(*) FROM "Posting"'
    assert params == []

    sql2, params2 = build_invariant_sql(ir.FlowAggregateFn.SUM, "Posting", "amount", [])
    assert sql2 == 'SELECT COALESCE(SUM("amount"), 0) FROM "Posting"'
    assert params2 == []


def test_validate_accepts_valid_invariant():
    appspec = _link(
        """
atomic post "Post":
  permit:
    execute: role(admin)
  input txn: ref Transaction required
  create Posting:
    transaction: input.txn
    amount: 0
  invariant: sum(Posting.amount where transaction = input.txn) = 0
"""
    )
    errs = _flow_invariant_errors(appspec)
    assert errs == [], errs


def test_validate_rejects_unknown_invariant_entity():
    appspec = _link(
        """
atomic post "Post":
  permit:
    execute: role(admin)
  input txn: ref Transaction required
  create Posting:
    transaction: input.txn
    amount: 0
  invariant: sum(Nope.amount where transaction = input.txn) = 0
"""
    )
    errs = _flow_invariant_errors(appspec)
    assert any("unknown entity 'Nope'" in e for e in errs), errs


def test_validate_accepts_field_rhs_invariant():
    _BUDGET = """
entity Budget "Budget":
  id: uuid pk
  total: int required

entity Allocation "Allocation":
  id: uuid pk
  budget: ref Budget required
  amount: int required
"""
    appspec = _link(
        _BUDGET
        + """
atomic allocate "Allocate":
  permit:
    execute: role(admin)
  input budget: ref Budget required
  create Allocation:
    budget: input.budget
    amount: 0
  invariant: sum(Allocation.amount where budget = input.budget) <= input.budget.total
"""
    )
    errs = _flow_invariant_errors(appspec)
    assert errs == [], errs


def test_validate_rejects_field_rhs_nonnumeric():
    _BUDGET = """
entity Budget "Budget":
  id: uuid pk
  name: str(40) required

entity Allocation "Allocation":
  id: uuid pk
  budget: ref Budget required
  amount: int required
"""
    appspec = _link(
        _BUDGET
        + """
atomic allocate "Allocate":
  permit:
    execute: role(admin)
  input budget: ref Budget required
  create Allocation:
    budget: input.budget
    amount: 0
  invariant: sum(Allocation.amount where budget = input.budget) <= input.budget.name
"""
    )
    errs = _flow_invariant_errors(appspec)
    assert any("numeric" in e for e in errs), errs
