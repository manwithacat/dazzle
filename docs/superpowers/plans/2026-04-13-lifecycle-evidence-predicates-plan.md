# Lifecycle Evidence Predicates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Dazzle's DSL to support lifecycle **evidence predicates** and **progress ordering** on entity state machines, unblocking `progress_evaluator.py` in the fitness methodology.

**Architecture:** Dazzle currently models entity lifecycles as enum fields (e.g., `status: enum[new, assigned, resolved]`) with transitions handled by backend mutation endpoints and scope/permit rules. There is NO dedicated lifecycle DSL construct today — the `ProcessSpec` in `src/dazzle/core/ir/process.py` is workflow-oriented (triggers, sagas, compensations), not entity-state-machine-oriented. This plan adds a new lightweight `lifecycle` DSL construct per entity with ordered states and per-transition evidence predicates.

**Tech Stack:** Python 3.12, Pydantic v2 for IR models, pytest, existing scope-rule predicate parser.

**Reference:** `docs/adr/ADR-0020-lifecycle-evidence-predicates.md` — the authoritative design. Also: the fitness methodology spec `docs/superpowers/specs/2026-04-13-agent-led-fitness-methodology-design.md` §6.1 for consumer requirements.

---

## File Structure

**Files to create:**
- `src/dazzle/core/ir/lifecycle.py` — new IR module for `LifecycleSpec`, `LifecycleStateSpec`, `LifecycleTransitionSpec`
- `src/dazzle/core/dsl_parser_impl/lifecycle.py` — parser mixin that reads `lifecycle:` blocks inside entity declarations
- `tests/unit/test_lifecycle_ir.py` — IR model unit tests
- `tests/unit/test_lifecycle_parser.py` — parser unit tests
- `tests/unit/test_lifecycle_validation.py` — validator unit tests

**Files to modify:**
- `src/dazzle/core/ir/entity.py` (or wherever `EntitySpec` lives) — add `lifecycle: LifecycleSpec | None` field
- `src/dazzle/core/ir/__init__.py` — export `LifecycleSpec`, etc.
- `src/dazzle/core/dsl_parser_impl/entity.py` — wire the lifecycle parser into the entity parser loop
- `src/dazzle/core/validator.py` — add lifecycle invariants (state order is total, evidence predicates parse, transitions reference declared states)
- `docs/reference/grammar.md` — add lifecycle syntax section
- `examples/support_tickets/app/*.dsl` (wherever ticket entity is declared) — add lifecycle block for tickets
- `examples/simple_task/app/*.dsl` — add lifecycle block for tasks (if they have state)
- `CHANGELOG.md` — add entry under `## [Unreleased]` → `### Added`

**Discovery task before implementation (Task 0):** the implementing agent MUST scout the actual entity parser location because the Dazzle codebase has grown and file layout may have shifted. Use `grep -rn "EntitySpec\|entity_parser" src/dazzle/` and `find src/dazzle -name "entity.py"` to confirm paths.

---

## Task 0: Discovery

**Files to read (no changes):**
- `src/dazzle/core/ir/__init__.py` (to find the entity model exports)
- `src/dazzle/core/ir/` — locate entity IR
- `src/dazzle/core/dsl_parser_impl/entity.py` — understand how fields/enums are parsed today
- `src/dazzle/core/validator.py` — understand existing validation pipeline
- `src/dazzle/core/dsl_parser_impl/conditions.py` — understand the existing predicate algebra parser (scope rules use it; lifecycle will reuse)
- `examples/support_tickets/app/` — see how the Ticket entity currently declares its status enum

- [ ] **Step 1: Scout entity IR**

Run: `grep -rn "class EntitySpec\|class FieldSpec" src/dazzle/core/ir/`
Expected: find the `EntitySpec` Pydantic model and its field list.

- [ ] **Step 2: Scout entity parser**

Run: `grep -n "def parse_entity\|^def parse\|^class" src/dazzle/core/dsl_parser_impl/entity.py`
Expected: identify the entry point the entity parser uses when it encounters a child block like `lifecycle:`.

- [ ] **Step 3: Scout predicate parser**

Run: `grep -n "def parse_condition\|def parse_predicate" src/dazzle/core/dsl_parser_impl/conditions.py`
Expected: identify the function that parses boolean expressions over entity fields (used by scope rules). This is the function the lifecycle parser will reuse for `evidence` expressions.

- [ ] **Step 4: Read an example entity**

Read `examples/support_tickets/app/` DSL files until you find the Ticket entity declaration. Note:
- What enum is the status field? (e.g., `status: enum[new, assigned, resolved, closed]`)
- Are there existing scope rules referencing status values?
- Are there existing transition endpoints (backend code that moves tickets between states)?

Output: a short internal note (not a commit) summarising the existing state-machine pattern. This informs Task 2's IR design.

---

## Task 1: LifecycleSpec IR models

**Files:**
- Create: `src/dazzle/core/ir/lifecycle.py`
- Create: `tests/unit/test_lifecycle_ir.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_lifecycle_ir.py
"""Unit tests for LifecycleSpec, LifecycleStateSpec, LifecycleTransitionSpec."""
import pytest
from pydantic import ValidationError

from dazzle.core.ir.lifecycle import (
    LifecycleSpec,
    LifecycleStateSpec,
    LifecycleTransitionSpec,
)


def test_state_spec_requires_name_and_order():
    state = LifecycleStateSpec(name="new", order=0)
    assert state.name == "new"
    assert state.order == 0


def test_state_spec_order_must_be_non_negative():
    with pytest.raises(ValidationError):
        LifecycleStateSpec(name="new", order=-1)


def test_transition_spec_basic():
    t = LifecycleTransitionSpec(
        from_state="new",
        to_state="assigned",
        evidence=None,
        roles=["support_agent"],
    )
    assert t.from_state == "new"
    assert t.to_state == "assigned"
    assert t.evidence is None


def test_transition_spec_with_evidence():
    t = LifecycleTransitionSpec(
        from_state="in_progress",
        to_state="resolved",
        evidence="resolution_notes != null",
        roles=["support_agent"],
    )
    assert t.evidence == "resolution_notes != null"


def test_lifecycle_spec_basic():
    lc = LifecycleSpec(
        status_field="status",
        states=[
            LifecycleStateSpec(name="new", order=0),
            LifecycleStateSpec(name="resolved", order=1),
        ],
        transitions=[
            LifecycleTransitionSpec(
                from_state="new",
                to_state="resolved",
                evidence=None,
                roles=["any"],
            ),
        ],
    )
    assert lc.status_field == "status"
    assert len(lc.states) == 2


def test_lifecycle_states_are_frozen():
    lc = LifecycleSpec(
        status_field="status",
        states=[LifecycleStateSpec(name="new", order=0)],
        transitions=[],
    )
    with pytest.raises(ValidationError):
        lc.status_field = "other"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_lifecycle_ir.py -v`
Expected: ImportError — `dazzle.core.ir.lifecycle` module does not exist yet.

- [ ] **Step 3: Create the IR module**

```python
# src/dazzle/core/ir/lifecycle.py
"""IR models for entity lifecycle declarations (ADR-0020).

Supports the fitness methodology's progress_evaluator by providing:
- Ordered states (progress direction is well-defined)
- Evidence predicates per transition (distinguishes motion from work)
"""

from pydantic import BaseModel, ConfigDict, Field


class LifecycleStateSpec(BaseModel):
    """One named state in an entity lifecycle, with a progress order."""

    name: str = Field(..., description="State name (matches an enum value on the entity)")
    order: int = Field(..., ge=0, description="Progress order (0 = earliest)")

    model_config = ConfigDict(frozen=True)


class LifecycleTransitionSpec(BaseModel):
    """One allowed transition in an entity lifecycle."""

    from_state: str = Field(..., description="Source state name")
    to_state: str = Field(..., description="Destination state name")
    evidence: str | None = Field(
        default=None,
        description=(
            "Boolean predicate over entity fields that must hold for this transition "
            "to count as valid progress. Uses the scope-rule predicate algebra syntax. "
            "When None, the transition is always valid (no evidence required)."
        ),
    )
    roles: list[str] = Field(
        default_factory=list,
        description="Persona roles authorized to perform this transition",
    )

    model_config = ConfigDict(frozen=True)


class LifecycleSpec(BaseModel):
    """Entity lifecycle declaration (ADR-0020).

    Attached to an EntitySpec via its `lifecycle` field. Consumed by the
    fitness methodology's progress_evaluator to distinguish motion from work.
    """

    status_field: str = Field(
        ...,
        description="Name of the entity's enum field that holds the current state",
    )
    states: list[LifecycleStateSpec] = Field(
        ...,
        min_length=1,
        description="Ordered states. `order` values must form a total order.",
    )
    transitions: list[LifecycleTransitionSpec] = Field(
        default_factory=list,
        description="Allowed transitions between states",
    )

    model_config = ConfigDict(frozen=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_lifecycle_ir.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/ir/lifecycle.py tests/unit/test_lifecycle_ir.py
git commit -m "feat(ir): add LifecycleSpec IR models for ADR-0020"
```

---

## Task 2: Wire LifecycleSpec into EntitySpec

**Files:**
- Modify: `src/dazzle/core/ir/entity.py` (discover exact path in Task 0)
- Modify: `src/dazzle/core/ir/__init__.py`

- [ ] **Step 1: Add optional `lifecycle` field to EntitySpec**

Add this field to the EntitySpec Pydantic model (after existing fields, before `model_config`):

```python
from dazzle.core.ir.lifecycle import LifecycleSpec

# ... within EntitySpec class:
lifecycle: LifecycleSpec | None = Field(
    default=None,
    description="Lifecycle declaration (ADR-0020): ordered states + evidence predicates",
)
```

- [ ] **Step 2: Export from package __init__**

Add to `src/dazzle/core/ir/__init__.py`:

```python
from dazzle.core.ir.lifecycle import (
    LifecycleSpec,
    LifecycleStateSpec,
    LifecycleTransitionSpec,
)

__all__ = [
    # ... existing exports ...
    "LifecycleSpec",
    "LifecycleStateSpec",
    "LifecycleTransitionSpec",
]
```

- [ ] **Step 3: Write a test that EntitySpec accepts a lifecycle**

Add to `tests/unit/test_lifecycle_ir.py`:

```python
from dazzle.core.ir import EntitySpec  # or the correct import path from Task 0


def test_entity_spec_accepts_lifecycle():
    lc = LifecycleSpec(
        status_field="status",
        states=[LifecycleStateSpec(name="draft", order=0), LifecycleStateSpec(name="published", order=1)],
        transitions=[LifecycleTransitionSpec(from_state="draft", to_state="published", roles=["author"])],
    )
    # NOTE: adjust EntitySpec(...) kwargs to match the actual constructor
    entity = EntitySpec(
        name="Article",
        title="Article",
        fields=[],  # adjust to minimum-valid field list
        lifecycle=lc,
    )
    assert entity.lifecycle is not None
    assert entity.lifecycle.status_field == "status"


def test_entity_spec_lifecycle_optional():
    entity = EntitySpec(name="Article", title="Article", fields=[])  # no lifecycle
    assert entity.lifecycle is None
```

- [ ] **Step 4: Run tests to verify both pass**

Run: `pytest tests/unit/test_lifecycle_ir.py::test_entity_spec_accepts_lifecycle tests/unit/test_lifecycle_ir.py::test_entity_spec_lifecycle_optional -v`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/ir/entity.py src/dazzle/core/ir/__init__.py tests/unit/test_lifecycle_ir.py
git commit -m "feat(ir): wire LifecycleSpec into EntitySpec"
```

---

## Task 3: Parser — recognise `lifecycle:` block inside entity

**Files:**
- Create: `src/dazzle/core/dsl_parser_impl/lifecycle.py`
- Modify: `src/dazzle/core/dsl_parser_impl/entity.py`
- Create: `tests/unit/test_lifecycle_parser.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_lifecycle_parser.py
"""Parser tests for the lifecycle: block inside an entity declaration."""

from dazzle.core.dsl_parser import parse_dsl  # adjust path if different


LIFECYCLE_DSL = """
module test_app
app test "Test"

entity Ticket "Support Ticket":
  id: uuid pk
  status: enum[new, assigned, in_progress, resolved, closed] required

  lifecycle:
    status_field: status
    states:
      - new         (order: 0)
      - assigned    (order: 1)
      - in_progress (order: 2)
      - resolved    (order: 3)
      - closed      (order: 4)
    transitions:
      - from: new
        to: assigned
        evidence: assignee_id != null
        role: support_agent
      - from: in_progress
        to: resolved
        evidence: resolution_notes != null
        role: support_agent
"""


def test_parse_lifecycle_block():
    spec = parse_dsl(LIFECYCLE_DSL)
    entity = spec.entities["Ticket"]
    assert entity.lifecycle is not None
    assert entity.lifecycle.status_field == "status"
    assert len(entity.lifecycle.states) == 5
    assert entity.lifecycle.states[0].name == "new"
    assert entity.lifecycle.states[0].order == 0
    assert entity.lifecycle.states[4].name == "closed"
    assert entity.lifecycle.states[4].order == 4


def test_parse_transitions():
    spec = parse_dsl(LIFECYCLE_DSL)
    entity = spec.entities["Ticket"]
    transitions = entity.lifecycle.transitions
    assert len(transitions) == 2

    t0 = transitions[0]
    assert t0.from_state == "new"
    assert t0.to_state == "assigned"
    assert t0.evidence == "assignee_id != null"
    assert "support_agent" in t0.roles


def test_parse_entity_without_lifecycle():
    minimal = """
    module test_app
    app test "Test"

    entity Note "Note":
      id: uuid pk
      body: text
    """
    spec = parse_dsl(minimal)
    entity = spec.entities["Note"]
    assert entity.lifecycle is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_lifecycle_parser.py -v`
Expected: tests FAIL — the parser doesn't yet recognise the `lifecycle:` block.

- [ ] **Step 3: Implement the lifecycle parser**

Create `src/dazzle/core/dsl_parser_impl/lifecycle.py`:

```python
"""Parser for the `lifecycle:` block inside an entity declaration (ADR-0020)."""

from dazzle.core.ir.lifecycle import (
    LifecycleSpec,
    LifecycleStateSpec,
    LifecycleTransitionSpec,
)
from dazzle.core.dsl_parser_impl.base import ParseError


def parse_lifecycle_block(block_source: str, entity_name: str) -> LifecycleSpec:
    """Parse a `lifecycle:` block's body into a LifecycleSpec.

    Expected shape:

        lifecycle:
          status_field: <field_name>
          states:
            - <state_name> (order: <int>)
            - ...
          transitions:
            - from: <state_name>
              to: <state_name>
              evidence: <boolean_predicate>  # optional
              role: <role_name>              # optional, can be repeated

    See ADR-0020 for the full grammar and semantic rules.
    """
    # Implementation: walk the block line-by-line or token-by-token
    # NOTE: adjust to match the actual parser style used by other blocks
    # (e.g., entity.py's field parser). Follow the existing pattern.

    lines = [line for line in block_source.splitlines() if line.strip()]
    state_specs: list[LifecycleStateSpec] = []
    transition_specs: list[LifecycleTransitionSpec] = []
    status_field: str | None = None

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("status_field:"):
            status_field = line.split(":", 1)[1].strip()
            i += 1
            continue

        if line == "states:":
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith("-"):
                state_line = lines[i].lstrip()[1:].strip()
                # "new (order: 0)" → name="new", order=0
                if "(" in state_line and ")" in state_line:
                    name_part, meta_part = state_line.split("(", 1)
                    name = name_part.strip()
                    meta = meta_part.rstrip(")").strip()
                    # meta: "order: 0"
                    order_key, order_val = meta.split(":", 1)
                    if order_key.strip() != "order":
                        raise ParseError(
                            f"entity {entity_name}: lifecycle state metadata must be `(order: N)`, "
                            f"got `{meta}`"
                        )
                    order = int(order_val.strip())
                else:
                    raise ParseError(
                        f"entity {entity_name}: lifecycle state `{state_line}` missing `(order: N)`"
                    )
                state_specs.append(LifecycleStateSpec(name=name, order=order))
                i += 1
            continue

        if line == "transitions:":
            i += 1
            current: dict = {}
            while i < len(lines):
                tl = lines[i].lstrip()
                if tl.startswith("-"):
                    # start of a new transition
                    if current:
                        transition_specs.append(_finalize_transition(current, entity_name))
                    current = {"from": None, "to": None, "evidence": None, "roles": []}
                    tl = tl[1:].strip()
                    if tl:
                        _apply_transition_kv(current, tl, entity_name)
                    i += 1
                elif ":" in tl and not tl.startswith("-"):
                    _apply_transition_kv(current, tl, entity_name)
                    i += 1
                else:
                    break
            if current:
                transition_specs.append(_finalize_transition(current, entity_name))
            continue

        raise ParseError(
            f"entity {entity_name}: unexpected line in lifecycle block: `{line}`"
        )

    if not status_field:
        raise ParseError(
            f"entity {entity_name}: lifecycle block missing `status_field`"
        )
    if not state_specs:
        raise ParseError(
            f"entity {entity_name}: lifecycle block missing `states`"
        )

    return LifecycleSpec(
        status_field=status_field,
        states=state_specs,
        transitions=transition_specs,
    )


def _apply_transition_kv(current: dict, line: str, entity_name: str) -> None:
    """Apply one key:value line to the current transition dict."""
    key, val = line.split(":", 1)
    key = key.strip()
    val = val.strip()
    if key == "from":
        current["from"] = val
    elif key == "to":
        current["to"] = val
    elif key == "evidence":
        current["evidence"] = val
    elif key == "role":
        current["roles"].append(val)
    else:
        raise ParseError(
            f"entity {entity_name}: unknown transition key `{key}`"
        )


def _finalize_transition(current: dict, entity_name: str) -> LifecycleTransitionSpec:
    if not current["from"] or not current["to"]:
        raise ParseError(
            f"entity {entity_name}: transition missing `from` or `to`"
        )
    return LifecycleTransitionSpec(
        from_state=current["from"],
        to_state=current["to"],
        evidence=current["evidence"],
        roles=current["roles"],
    )
```

**NOTE:** The exact line-parsing style should match the rest of `src/dazzle/core/dsl_parser_impl/`. If the existing parser uses a Lark grammar or PEG, the implementer should integrate with it instead of line-walking.

- [ ] **Step 4: Wire into entity parser**

In `src/dazzle/core/dsl_parser_impl/entity.py`, find where the entity parser walks child blocks (scope, permit, stories, etc.) and add a branch for `lifecycle:`:

```python
from dazzle.core.dsl_parser_impl.lifecycle import parse_lifecycle_block

# ... within the entity block-dispatch loop:
elif block_name == "lifecycle":
    entity.lifecycle = parse_lifecycle_block(block_body, entity.name)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_lifecycle_parser.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/lifecycle.py src/dazzle/core/dsl_parser_impl/entity.py tests/unit/test_lifecycle_parser.py
git commit -m "feat(parser): accept lifecycle: blocks inside entity declarations"
```

---

## Task 4: Validation — enforce lifecycle invariants

**Files:**
- Modify: `src/dazzle/core/validator.py`
- Create: `tests/unit/test_lifecycle_validation.py`

- [ ] **Step 1: Write failing tests for invariants**

```python
# tests/unit/test_lifecycle_validation.py
"""Validation tests for lifecycle declarations."""

import pytest
from dazzle.core.dsl_parser import parse_dsl
from dazzle.core.validator import ValidationError, validate_appspec


VALID = """
module t
app t "T"

entity Ticket "Ticket":
  id: uuid pk
  status: enum[new, resolved] required
  lifecycle:
    status_field: status
    states:
      - new (order: 0)
      - resolved (order: 1)
    transitions:
      - from: new
        to: resolved
"""


def test_valid_lifecycle_passes():
    spec = parse_dsl(VALID)
    validate_appspec(spec)  # no exception


def test_status_field_must_exist_on_entity():
    bad = VALID.replace("status_field: status", "status_field: nonexistent")
    spec = parse_dsl(bad)
    with pytest.raises(ValidationError, match="status_field `nonexistent` not found"):
        validate_appspec(spec)


def test_state_must_match_enum_value():
    bad = VALID.replace("- new (order: 0)\n      - resolved (order: 1)",
                        "- new (order: 0)\n      - notreal (order: 1)")
    spec = parse_dsl(bad)
    with pytest.raises(ValidationError, match="state `notreal`"):
        validate_appspec(spec)


def test_state_order_must_be_unique():
    bad = VALID.replace("- resolved (order: 1)", "- resolved (order: 0)")
    spec = parse_dsl(bad)
    with pytest.raises(ValidationError, match="duplicate order"):
        validate_appspec(spec)


def test_transition_states_must_be_declared():
    bad = VALID.replace("from: new\n        to: resolved",
                        "from: draft\n        to: published")
    spec = parse_dsl(bad)
    with pytest.raises(ValidationError, match="transition references unknown state"):
        validate_appspec(spec)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_lifecycle_validation.py -v`
Expected: tests FAIL because the validator doesn't yet check lifecycle invariants.

- [ ] **Step 3: Add lifecycle invariants to the validator**

In `src/dazzle/core/validator.py`, add a validation function and call it from the main entity-validation loop:

```python
def _validate_lifecycle(entity: EntitySpec) -> list[ValidationError]:
    """Check lifecycle declaration invariants (ADR-0020)."""
    errors: list[ValidationError] = []
    lc = entity.lifecycle
    if lc is None:
        return errors

    # 1. status_field must exist on the entity AND be an enum
    status_field = next(
        (f for f in entity.fields if f.name == lc.status_field),
        None,
    )
    if status_field is None:
        errors.append(
            ValidationError(
                f"entity `{entity.name}`: lifecycle status_field "
                f"`{lc.status_field}` not found on entity"
            )
        )
        return errors

    if status_field.type != "enum":
        errors.append(
            ValidationError(
                f"entity `{entity.name}`: lifecycle status_field "
                f"`{lc.status_field}` is not an enum field"
            )
        )
        return errors

    enum_values = set(status_field.enum_values or [])

    # 2. every declared state must match an enum value
    for state in lc.states:
        if state.name not in enum_values:
            errors.append(
                ValidationError(
                    f"entity `{entity.name}`: lifecycle state `{state.name}` "
                    f"is not a value of enum field `{lc.status_field}` "
                    f"(valid values: {sorted(enum_values)})"
                )
            )

    # 3. orders must be unique
    orders = [s.order for s in lc.states]
    if len(orders) != len(set(orders)):
        duplicates = sorted({o for o in orders if orders.count(o) > 1})
        errors.append(
            ValidationError(
                f"entity `{entity.name}`: lifecycle states have duplicate order values: {duplicates}"
            )
        )

    # 4. transitions must reference declared states
    state_names = {s.name for s in lc.states}
    for t in lc.transitions:
        if t.from_state not in state_names:
            errors.append(
                ValidationError(
                    f"entity `{entity.name}`: transition references unknown state "
                    f"`{t.from_state}` (from)"
                )
            )
        if t.to_state not in state_names:
            errors.append(
                ValidationError(
                    f"entity `{entity.name}`: transition references unknown state "
                    f"`{t.to_state}` (to)"
                )
            )

    # 5. evidence predicates should parse — reuse the scope-rule parser
    # NOTE: defer strict predicate parsing to a later step; for now accept any string.
    # A future task will plug the existing predicate parser in.

    return errors


# ... in the main validate_appspec loop:
for entity in appspec.entities.values():
    errors.extend(_validate_lifecycle(entity))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_lifecycle_validation.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/validator.py tests/unit/test_lifecycle_validation.py
git commit -m "feat(validator): enforce lifecycle invariants (ADR-0020)"
```

---

## Task 5: Example app adoption (support_tickets)

**Files:**
- Modify: `examples/support_tickets/app/*.dsl` (find the Ticket entity and add a `lifecycle:` block)

- [ ] **Step 1: Locate the Ticket entity DSL file**

Run: `grep -rn "entity Ticket" examples/support_tickets/`
Read the file to understand the current state enum structure.

- [ ] **Step 2: Add lifecycle block**

Example (adapt to the actual states the example uses):

```dsl
entity Ticket "Support Ticket":
  id: uuid pk
  title: str(200) required
  status: enum[new, assigned, in_progress, resolved, closed] required
  assignee_id: ref User
  resolution_notes: text

  lifecycle:
    status_field: status
    states:
      - new         (order: 0)
      - assigned    (order: 1)
      - in_progress (order: 2)
      - resolved    (order: 3)
      - closed      (order: 4)
    transitions:
      - from: new
        to: assigned
        evidence: assignee_id != null
        role: support_agent
      - from: assigned
        to: in_progress
        evidence: assignee_id != null
        role: support_agent
      - from: in_progress
        to: resolved
        evidence: resolution_notes != null
        role: support_agent
      - from: resolved
        to: closed
        role: any
```

- [ ] **Step 3: Validate the example parses**

Run: `cd examples/support_tickets && dazzle validate`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add examples/support_tickets/app/
git commit -m "feat(examples): add ticket lifecycle declaration (ADR-0020)"
```

---

## Task 6: Grammar documentation

**Files:**
- Modify: `docs/reference/grammar.md`

- [ ] **Step 1: Add lifecycle section**

Find the entity grammar section in `docs/reference/grammar.md` and append:

```markdown
### Lifecycle block (ADR-0020)

Entities may declare a lifecycle with ordered states and evidence predicates.
Consumed by the agent-led fitness methodology's `progress_evaluator`.

```dsl
entity Ticket "Support Ticket":
  id: uuid pk
  status: enum[new, assigned, resolved] required

  lifecycle:
    status_field: status
    states:
      - new       (order: 0)
      - assigned  (order: 1)
      - resolved  (order: 2)
    transitions:
      - from: new
        to: assigned
        evidence: assignee_id != null
        role: support_agent
      - from: assigned
        to: resolved
        evidence: resolution_notes != null
        role: support_agent
```

**Semantic rules:**

- `status_field` must be an enum field on the entity
- Each declared state must match a value of that enum
- State `order` values must be unique (induce a total order)
- A transition's `from` and `to` must reference declared states
- `evidence` (optional) is a boolean predicate over entity fields; when present,
  the transition is counted as valid progress only if the predicate holds
- `role` (optional, repeatable) lists persona roles authorized to perform the
  transition
```

- [ ] **Step 2: Commit**

```bash
git add docs/reference/grammar.md
git commit -m "docs(grammar): lifecycle block syntax (ADR-0020)"
```

---

## Task 7: CHANGELOG entry

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add entry under `## [Unreleased]` → `### Added`**

```markdown
### Added

- DSL `lifecycle:` block on entities with ordered states and per-transition
  evidence predicates. Prerequisite for the agent-led fitness methodology's
  progress evaluator. See ADR-0020.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "changelog: lifecycle: block (ADR-0020)"
```

---

## Task 8: Final integration check

- [ ] **Step 1: Run the full unit-test suite for the touched modules**

Run:
```bash
pytest tests/unit/test_lifecycle_ir.py tests/unit/test_lifecycle_parser.py tests/unit/test_lifecycle_validation.py -v
```
Expected: all tests pass.

- [ ] **Step 2: Run lint**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`
Expected: no errors.

- [ ] **Step 3: Run mypy**

Run: `mypy src/dazzle/core/ir/lifecycle.py src/dazzle/core/dsl_parser_impl/lifecycle.py`
Expected: no errors.

- [ ] **Step 4: Validate every example app to catch regressions**

Run:
```bash
for app in examples/*/; do
  if [ -d "$app/app" ]; then
    echo "Validating $app"
    (cd "$app" && dazzle validate) || echo "FAILED: $app"
  fi
done
```
Expected: all examples validate. (Any example that doesn't declare a lifecycle still validates — lifecycle is optional.)

- [ ] **Step 5: Final commit if any small fixes were needed**

```bash
git status
# If any pending changes:
git add -A
git commit -m "chore: lint + mypy fixes for lifecycle"
```

---

## Success criteria (ADR prerequisite)

When all tasks are complete:

1. `LifecycleSpec`, `LifecycleStateSpec`, `LifecycleTransitionSpec` exist as Pydantic IR models
2. `EntitySpec.lifecycle` is an optional field
3. DSL parser accepts `lifecycle:` blocks inside entity declarations
4. Validator enforces: status_field exists, states match enum values, orders are unique, transitions reference declared states
5. `support_tickets` example declares a ticket lifecycle and validates cleanly
6. Grammar documentation updated
7. CHANGELOG entry added
8. All tests pass, lint clean, mypy clean
9. `dazzle validate` on every example app still succeeds

**This plan does NOT touch `progress_evaluator.py` itself** — that lives in the fitness v1 plan. This plan only delivers the DSL extension the evaluator will read.
