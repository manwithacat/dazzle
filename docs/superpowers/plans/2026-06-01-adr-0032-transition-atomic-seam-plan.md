# Lifecycle Transition → Atomic Seam Implementation Plan (ADR-0032, #1319)

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax. Implement task-by-task with a review checkpoint after the executor-seam refactor.

**Goal:** Let a state-machine `on_transition:` declare `invoke <flow>(<bindings>)` to invoke a named `atomic` flow when the transition fires, with explicit input binding from the transitioning row + transition inputs.

**Architecture:** Staged. **Slice A (this plan)** = the *surface*: IR (`InvokeFlowSpec` on the transition) + parser + cross-reference validator + a pure factoring of `execute_atomic_flow` into an `…_on_conn` seam + a state-machine fixture that parses/validates clean. The binding is declared + analyzable but **not yet wired into the live update path**. **Slice B (separate, reviewed plan)** = the hot-path shared-transaction integration (`repository.update` conn-injection, `CRUDService.update` interception, `AuthContext`/`access_specs` threading, real-PG atomicity tests). Slice A touches NO hot path and is independently shippable.

**Tech stack:** Python 3.12, Pydantic IR, `dsl_parser_impl` mixins, pytest. Reuse the #1318 cadence.

**Ground-truth anchors (from the #1319 code exploration):**
- `StateTransition` IR: `src/dazzle/core/ir/state_machine.py:118-135` (has `effects: list[StepEffect]`).
- `StepEffect` / `EffectAction`: `src/dazzle/core/ir/process.py:133-165`.
- on_transition parser: `src/dazzle/core/dsl_parser_impl/entity.py` — `_parse_entity_on_transition_block` (≈836-854), `_parse_transition_effect` (≈2149-2247), `_merge_transition_effects` (≈1019-1027). Existing effect DSL: `on_transition:` → `from -> to:` → nested `create E:` / `update E:` bodies.
- `execute_atomic_flow`: `src/dazzle/http/runtime/atomic_flow_executor.py:378-528` — opens its own `with db_manager.connection() as conn:` at line 448; all inner helpers already take `conn` as a param.
- Flows live in `appspec.atomic_flows` (`AtomicFlowSpec`, with `inputs: list[FlowInput]`).

---

## DSL surface (target)

```dsl
on_transition:
  submitted -> fulfilled:
    invoke fulfil_order(order: self, warehouse: input.warehouse)
```
- `self` → the transitioning entity row (its id).
- `input.<name>` → a transition action input.
- literal → a constant.
- One `invoke` per transition in v1 (ADR-0032 honest limits). May coexist with existing `create`/`update` effects in the same `from -> to:` block.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `src/dazzle/core/ir/state_machine.py` | `InvokeBinding`, `InvokeFlowSpec` types + `StateTransition.invoke_flow: InvokeFlowSpec \| None` | Modify |
| `src/dazzle/core/ir/__init__.py` | export the new public IR names | Modify |
| `src/dazzle/core/dsl_parser_impl/entity.py` | parse `invoke <flow>(<bindings>)` inside an `on_transition:` `from -> to:` block | Modify |
| `src/dazzle/core/validator.py` | validate invoke: flow exists, required flow inputs bound, sources resolve, `self` valid | Modify |
| `src/dazzle/http/runtime/atomic_flow_executor.py` | factor `execute_atomic_flow_on_conn(...)` (accept external conn); `execute_atomic_flow` becomes a thin wrapper | Modify |
| `fixtures/transition_atomic/` (new) | a state-machine entity + `invoke` transition + the referenced `atomic` flow that parses + validates clean | Create |
| `docs/api-surface/ir-types.txt` | regenerated baseline (new IR types) | Regenerate |
| tests | parser, validator, executor-seam, fixture | Create/Modify |

---

## Task 1 — IR: `InvokeFlowSpec` on the transition

**Files:** `src/dazzle/core/ir/state_machine.py`, `src/dazzle/core/ir/__init__.py`, `tests/unit/test_transition_invoke.py` (new).

- [ ] **Step 1 — failing test**
```python
# tests/unit/test_transition_invoke.py
from dazzle.core import ir

def test_invoke_flow_ir():
    b = ir.InvokeBinding(flow_input="order", source_kind=ir.InvokeSourceKind.SELF)
    spec = ir.InvokeFlowSpec(flow_name="fulfil_order", bindings=[b])
    assert spec.flow_name == "fulfil_order"
    assert spec.bindings[0].source_kind == ir.InvokeSourceKind.SELF
```
- [ ] **Step 2 — run, expect FAIL** (`AttributeError: InvokeFlowSpec`).
- [ ] **Step 3 — implement** in `state_machine.py` (frozen pydantic, match the file's existing `StateTransition`/`StepEffect` style):
```python
class InvokeSourceKind(StrEnum):
    SELF = "self"           # the transitioning entity row (its id)
    INPUT = "input"         # input.<name> — a transition action input
    LITERAL = "literal"

class InvokeBinding(BaseModel):
    flow_input: str                       # the atomic-flow input name being bound
    source_kind: InvokeSourceKind
    source_name: str | None = None        # for INPUT: the transition input name
    literal: str | int | float | bool | None = None  # for LITERAL
    model_config = ConfigDict(frozen=True)

class InvokeFlowSpec(BaseModel):
    """A transition effect that invokes a named atomic flow (#1319, ADR-0032)."""
    flow_name: str
    bindings: list[InvokeBinding]
    model_config = ConfigDict(frozen=True)
```
Add `invoke_flow: InvokeFlowSpec | None = None` to `StateTransition`. Export `InvokeSourceKind`, `InvokeBinding`, `InvokeFlowSpec` from `ir/__init__.py` (import block + `__all__`).
- [ ] **Step 4 — run, PASS.**
- [ ] **Step 5 — gates + commit** (ruff + `mypy src/dazzle/core/ir/state_machine.py`; `dazzle inspect api ir-types --write` + include the baseline + `pytest tests/unit/test_api_surface_drift.py -q`). **Stage by path** (never `git add -A`; untracked `docs/adr/0030-*.md` must stay out). `git commit -m "#1319 slice A: InvokeFlowSpec IR (ADR-0032)"`

## Task 2 — Parser: `invoke <flow>(<bindings>)` in `on_transition:`

**Files:** `src/dazzle/core/dsl_parser_impl/entity.py`, `tests/unit/test_transition_invoke.py` (or the entity parser test file).

Study `_parse_transition_effect` (≈2149) — it already dispatches `create`/`update` inside a `from -> to:` block. Add an `invoke` branch (add an `INVOKE` keyword token if absent — check the lexer keyword derivation; mirror how `create`/`update` effect keywords are recognised there). Parse `invoke <ident>(<arg>: <self|input.<name>|literal>, ...)` → an `InvokeFlowSpec`, and set it on the `StateTransition.invoke_flow` (thread it through `_merge_transition_effects` ≈1019 alongside `effects`).

- [ ] **Step 1 — failing test:** parse an entity with
```
on_transition:
  submitted -> fulfilled:
    invoke fulfil_order(order: self, qty: input.qty)
```
assert the transition's `invoke_flow.flow_name == "fulfil_order"`, bindings `[(order, SELF), (qty, INPUT "qty")]`.
- [ ] **Step 2 — run, FAIL.**
- [ ] **Step 3 — implement** the `invoke` parse branch + thread `invoke_flow` onto the `StateTransition`. Bindings: `self` → `InvokeBinding(flow_input=arg, source_kind=SELF)`; `input.<name>` → INPUT + source_name; a number/string literal → LITERAL. Use `make_parse_error` for a malformed binding.
- [ ] **Step 4 — run, PASS** + full parser suite (`pytest tests/unit/test_parser.py tests/unit/test_transition_invoke.py -q`) no regressions.
- [ ] **Step 5 — gates + commit** (stage by path). `"#1319 slice A: parse invoke: on a transition"`

## Task 3 — Validator: cross-reference the invoked flow

**Files:** `src/dazzle/core/validator.py`, test file.

Find where state-machine transitions are validated (grep `StateTransition`/`validate_state_machine` in validator.py; if transitions aren't validated there yet, add a small `validate_transition_invocations(appspec)` and call it from the same place `validate_atomic_flows` is called — `src/dazzle/core/lint.py`). Checks per `invoke_flow`:
1. `flow_name` ∈ `{f.name for f in appspec.atomic_flows}` — else error "...invokes unknown atomic flow '<name>'".
2. every **required** flow input (`AtomicFlowSpec.inputs` where `required`) is bound by some `InvokeBinding.flow_input` — else error "...does not bind required input '<x>'".
3. every binding's `flow_input` is a real input of the flow — else error "...binds unknown input '<x>'".
4. (light) a `SELF` binding targets a flow input that is a `ref <ThisEntity>` (the entity owning the state machine) — warn/err if the ref entity doesn't match. (Keep simple; type-deep checks can be Slice B.)

- [ ] **Step 1 — failing tests:** unknown-flow → error; missing-required-binding → error; valid → no error. Build the appspec via the `_link(...)` parse→link harness (so `appspec.atomic_flows` + entities are populated).
- [ ] **Step 2 — run, FAIL.**
- [ ] **Step 3 — implement.**
- [ ] **Step 4 — run, PASS** (+ no regression to existing validator tests).
- [ ] **Step 5 — gates + commit** (stage by path). `"#1319 slice A: validate transition invoke: cross-references"`

## Task 4 — Executor seam: `execute_atomic_flow_on_conn`

**Files:** `src/dazzle/http/runtime/atomic_flow_executor.py`, `tests/unit/test_atomic_flow_executor.py`.

Pure refactor (Slice B will call the new entry point with a shared connection). Factor the body of `execute_atomic_flow`'s `with db_manager.connection() as conn:` block (lines ≈448-528) into:
```python
def execute_atomic_flow_on_conn(flow, inputs, conn, placeholder, *, auth_context=None, access_specs=None, fk_graph=None, audit_sink=None) -> dict[str, UUID]:
    # everything currently inside the with-block (derived-order, step loop, invariant
    # enforcement, strict-audit write) — but operating on the passed-in conn/placeholder.
    ...
def execute_atomic_flow(flow, inputs, db_manager, *, auth_context=None, access_specs=None, fk_graph=None, audit_sink=None) -> dict[str, UUID]:
    with db_manager.connection() as conn:
        return execute_atomic_flow_on_conn(flow, inputs, conn, db_manager.placeholder,
            auth_context=auth_context, access_specs=access_specs, fk_graph=fk_graph, audit_sink=audit_sink)
```
**Behaviour must be byte-identical** — the existing `test_atomic_flow_executor.py` (MagicMock db) + the real-PG `test_scope_runtime_pg.py` are the regression guard.

- [ ] **Step 1 — add a unit test** asserting `execute_atomic_flow_on_conn` runs the steps on a passed MagicMock `conn` without calling `db_manager.connection()` (i.e. the caller owns the conn). (TDD: write it against the intended signature.)
- [ ] **Step 2 — run, FAIL** (function missing).
- [ ] **Step 3 — do the factoring.**
- [ ] **Step 4 — run** the full `tests/unit/test_atomic_flow_executor.py` + (local PG) `test_scope_runtime_pg.py -m postgres` — all green (no behaviour change).
- [ ] **Step 5 — gates + commit** (stage by path). `"#1319 slice A: factor execute_atomic_flow_on_conn seam (for the transition shared-tx, Slice B)"`
- [ ] **REVIEW CHECKPOINT:** independent review of Task 4 (the refactor must be behaviour-preserving — it's on the atomic hot path) before proceeding.

## Task 5 — Fixture: a state-machine + invoke transition that parses + validates clean

**Files:** `fixtures/transition_atomic/` (dazzle.toml + dsl), `tests/unit/` (a parse+validate test, or extend an examples-lint test).

- [ ] Create a minimal app: an entity with a `status` state-machine field + states + an `on_transition:` `invoke <flow>(...)`, and the referenced `atomic` flow (a single guarded create whose input is `ref <ThisEntity>` bound to `self`). Mirror `fixtures/scope_runtime` layout.
- [ ] **Step — test:** `dazzle validate` on the fixture exits 0; a unit test loads the appspec and asserts the transition's `invoke_flow` is populated + validates clean.
- [ ] **Step — commit** (stage by path). `"#1319 slice A: transition_atomic fixture (invoke: parses + validates)"`

---

## Ship Slice A
- [ ] `ruff check src/ tests/ --fix && ruff format`; `mypy src/dazzle` clean.
- [ ] `pytest tests/ -m "not e2e"` green (the required gate).
- [ ] Local-PG `test_scope_runtime_pg.py -m postgres` green (executor seam regression).
- [ ] CHANGELOG `### Added` (the `invoke:` surface is declared + validated; runtime wiring = Slice B) + `### Agent Guidance`.
- [ ] `/bump patch`, commit, branch→main (ff-merge), push, tag, CI, comment on #1319 (Slice A landed; Slice B = hot-path integration, tracked), leave #1319 **open**.

## Slice B outline (separate plan, reviewed)
Hot-path shared-tx: add `conn=` injection to `repository.update`; intercept in `CRUDService.update` (open one conn, status-write + `execute_atomic_flow_on_conn` on it, commit/rollback together); thread `AuthContext` through `route_generator._core` → `service.update`; plumb `access_specs`/`fk_graph` onto the service at wiring; real-PG atomicity tests (transition+effect commit together; flow scope-denial rolls the transition back; no-user transition invoking a guarded flow → validate-time error). Adversarial review of the hot-path change required.

## Self-review (author)
- Slice A is surface-only: no `repository`/`CRUDService`/auth changes, no real-PG atomicity claim (that's Slice B). The executor factoring (Task 4) is the one hot-path-adjacent change and is behaviour-preserving (guarded by existing tests + a review checkpoint).
- Deferred to Slice B / ADR honest-limits: shared-tx wiring, principal threading + no-user validate-time rejection, multiple invokes per transition, re-entrancy bounds.
