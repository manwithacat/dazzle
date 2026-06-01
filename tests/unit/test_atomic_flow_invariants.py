from dazzle.core import ir


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
