# Flow-Level Aggregate Invariants Implementation Plan (ADR-0031, #1318)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-flow `invariant:` construct to `atomic` blocks that asserts an aggregate (`sum`/`count`) over a row-filtered set, enforced in-transaction before commit with anchor-row locking, fail-closed.

**Architecture:** IR-first, mirroring the proven #1313–#1317 cadence. A new `FlowInvariant` IR type hangs off `AtomicFlowSpec`; the parser reads `invariant:` lines; the linker/validator resolves + rejects unanchored/invalid forms; the executor, after its step loop and before commit, `SELECT … FOR UPDATE`s the anchor row, runs one aggregate `SELECT … WHERE <filter>`, compares to the bound, and raises (rollback-all) on failure. ADR-0009's row-scoped predicate algebra is **reused** for the `where` filter (compiled via the existing `predicate_compiler`), not extended.

**Tech Stack:** Python 3.12, Pydantic IR models, the existing `dsl_parser_impl` mixins, `predicate_compiler`, psycopg/PostgreSQL, pytest (unit + real-PG integration marked `postgres`).

**Canonical references (read before starting):**
- `docs/adr/0031-flow-level-aggregate-invariants.md` — the accepted decision.
- `docs/adr/0029-atomic-flows-transactional-intent-substrate.md` invariants 6/8 — fail-closed + analyzability.
- `src/dazzle/http/runtime/atomic_flow_executor.py` — the executor this extends; note `_acquire_scope_parent_share_locks` (#1316) for the lock idiom and the `with db_manager.connection() as conn` commit block.
- `src/dazzle/core/dsl_parser_impl/atomic_flow.py` — the `atomic` block parser (the `audit:`/`on_failure:` branches show the keyword-field pattern).
- `src/dazzle/http/runtime/predicate_compiler.py:618` `compile_predicate` — compile an IR `ScopePredicate` to `WHERE` SQL.
- `src/dazzle/core/dsl_parser_impl/entity.py:1327` `_parse_scope_rule` — how a `scope:` condition is parsed into IR (reuse its condition-parsing for the `where`).

---

## DSL surface (target)

```dsl
atomic post_journal "Post a balanced journal entry":
  permit:
    execute: role(accountant)
  input txn: ref Transaction required
  ...steps...
  invariant: sum(Posting.amount where transaction = input.txn) = 0
  invariant: count(Approver where request = input.request) >= 2
  invariant: sum(Allocation.amount where budget = input.budget) <= input.budget.total
```

Shape: `invariant:` `<sum|count>` `(` `<Entity>` [`.` `<field>`] `where` `<predicate>` `)` `<op>` `<rhs>`
- `count` omits the `.field`; `sum` requires it.
- `<predicate>` reuses the scope-condition grammar.
- `<op>` ∈ `= <= >= < >`.
- `<rhs>` is an integer/decimal literal **or** `input.<name>.<field>` (a field on a flow-anchor row).

**Anchor (derived, load-bearing):** the lockable anchor row is identified by a filter term of the form `<fk_field> = input.<name>` where `<fk_field>` is an FK on the target entity. `anchor_entity` = that FK's target; the anchor id = `inputs[<name>]`. A flow invariant whose filter has **no** such single FK-equality-to-input term is **unanchored** → rejected at validate time (ADR-0031 deferred-list: no lockable anchor).

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `src/dazzle/core/ir/atomic_flows.py` | `FlowAggregateFn`, `FlowInvariantOp` (reuse `CompOp`), `InvariantRhs`, `FlowInvariant` types + `AtomicFlowSpec.invariants` | Modify |
| `src/dazzle/core/ir/__init__.py` | export the new public IR names | Modify |
| `src/dazzle/core/dsl_parser_impl/atomic_flow.py` | parse the `invariant:` line into a *raw* `FlowInvariant` (predicate as a parsed condition) | Modify |
| `src/dazzle/core/linker.py` | resolve each invariant's filter → compiled `ScopePredicate`, derive the anchor, attach to the flow | Modify |
| `src/dazzle/core/validator.py` (`validate_atomic_flows`) | reject unknown entity/field, unanchored aggregate, type-mismatched RHS, sum-without-field | Modify |
| `src/dazzle/http/runtime/atomic_flow_invariants.py` | **new** — `enforce_flow_invariants(conn, flow, inputs, fk_graph)`: lock anchors, run aggregates, compare, raise | Create |
| `src/dazzle/http/runtime/atomic_flow_executor.py` | call `enforce_flow_invariants` after the step loop, before commit | Modify |
| `src/dazzle/rbac/matrix.py` | project `flow.invariants` into the matrix JSON/table (analyzability) | Modify |
| `docs/api-surface/ir-types.txt` | regenerated baseline (new IR types) | Regenerate |
| `fixtures/scope_runtime/dsl/*.dsl` | a `balanced_ledger`-style flow that declares an invariant | Modify |
| `tests/unit/test_atomic_flow_parser.py` | parser cases | Modify |
| `tests/unit/test_atomic_flow_invariants.py` | **new** — validator + pure aggregate-SQL-builder unit tests | Create |
| `tests/integration/test_scope_runtime_pg.py` | real-PG: in-bounds commit / out-of-bounds rollback / concurrency | Modify |

---

## Slice 1 — IR + parser (IR-first; executor still ignores invariants)

### Task 1: IR types for a flow invariant

**Files:**
- Modify: `src/dazzle/core/ir/atomic_flows.py`
- Modify: `src/dazzle/core/ir/__init__.py`
- Test: `tests/unit/test_atomic_flow_invariants.py` (Create)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_atomic_flow_invariants.py
from dazzle.core import ir


def test_flow_invariant_ir_roundtrips():
    inv = ir.FlowInvariant(
        agg_fn=ir.FlowAggregateFn.SUM,
        entity="Posting",
        field="amount",
        filter_predicate=None,            # attached by the linker; raw IR allows None
        anchor_entity=None,
        anchor_input=None,
        op=ir.CompOp.EQ,
        rhs=ir.InvariantRhs(literal=0),
    )
    assert inv.agg_fn == ir.FlowAggregateFn.SUM
    assert inv.rhs.literal == 0
    # default: a flow has no invariants
    flow = ir.AtomicFlowSpec(
        name="f", label="F", permit_execute=["a"], inputs=[], steps=[],
    )
    assert flow.invariants == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_atomic_flow_invariants.py::test_flow_invariant_ir_roundtrips -v`
Expected: FAIL — `AttributeError: module 'dazzle.core.ir' has no attribute 'FlowInvariant'`.

- [ ] **Step 3: Add the IR types**

In `src/dazzle/core/ir/atomic_flows.py`, after `FlowAuditMode` (reuse `CompOp` from predicates):

```python
from dazzle.core.ir.predicates import CompOp, ScopePredicate  # add to imports


class FlowAggregateFn(StrEnum):
    """Aggregate function in a flow-level invariant (#1318, ADR-0031)."""

    SUM = "sum"
    COUNT = "count"


class InvariantRhs(BaseModel):
    """Right-hand bound of a flow invariant: a literal OR an anchor-row field.

    Exactly one slot is populated: ``literal`` for `= 0` / `<= 1000`; the
    ``anchor_input`` + ``anchor_field`` pair for `<= input.budget.total`.
    """

    literal: int | float | None = None
    anchor_input: str | None = None
    anchor_field: str | None = None

    model_config = ConfigDict(frozen=True)


class FlowInvariant(BaseModel):
    """A flow-level aggregate invariant (#1318, ADR-0031).

    Asserts ``<agg_fn>(<entity>.<field> where <filter>) <op> <rhs>`` holds at
    commit, or the whole flow rolls back. ``filter_predicate``, ``anchor_entity``
    and ``anchor_input`` are ``None`` in raw parser output and filled in by the
    linker (`_resolve_flow_invariants`).
    """

    agg_fn: FlowAggregateFn
    entity: str
    field: str | None  # None only for COUNT
    filter_predicate: ScopePredicate | None
    anchor_entity: str | None
    anchor_input: str | None
    op: CompOp
    rhs: InvariantRhs
    location: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)
```

Add `invariants: list[FlowInvariant] = []` to `AtomicFlowSpec` (after `steps`).

In `src/dazzle/core/ir/__init__.py`, add to the `from .atomic_flows import (...)` block and `__all__`: `FlowAggregateFn`, `FlowInvariant`, `InvariantRhs`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_atomic_flow_invariants.py::test_flow_invariant_ir_roundtrips -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/ir/atomic_flows.py src/dazzle/core/ir/__init__.py tests/unit/test_atomic_flow_invariants.py
git commit -m "#1318 slice 1: FlowInvariant IR types (ADR-0031, IR-first)"
```

### Task 2: Parse the `invariant:` line

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/atomic_flow.py`
- Test: `tests/unit/test_atomic_flow_parser.py`

The parser produces a **raw** `FlowInvariant` (predicate left as a parsed `ConditionExpr`, anchor `None`) — the linker compiles it. Reuse the scope-condition parser: study `_parse_scope_rule` (`entity.py:1327`) and the `conditions.py` mixin it calls; the `where <predicate>` uses the same condition-expression parser, stopping at the closing `)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_atomic_flow_parser.py  (add)
def test_invariant_sum_parses(self) -> None:
    dsl = _base_entities() + """
atomic onboard "X":
  permit:
    execute: role(admin)
  input legal_name: str(200) required
  create Person:
    legal_name: input.legal_name
  invariant: count(Employment where person = input.person) >= 1
"""
    af = _parse_fragment(dsl).atomic_flows[0]
    assert len(af.invariants) == 1
    inv = af.invariants[0]
    assert inv.agg_fn == ir.FlowAggregateFn.COUNT
    assert inv.entity == "Employment"
    assert inv.field is None
    assert inv.op == ir.CompOp.GTE
    assert inv.rhs.literal == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_atomic_flow_parser.py -k invariant_sum_parses -v`
Expected: FAIL — `invariants` empty / attribute error.

- [ ] **Step 3: Implement the parse branch**

In `parse_atomic_flow` (`atomic_flow.py`), add a local `invariants: list[ir.FlowInvariant] = []`, an `elif self.match(TokenType.INVARIANT):` branch (add `INVARIANT` to the lexer keyword set if absent — see `_lexical.py` / the token table; mirror how `AUDIT`/`ON_FAILURE` are registered), and pass `invariants=invariants` to the `AtomicFlowSpec(...)` call. Implement `_parse_atomic_invariant()`:

```python
def _parse_atomic_invariant(self) -> ir.FlowInvariant:
    """Parse `invariant: <sum|count>(<Entity>[.<field>] where <pred>) <op> <rhs>`."""
    self.expect(TokenType.INVARIANT)
    self.expect(TokenType.COLON)
    fn_tok = self.expect_identifier_or_keyword()
    agg = {"sum": ir.FlowAggregateFn.SUM, "count": ir.FlowAggregateFn.COUNT}.get(str(fn_tok.value))
    if agg is None:
        raise make_parse_error(
            f"`invariant:` aggregate must be `sum` or `count`; got `{fn_tok.value}`.",
            self.file, fn_tok.line, fn_tok.column,
        )
    self.expect(TokenType.LPAREN)
    entity = str(self.expect_identifier_or_keyword().value)
    field: str | None = None
    if self.match(TokenType.DOT):
        self.advance()
        field = str(self.expect_identifier_or_keyword().value)
    # `where <predicate>` — reuse the scope condition parser (see _parse_scope_rule).
    self.expect_keyword("where")  # or TokenType.WHERE if tokenised; match _parse_scope_rule
    condition = self._parse_scope_condition()  # the SAME helper _parse_scope_rule uses
    self.expect(TokenType.RPAREN)
    op = self._parse_comparison_op()  # = <= >= < > → CompOp ; reuse conditions.py mapping
    rhs = self._parse_invariant_rhs()  # literal | input.<name>.<field>
    return ir.FlowInvariant(
        agg_fn=agg, entity=entity, field=field,
        filter_predicate=None, anchor_entity=None, anchor_input=None,
        op=op, rhs=rhs,
    )
```

Implement `_parse_invariant_rhs()` to read either a numeric literal (`NUMBER`) → `InvariantRhs(literal=...)`, or `input` `.` `<name>` `.` `<field>` → `InvariantRhs(anchor_input=name, anchor_field=field)`. (`_parse_scope_condition`, `_parse_comparison_op`, `expect_keyword` may need thin wrappers around the existing `conditions.py` helpers — name them to match what `_parse_scope_rule` already calls; do not duplicate the condition grammar.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_atomic_flow_parser.py -k invariant -v`
Expected: PASS. Also add `test_invariant_invalid_aggregate_errors` (`avg(...)` → `pytest.raises(ParseError, match="sum.*count")`).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/ tests/unit/test_atomic_flow_parser.py
git commit -m "#1318 slice 1: parse `invariant:` on the atomic block"
```

### Task 3: Regenerate the ir-types api-surface baseline

- [ ] **Step 1:** Run `python -c "from dazzle.api_surface import ir_types as m; print(m.diff_against_baseline())"` — confirm the diff shows only the new `FlowInvariant`/`InvariantRhs`/`FlowAggregateFn` + `AtomicFlowSpec.invariants`.
- [ ] **Step 2:** `dazzle inspect api ir-types --write`
- [ ] **Step 3:** `pytest tests/unit/test_api_surface_drift.py -q` — Expected: PASS.
- [ ] **Step 4: Commit**

```bash
git add docs/api-surface/ir-types.txt
git commit -m "#1318 slice 1: regenerate ir-types baseline for FlowInvariant"
```

---

## Slice 2 — linker resolution + validator

### Task 4: Resolve filter → predicate + derive the anchor (linker)

**Files:**
- Modify: `src/dazzle/core/linker.py`
- Test: `tests/unit/test_atomic_flow_invariants.py`

The linker compiles each raw invariant's `where` condition into a `ScopePredicate` (reuse `build_scope_predicate`, the same call `_compile_scope_predicates` uses for entity scopes, rooting the path at the invariant's `entity`), and derives the anchor: scan the filter for an equality `<fk_field> = input.<name>` where `<fk_field>` is an FK on `entity` (use `fk_graph.resolve_segment`); set `anchor_entity` = the FK target, `anchor_input` = `<name>`. Leave both `None` if no such term (validator rejects).

- [ ] **Step 1: Write the failing test** (build a linked appspec via `parse_modules` + `build_appspec`, mirroring `tests/unit/test_scope_create_link_time.py`):

```python
def test_linker_resolves_invariant_predicate_and_anchor():
    appspec = _link("""
atomic post "Post":
  permit:
    execute: role(admin)
  input txn: ref Transaction required
  create Posting:
    transaction: input.txn
    amount: 0
  invariant: sum(Posting.amount where transaction = input.txn) = 0
""")
    inv = appspec.atomic_flows[0].invariants[0]
    assert inv.filter_predicate is not None          # compiled
    assert inv.anchor_entity == "Transaction"        # derived FK target
    assert inv.anchor_input == "txn"
```

(`_link` + `_BASE` declaring `Transaction` and `Posting(transaction: ref Transaction, amount: int)` — copy the harness from `test_atomic_derived_order_1315.py`.)

- [ ] **Step 2: Run** → FAIL (`filter_predicate is None`).
- [ ] **Step 3:** Add `_resolve_flow_invariants(atomic_flows, fk_graph)` in `linker.py`, called right after `_derive_atomic_step_orders` (both consume `fk_graph`); reassign `atomic_flows`. For each invariant: compile the condition; derive the anchor; `model_copy(update=...)`. Implement `_derive_invariant_anchor(predicate, entity, fk_graph) -> tuple[str|None, str|None]` walking the predicate for a `ColumnCheck`/`UserAttrCheck`-shaped `fk = input.<name>` term (the parser must record input-ref RHS in the condition; if the scope-condition grammar can't carry `input.<name>`, record the anchor term in the raw `FlowInvariant` at parse time instead and resolve here).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `"#1318 slice 2: linker compiles invariant filter + derives anchor"`.

### Task 5: Validate flow invariants

**Files:**
- Modify: `src/dazzle/core/validator.py` (`validate_atomic_flows`)
- Test: `tests/unit/test_atomic_flow_invariants.py`

Checks (each its own `errors.append`): (a) `entity` exists; (b) `sum` has a `field` and it exists + is numeric; `count` has no field; (c) the anchor is non-`None` (else "unanchored aggregate invariant — no lockable anchor row; see ADR-0031"); (d) RHS `anchor_input`/`anchor_field` resolve to a flow input + a field on that input's entity, numeric; (e) the filter predicate is probe-able (no unsupported shape).

- [ ] **Step 1:** Write `test_unanchored_invariant_errors` (a `where` with only a literal column compare, no `= input.X`) → expect an error matching `"unanchored"`. Write `test_sum_requires_numeric_field`.
- [ ] **Step 2: Run** → FAIL (no errors raised).
- [ ] **Step 3:** Implement the checks in `validate_atomic_flows`, iterating `flow.invariants` after the step loop.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `"#1318 slice 2: validate flow invariants (reject unanchored / bad field / bad RHS)"`.

---

## Slice 3 — runtime enforcement (the core)

### Task 6: Aggregate-SQL builder (pure, unit-tested)

**Files:**
- Create: `src/dazzle/http/runtime/atomic_flow_invariants.py`
- Test: `tests/unit/test_atomic_flow_invariants.py`

- [ ] **Step 1: Write the failing test** (pure SQL assembly, no DB):

```python
def test_build_invariant_sql_sum():
    from dazzle.http.runtime.atomic_flow_invariants import build_invariant_sql
    # Given a compiled filter SQL fragment + params, assemble the aggregate query.
    sql, _params = build_invariant_sql(
        agg_fn="sum", entity="Posting", field="amount",
        where_sql='"transaction_id" = %s', where_params=["txn-1"],
    )
    assert sql == 'SELECT COALESCE(SUM("amount"), 0) FROM "Posting" WHERE "transaction_id" = %s'
```

- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3:** Implement `build_invariant_sql(...)` using `quote_identifier`; `SUM` wrapped in `COALESCE(..., 0)` (empty set → 0, not NULL); `COUNT` → `COUNT(*)`. Return `(sql, where_params)`.
- [ ] **Step 4: Run** → PASS. Add `test_build_invariant_sql_count` (`SELECT COUNT(*) FROM "Approver" WHERE ...`).
- [ ] **Step 5: Commit** `"#1318 slice 3: aggregate-SQL builder"`.

### Task 7: `enforce_flow_invariants` — lock, query, compare

**Files:**
- Modify: `src/dazzle/http/runtime/atomic_flow_invariants.py`
- Modify: `src/dazzle/http/runtime/atomic_flow_executor.py`
- Test: `tests/integration/test_scope_runtime_pg.py`

`enforce_flow_invariants(conn, flow, inputs, fk_graph)`: for each invariant, in deterministic order — (1) `SELECT "id" FROM "<anchor_entity>" WHERE "id" = %s FOR UPDATE` with `inputs[anchor_input]` (reuse the single-row-lock shape from `_acquire_scope_parent_share_locks`; FOR UPDATE, not FOR SHARE — we're gating writes to the set); (2) compile the filter via `compile_predicate` + resolve params from `inputs`; (3) run `build_invariant_sql`; (4) resolve the RHS (literal, or `SELECT "<field>" FROM "<input entity>" WHERE id=%s` for an anchor-field); (5) compare with the `CompOp`; (6) on failure raise `AtomicFlowError(flow.name, f"invariant violated: {agg}({entity}…) {op} {rhs}")`. Called in `execute_atomic_flow` inside the `with conn` block, **after** the step loop, **before** the block exits (alongside the #1317 strict-audit write — invariants first so a violation rolls back the audit too).

- [ ] **Step 1: Write the failing real-PG test** in `test_scope_runtime_pg.py` (add a `balanced_post` flow to `fixtures/scope_runtime` with `invariant: sum(Posting.amount where transaction = input.txn) = 0`, two postings +5/−5):

```python
async def test_invariant_balanced_commits(app):
    resp = await _csrf_post(await app.client_as("admin"),
        "/api/atomic/balanced_post", {"txn": app.txn_id, "a": 5, "b": -5})
    assert resp.status_code < 400, resp.text[:300]

async def test_invariant_unbalanced_rolls_back(app):
    resp = await _csrf_post(await app.client_as("admin"),
        "/api/atomic/balanced_post", {"txn": app.txn_id, "a": 5, "b": -4})
    assert resp.status_code == 400          # AtomicFlowError → 400
    # nothing persisted
    with psycopg.connect(app._db_url) as c:
        cur = c.cursor()
        cur.execute('SELECT count(*) FROM "Posting" WHERE "transaction_id" = %s', [app.txn_id])
        assert cur.fetchone()[0] == 0
```

- [ ] **Step 2: Run** (local PG: `createdb dazzle_inv_test; TEST_DATABASE_URL=postgresql://$USER@localhost:5432/dazzle_inv_test pytest tests/integration/test_scope_runtime_pg.py -k invariant -m postgres -v`) → FAIL (no enforcement; unbalanced commits).
- [ ] **Step 3:** Implement `enforce_flow_invariants` + wire it into `execute_atomic_flow`.
- [ ] **Step 4: Run** → PASS (balanced commits; unbalanced 400 + 0 rows).
- [ ] **Step 5: Commit** `"#1318 slice 3: enforce flow invariants in-transaction (anchor FOR UPDATE + aggregate + compare)"`.

### Task 8: Concurrency test (anchor lock soundness)

**Files:** `tests/integration/test_scope_runtime_pg.py`

- [ ] **Step 1:** Write `test_invariant_anchor_lock_serializes` mirroring `tests/integration/test_scope_parent_lock_pg.py`: open conn A, run the flow's anchor `SELECT … FOR UPDATE` on the txn row (or start an unbalanced-making UPDATE) and hold; in a worker thread fire a second flow on the same `txn`; assert it BLOCKS (does not complete within ~2s); release A; assert it proceeds. Proves two flows on the same anchor serialize.
- [ ] **Step 2: Run** → PASS against local PG.
- [ ] **Step 3: Commit** `"#1318 slice 3: anchor-lock concurrency regression test"`.

---

## Slice 4 — analysis surface (ADR-0029 invariant 8)

### Task 9: Project invariants into the RBAC matrix

**Files:**
- Modify: `src/dazzle/rbac/matrix.py` (extend `AtomicFlowProjection` from #1314 or add an `invariants` field to its serialization)
- Test: `tests/unit/test_rbac_matrix.py`

- [ ] **Step 1:** Write `test_matrix_surfaces_flow_invariants` — a flow with an invariant appears in `AccessMatrix.to_json()["atomic_flows"][0]["invariants"]` as `["sum(Posting.amount) = 0"]` (a human string).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3:** Add `invariants: tuple[str, ...]` to `AtomicFlowProjection` and render each `FlowInvariant` to a stable string in `generate_access_matrix`; include in `to_json()` + the `to_table()` "Atomic flows" section.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `"#1318 slice 4: surface flow invariants in the RBAC matrix (analyzability, ADR-0029 inv 8)"`.

---

## Ship (after all slices)

- [ ] `ruff check src/ tests/ --fix && ruff format src/ tests/`
- [ ] `mypy src/dazzle` — clean.
- [ ] `pytest tests/ -m "not e2e"` — green (the required pre-ship gate; per project memory, not just `tests/unit/`).
- [ ] Real-PG: `TEST_DATABASE_URL=… pytest tests/integration/test_scope_runtime_pg.py -m postgres` — green.
- [ ] `dazzle validate` in `fixtures/scope_runtime` — clean.
- [ ] CHANGELOG entry under `### Added` + an `### Agent Guidance` bullet (how to use `invariant:`); flip nothing in ADR-0031 (already Accepted).
- [ ] `/bump patch`, commit, push, monitor CI (PostgreSQL job runs the real-PG tests), close #1318.
- [ ] Independent adversarial review at the Slice-3 checkpoint (security/concurrency-sensitive): focus on the anchor-lock soundness, the COALESCE/empty-set semantics, RHS resolution, and fail-closed-on-error.

---

## Self-review notes (author)

- **Spec coverage:** construct (Task 1–2), set-via-ADR-0009-filter (Task 4), sum/count + literal/anchor-field RHS (Task 1, 4, 7), in-txn pre-commit fail-closed (Task 7), anchor FOR UPDATE concurrency (Task 7–8), ADR-0015 boundary (doc-only — no ledger code touched), analyzability (Task 9), unanchored rejected at validate time (Task 5). All ADR-0031 v1 requirements map to a task.
- **Known integration risk (call out to the executor):** the scope-condition grammar may not natively carry an `input.<name>` RHS inside a `where`. Task 2/4 note the fallback: record the anchor term explicitly in the raw `FlowInvariant` at parse time and resolve in the linker, rather than forcing it through the scope-condition value grammar. Resolve this the moment Task 2 is implemented — it determines the parser shape.
- **Deferred (not in this plan, per ADR-0031):** min/max/avg, expression RHS, unanchored/global aggregates, cross-entity aggregates.
