"""#1315 — derived FK-graph step ordering for create-DAG atomic flows.

End-to-end (parse → link → validate) coverage that:

1. An author can declare a create-DAG flow's steps **out of FK order**; the
   linker derives a parent-before-child `derived_step_order` from the FK graph,
   and validation passes (the `above`-ref is checked in execution order).
2. A flow already in declared parent-before-child order keeps
   `derived_step_order = None` (no reorder needed).
3. A flow with an `update` step is never reordered (declared order).
4. The executor runs steps in derived order when set.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from dazzle.core import ir
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import validate_atomic_flows

_BASE = """\
module test

app test "Test"

entity Invoice "Invoice":
  id: uuid pk
  ref: str(40) required

entity LineItem "Line Item":
  id: uuid pk
  invoice: ref Invoice required
  amount: int required
"""


def _link(extra: str) -> ir.AppSpec:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(_BASE + extra)
        tmp = Path(f.name)
    return build_appspec(parse_modules([tmp]), root_module_name="test", known_renderers=None)


def _flow(appspec: ir.AppSpec, name: str) -> ir.AtomicFlowSpec:
    return next(f for f in appspec.atomic_flows if f.name == name)


def test_out_of_order_create_dag_is_reordered_and_validates() -> None:
    # LineItem (child) declared BEFORE Invoice (parent) — today this would be an
    # `above`-ref error; #1315 derives parent-first order so it's legal.
    appspec = _link(
        """
atomic make_invoice "Make Invoice":
  permit:
    execute: role(admin)
  input ref: str(40) required
  input amount: int required

  create LineItem:
    invoice: above.Invoice.id
    amount: input.amount

  create Invoice:
    ref: input.ref
"""
    )
    flow = _flow(appspec, "make_invoice")
    # steps stay in declared order (LineItem, Invoice); derived order runs Invoice first.
    assert [s.entity for s in flow.steps] == ["LineItem", "Invoice"]
    assert flow.derived_step_order is not None
    ordered = [flow.steps[i].entity for i in flow.derived_step_order]
    assert ordered == ["Invoice", "LineItem"]

    errors, _ = validate_atomic_flows(appspec)
    assert not [e for e in errors if "make_invoice" in e], errors


def test_already_ordered_create_dag_keeps_none() -> None:
    appspec = _link(
        """
atomic make_invoice "Make Invoice":
  permit:
    execute: role(admin)
  input ref: str(40) required
  input amount: int required

  create Invoice:
    ref: input.ref

  create LineItem:
    invoice: above.Invoice.id
    amount: input.amount
"""
    )
    flow = _flow(appspec, "make_invoice")
    # Declared order is already parent-before-child → no derived order carried.
    assert flow.derived_step_order is None


def test_flow_with_update_step_is_not_reordered() -> None:
    appspec = _link(
        """
atomic touch "Touch":
  permit:
    execute: role(admin)
  input ref: str(40) required
  input invoice: ref Invoice required

  create LineItem:
    invoice: input.invoice
    amount: 1

  update Invoice(input.invoice):
    ref: input.ref
"""
    )
    flow = _flow(appspec, "touch")
    assert flow.derived_step_order is None  # any update → declared order


def test_executor_runs_in_derived_order() -> None:
    from dazzle.http.runtime.atomic_flow_executor import execute_atomic_flow

    # A 2-create flow whose derived order reverses the declared order.
    flow = ir.AtomicFlowSpec(
        name="f",
        label="F",
        permit_execute=["admin"],
        inputs=[],
        steps=[
            ir.FlowCreate(
                entity="LineItem",
                assignments={
                    "invoice": ir.FlowFieldValue(
                        kind=ir.FlowFieldValueKind.ABOVE_REF,
                        above_entity="Invoice",
                        above_field="id",
                    )
                },
            ),
            ir.FlowCreate(
                entity="Invoice",
                assignments={
                    "ref": ir.FlowFieldValue(kind=ir.FlowFieldValueKind.LITERAL, literal="x")
                },
            ),
        ],
        derived_step_order=[1, 0],  # run Invoice (idx 1) first, then LineItem (idx 0)
    )
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cursor)
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    db = MagicMock()
    db.placeholder = "%s"
    db.connection = MagicMock(return_value=ctx)

    execute_atomic_flow(flow, {}, db)
    # First INSERT must be Invoice (derived order), second LineItem.
    first_sql = cursor.execute.call_args_list[0].args[0]
    second_sql = cursor.execute.call_args_list[1].args[0]
    assert "Invoice" in first_sql
    assert "LineItem" in second_sql
