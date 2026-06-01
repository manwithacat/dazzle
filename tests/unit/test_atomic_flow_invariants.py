import tempfile
from pathlib import Path

from dazzle.core import ir
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules

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
"""


def _link(extra: str) -> ir.AppSpec:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(_BASE + extra)
        tmp = Path(f.name)
    return build_appspec(parse_modules([tmp]), root_module_name="test", known_renderers=None)


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
        filter_predicate=None,  # attached by the linker; raw IR allows None
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
