# Scope `via` Clause Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `via` keyword to scope blocks so access control can filter rows through junction tables (e.g., `via AgentAssignment(agent = current_user.contact, contact = id)`).

**Architecture:** New `ViaCondition` IR node flows through the existing pipeline: lexer (VIA token already exists) → parser (new branch in `_parse_scope_rule`) → IR (`via_condition` field on `ConditionExpr`) → linker (junction entity/field validation) → converter (new `_convert_via_condition`) → backend spec (`via_check` kind on `AccessConditionSpec`) → route generator (new `_build_via_subquery`) → query builder (new `IN_SUBQUERY` operator).

**Design decision:** The spec proposed a separate `ViaConditionSpec` type, but this plan adds via fields directly to `AccessConditionSpec` with `kind="via_check"` — following the existing `grant_check` pattern. This avoids widening `ScopeRuleSpec.condition` to a union type and keeps all condition kinds in one flat model, consistent with how the codebase already works.

**Tech Stack:** Python 3.12, Pydantic models (IR + backend specs), raw SQL subquery generation, existing parser infrastructure.

**Spec:** `docs/superpowers/specs/2026-03-18-scope-via-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/dazzle/core/ir/conditions.py` | **Modify** — add `ViaBinding`, `ViaCondition` models + `via_condition` field on `ConditionExpr` |
| `src/dazzle/core/dsl_parser_impl/entity.py` | **Modify** — add `_parse_via_condition()` method, branch in `_parse_scope_rule()` |
| `src/dazzle/core/linker.py` | **Modify** — add via junction entity/field validation during linking |
| `src/dazzle_back/specs/auth.py` | **Modify** — add `via_check` kind + via fields to `AccessConditionSpec` |
| `src/dazzle_back/converters/entity_converter.py` | **Modify** — add `_convert_via_condition()`, branch in `_convert_scope_rule()` |
| `src/dazzle_back/runtime/route_generator.py` | **Modify** — add `_build_via_subquery()`, handle `via_check` in `_extract_condition_filters()` |
| `src/dazzle_back/runtime/query_builder.py` | **Modify** — add `IN_SUBQUERY` to `FilterOperator` + `to_sql()` handling |
| `tests/unit/test_scope_via.py` | **Create** — all via-related tests (parser, IR, converter, runtime) |
| `examples/shapes_validation/dsl/entities.dsl` | **Modify** — add junction-table scoped entity example |

---

## Task 1: IR Model — ViaBinding + ViaCondition

**Files:**
- Modify: `src/dazzle/core/ir/conditions.py`
- Create: `tests/unit/test_scope_via.py` (initial)

Add the new IR types and the `via_condition` field on `ConditionExpr`.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_scope_via.py
"""Tests for scope via clause — junction-table access control (#530)."""

from __future__ import annotations

import pytest

from dazzle.core.ir.conditions import ConditionExpr, ViaBinding, ViaCondition


class TestViaBindingModel:
    def test_entity_binding(self) -> None:
        b = ViaBinding(junction_field="contact", target="id")
        assert b.junction_field == "contact"
        assert b.target == "id"
        assert b.operator == "="

    def test_user_binding(self) -> None:
        b = ViaBinding(junction_field="agent", target="current_user.contact")
        assert b.target == "current_user.contact"

    def test_literal_filter(self) -> None:
        b = ViaBinding(junction_field="revoked_at", target="null", operator="=")
        assert b.target == "null"

    def test_not_equals_operator(self) -> None:
        b = ViaBinding(junction_field="status", target="null", operator="!=")
        assert b.operator == "!="


class TestViaConditionModel:
    def test_basic_via(self) -> None:
        via = ViaCondition(
            junction_entity="AgentAssignment",
            bindings=[
                ViaBinding(junction_field="agent", target="current_user.contact"),
                ViaBinding(junction_field="contact", target="id"),
            ],
        )
        assert via.junction_entity == "AgentAssignment"
        assert len(via.bindings) == 2

    def test_with_literal_filter(self) -> None:
        via = ViaCondition(
            junction_entity="AgentAssignment",
            bindings=[
                ViaBinding(junction_field="agent", target="current_user.contact"),
                ViaBinding(junction_field="contact", target="id"),
                ViaBinding(junction_field="revoked_at", target="null"),
            ],
        )
        assert len(via.bindings) == 3


class TestConditionExprViaField:
    def test_via_condition_on_condition_expr(self) -> None:
        via = ViaCondition(
            junction_entity="AgentAssignment",
            bindings=[
                ViaBinding(junction_field="agent", target="current_user.contact"),
                ViaBinding(junction_field="contact", target="id"),
            ],
        )
        expr = ConditionExpr(via_condition=via)
        assert expr.via_condition is not None
        assert expr.is_via_check
        assert not expr.is_compound
        assert not expr.is_role_check

    def test_via_condition_none_by_default(self) -> None:
        expr = ConditionExpr()
        assert expr.via_condition is None
        assert not expr.is_via_check
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_scope_via.py -v`
Expected: FAIL — `ImportError: cannot import name 'ViaBinding'`

- [ ] **Step 3: Implement IR types**

In `src/dazzle/core/ir/conditions.py`, add before the `ConditionExpr` class:

```python
class ViaBinding(BaseModel):
    """A single binding inside a via() scope clause.

    Binding types:
    - Entity binding: junction_field = "id" or "field_name" (links back to scoped entity)
    - User binding: junction_field = "current_user" or "current_user.attr"
    - Literal filter: junction_field = "null" (with operator "=" or "!=")
    """

    junction_field: str
    target: str  # "id", "field_name", "current_user", "current_user.attr", or "null"
    operator: str = "="  # "=" or "!="

    model_config = ConfigDict(frozen=True)


class ViaCondition(BaseModel):
    """Subquery condition through a junction table.

    Example DSL:
        via AgentAssignment(agent = current_user.contact, contact = id, revoked_at = null)

    Generates SQL:
        WHERE "id" IN (SELECT "contact" FROM "AgentAssignment" WHERE "agent" = $1 AND "revoked_at" IS NULL)
    """

    junction_entity: str
    bindings: list[ViaBinding]

    model_config = ConfigDict(frozen=True)
```

Then add to `ConditionExpr`:

```python
class ConditionExpr(BaseModel):
    # ... existing fields ...
    via_condition: ViaCondition | None = None  # Via-subquery condition (#530)

    # ... existing properties ...

    @property
    def is_via_check(self) -> bool:
        """Check if this is a via-check condition."""
        return self.via_condition is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_scope_via.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/ir/conditions.py tests/unit/test_scope_via.py
git commit -m "feat(scope): add ViaBinding, ViaCondition IR types (#530)"
```

---

## Task 2: Parser — `_parse_via_condition()`

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/entity.py`
- Modify: `tests/unit/test_scope_via.py` (add parser tests)

Add `via` parsing branch in `_parse_scope_rule()`. The `VIA` token already exists in the lexer (`TokenType.VIA`).

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_scope_via.py`:

```python
from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError


def _parse(dsl: str):
    """Parse DSL text and return the ModuleFragment."""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return fragment


class TestParseViaClause:
    def test_basic_via(self) -> None:
        dsl = '''
module test
app test "Test"

entity AgentAssignment "Assignment":
  agent: ref Contact required
  contact: ref Contact required

entity Contact "Contact":
  name: str(200) required

  permit:
    list: role(agent)

  scope:
    list: via AgentAssignment(agent = current_user.contact, contact = id)
      for: agent
'''
        fragment = _parse(dsl)
        contact = [e for e in fragment.entities if e.name == "Contact"][0]
        assert contact.access is not None
        assert len(contact.access.scopes) == 1

        scope_rule = contact.access.scopes[0]
        assert scope_rule.condition is not None
        assert scope_rule.condition.via_condition is not None

        via = scope_rule.condition.via_condition
        assert via.junction_entity == "AgentAssignment"
        assert len(via.bindings) == 2

    def test_via_with_literal_filter(self) -> None:
        dsl = '''
module test
app test "Test"

entity AgentAssignment "Assignment":
  agent: ref Contact required
  contact: ref Contact required
  revoked_at: datetime

entity Contact "Contact":
  name: str(200) required

  permit:
    list: role(agent)

  scope:
    list: via AgentAssignment(agent = current_user.contact, contact = id, revoked_at = null)
      for: agent
'''
        fragment = _parse(dsl)
        contact = [e for e in fragment.entities if e.name == "Contact"][0]
        via = contact.access.scopes[0].condition.via_condition
        assert len(via.bindings) == 3
        null_binding = [b for b in via.bindings if b.target == "null"][0]
        assert null_binding.junction_field == "revoked_at"

    def test_via_with_not_equals(self) -> None:
        dsl = '''
module test
app test "Test"

entity TeamMembership "Membership":
  user: ref User required
  team: ref Team required
  status: str(20)

entity Task "Task":
  team: ref Team required

  permit:
    list: role(member)

  scope:
    list: via TeamMembership(user = current_user, team = team, status != null)
      for: member
'''
        fragment = _parse(dsl)
        task = [e for e in fragment.entities if e.name == "Task"][0]
        via = task.access.scopes[0].condition.via_condition
        ne_binding = [b for b in via.bindings if b.operator == "!="][0]
        assert ne_binding.junction_field == "status"

    def test_via_missing_parens_error(self) -> None:
        dsl = '''
module test
app test "Test"

entity Contact "Contact":
  name: str(200) required

  permit:
    list: role(agent)

  scope:
    list: via AgentAssignment agent = current_user
      for: agent
'''
        with pytest.raises(ParseError, match="Expected '\\(' after"):
            _parse(dsl)

    def test_via_missing_entity_binding_error(self) -> None:
        dsl = '''
module test
app test "Test"

entity Contact "Contact":
  name: str(200) required

  permit:
    list: role(agent)

  scope:
    list: via AgentAssignment(agent = current_user)
      for: agent
'''
        with pytest.raises(ParseError, match="at least one entity binding"):
            _parse(dsl)

    def test_via_missing_user_binding_error(self) -> None:
        dsl = '''
module test
app test "Test"

entity Contact "Contact":
  name: str(200) required

  permit:
    list: role(agent)

  scope:
    list: via AgentAssignment(contact = id)
      for: agent
'''
        with pytest.raises(ParseError, match="at least one user binding"):
            _parse(dsl)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_scope_via.py::TestParseViaClause -v`
Expected: FAIL — parser doesn't recognize `via` in scope condition

- [ ] **Step 3: Implement parser**

In `src/dazzle/core/dsl_parser_impl/entity.py`, find the `_parse_scope_rule()` method. At the point where it checks for `all` keyword (around line 830-836), add a `via` branch:

```python
    # Check for 'all' keyword — means no row filter
    condition: ir.ConditionExpr | None
    if self.match(TokenType.ALL):
        self.advance()
        condition = None
    elif self.match(TokenType.VIA):
        condition = self._parse_via_condition()
    else:
        condition = self.parse_condition_expr()
```

Then add the `_parse_via_condition()` method to the same class:

```python
def _parse_via_condition(self) -> ir.ConditionExpr:
    """Parse a via clause: via Entity(binding, binding, ...).

    Returns a ConditionExpr with via_condition set.
    """
    from dazzle.core.ir.conditions import ViaBinding, ViaCondition

    via_token = self.current_token()
    self.advance()  # consume 'via'

    # Expect junction entity name
    entity_token = self.current_token()
    if not self.match(TokenType.IDENTIFIER):
        raise make_parse_error(
            f"Expected entity name after 'via', got {entity_token.type.value}",
            self.file,
            entity_token.line,
            entity_token.column,
        )
    junction_entity = entity_token.value
    self.advance()

    # Expect opening paren
    if not self.match(TokenType.LPAREN):
        paren_token = self.current_token()
        raise make_parse_error(
            f"Expected '(' after junction entity name '{junction_entity}'",
            self.file,
            paren_token.line,
            paren_token.column,
        )
    self.advance()

    # Parse comma-separated bindings
    bindings: list[ViaBinding] = []
    while not self.match(TokenType.RPAREN):
        if bindings:
            self.expect(TokenType.COMMA)

        # Parse: junction_field = target or junction_field != target
        field_token = self.current_token()
        junction_field = self.expect_identifier_or_keyword().value

        # Expect = or !=
        op_token = self.current_token()
        if self.match(TokenType.NOT_EQUALS):
            operator = "!="
            self.advance()
        elif self.match(TokenType.EQUALS):
            operator = "="
            self.advance()
        else:
            raise make_parse_error(
                f"via binding must contain '=' or '!=', got {op_token.type.value}",
                self.file,
                op_token.line,
                op_token.column,
            )

        # Parse target: identifier, current_user, current_user.attr, or null.
        # NOTE: The lexer has no CURRENT_USER or NULL token types.
        # These are parsed as IDENTIFIER tokens with specific .value strings,
        # consistent with how parse_condition_expr() handles them elsewhere.
        target_token = self.current_token()
        if not self.match(TokenType.IDENTIFIER):
            raise make_parse_error(
                f"Expected identifier in via binding, got {target_token.type.value}",
                self.file,
                target_token.line,
                target_token.column,
            )
        raw_value = target_token.value
        self.advance()

        if raw_value in ("null", "None"):
            target = "null"
        elif raw_value == "current_user":
            target = "current_user"
            # Check for dotted attribute: current_user.contact
            if self.match(TokenType.DOT):
                self.advance()
                attr_token = self.expect_identifier_or_keyword()
                target = f"current_user.{attr_token.value}"
        else:
            target = raw_value

        bindings.append(ViaBinding(
            junction_field=junction_field,
            target=target,
            operator=operator,
        ))

    self.advance()  # consume ')'

    # Validate: at least one entity binding and one user binding
    has_entity_binding = any(
        not b.target.startswith("current_user") and b.target != "null"
        for b in bindings
    )
    has_user_binding = any(
        b.target.startswith("current_user")
        for b in bindings
    )

    if not has_entity_binding:
        raise make_parse_error(
            "via condition requires at least one entity binding (e.g., 'contact = id')",
            self.file,
            via_token.line,
            via_token.column,
        )
    if not has_user_binding:
        raise make_parse_error(
            "via condition requires at least one user binding (e.g., 'agent = current_user')",
            self.file,
            via_token.line,
            via_token.column,
        )

    return ir.ConditionExpr(
        via_condition=ViaCondition(
            junction_entity=junction_entity,
            bindings=bindings,
        )
    )
```

**Note:** Check the lexer for exact `TokenType` names for `=`, `!=`, `(`, `)`. They may be `ASSIGN`/`EQUALS`, `NEQ`/`NOT_EQUALS`, `LPAREN`/`RPAREN`, etc. `null` and `current_user` are parsed as `IDENTIFIER` tokens with specific `.value` strings — there are no dedicated `TokenType.NULL` or `TokenType.CURRENT_USER` token types.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_scope_via.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/entity.py tests/unit/test_scope_via.py
git commit -m "feat(scope): parse via clause in scope blocks (#530)"
```

---

## Task 3: Linker Validation

**Files:**
- Modify: `src/dazzle/core/linker.py` (or wherever post-parse entity validation lives)
- Modify: `tests/unit/test_scope_via.py` (add validation tests)

Add post-parse validation for `via` conditions during linking: junction entity must exist, junction fields must exist on that entity, entity field must exist on the scoped entity. Emit a warning if the junction entity has no `ref` field pointing back to the scoped entity.

- [ ] **Step 1: Find the linker validation location**

Read `src/dazzle/core/linker.py` to find where entity cross-references are validated. Look for where `ref` fields are checked for valid target entities — the `via` junction entity check goes next to that.

- [ ] **Step 2: Write failing tests**

Append to `tests/unit/test_scope_via.py`:

```python
class TestLinkerViaValidation:
    def test_via_junction_entity_not_found(self) -> None:
        """Linker should error if the junction entity doesn't exist."""
        dsl = '''
module test
app test "Test"

entity Contact "Contact":
  name: str(200) required

  permit:
    list: role(agent)

  scope:
    list: via NonexistentEntity(agent = current_user, contact = id)
      for: agent
'''
        # This should raise a validation error during linking (not during parsing)
        # The exact error mechanism depends on how the linker reports errors.
        # Adapt this test after reading the linker code.
        pass  # TODO: implement after reading linker
```

- [ ] **Step 3: Implement linker validation**

Add validation in the linker that, for each entity with scope rules containing `via_condition`:
1. Check that `via_condition.junction_entity` matches a declared entity name
2. Check that each binding's `junction_field` exists on the junction entity
3. Check that entity bindings reference valid fields on the scoped entity
4. Warn if the junction entity has no `ref` field to the scoped entity

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_scope_via.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/linker.py tests/unit/test_scope_via.py
git commit -m "feat(scope): add linker validation for via junction entities (#530)"
```

---

## Task 4: Backend Spec + Converter (was Task 3)

**Files:**
- Modify: `src/dazzle_back/specs/auth.py`
- Modify: `src/dazzle_back/converters/entity_converter.py`
- Modify: `tests/unit/test_scope_via.py` (add converter tests)

Add `via_check` kind to `AccessConditionSpec` and a `_convert_via_condition()` function.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_scope_via.py`:

```python
from dazzle.core.ir.domain import PermissionKind, ScopeRule
from dazzle_back.converters.entity_converter import _convert_scope_rule
from dazzle_back.specs.auth import AccessOperationKind


class TestConvertViaCondition:
    def test_converts_via_scope_rule(self) -> None:
        via = ViaCondition(
            junction_entity="AgentAssignment",
            bindings=[
                ViaBinding(junction_field="agent", target="current_user.contact"),
                ViaBinding(junction_field="contact", target="id"),
                ViaBinding(junction_field="revoked_at", target="null"),
            ],
        )
        rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=ConditionExpr(via_condition=via),
            personas=["agent"],
        )
        spec = _convert_scope_rule(rule)

        assert spec.operation == AccessOperationKind.LIST
        assert spec.condition is not None
        assert spec.condition.kind == "via_check"
        assert spec.condition.via_junction_entity == "AgentAssignment"
        assert len(spec.condition.via_bindings) == 3
        assert spec.personas == ["agent"]

    def test_converts_via_binding_fields(self) -> None:
        via = ViaCondition(
            junction_entity="TeamMembership",
            bindings=[
                ViaBinding(junction_field="user", target="current_user"),
                ViaBinding(junction_field="team", target="team"),
            ],
        )
        rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=ConditionExpr(via_condition=via),
            personas=["member"],
        )
        spec = _convert_scope_rule(rule)
        bindings = spec.condition.via_bindings
        assert bindings[0]["junction_field"] == "user"
        assert bindings[0]["target"] == "current_user"
        assert bindings[1]["junction_field"] == "team"
        assert bindings[1]["target"] == "team"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_scope_via.py::TestConvertViaCondition -v`
Expected: FAIL — `via_check` kind not recognized

- [ ] **Step 3: Modify backend spec**

In `src/dazzle_back/specs/auth.py`, update `AccessConditionSpec`:

1. Update the `kind` literal to include `"via_check"`:
```python
kind: Literal["comparison", "role_check", "logical", "grant_check", "via_check"] = Field(...)
```

2. Add via fields after the grant fields:
```python
    # For via_check: subquery through junction table (#530)
    via_junction_entity: str | None = Field(
        default=None, description="Junction entity name (e.g., 'AgentAssignment')"
    )
    via_bindings: list[dict[str, str]] | None = Field(
        default=None, description="List of binding dicts with junction_field, target, operator"
    )
```

- [ ] **Step 4: Modify converter**

In `src/dazzle_back/converters/entity_converter.py`, modify `_convert_scope_rule()` to branch before `_convert_access_condition()`:

```python
def _convert_scope_rule(rule: ir.ScopeRule) -> ScopeRuleSpec:
    """Convert IR ScopeRule to BackendSpec ScopeRuleSpec."""
    op_map = {
        ir.PermissionKind.CREATE: AccessOperationKind.CREATE,
        ir.PermissionKind.READ: AccessOperationKind.READ,
        ir.PermissionKind.UPDATE: AccessOperationKind.UPDATE,
        ir.PermissionKind.DELETE: AccessOperationKind.DELETE,
        ir.PermissionKind.LIST: AccessOperationKind.LIST,
    }

    condition = None
    if rule.condition:
        if rule.condition.via_condition:
            condition = _convert_via_condition(rule.condition.via_condition)
        else:
            condition = _convert_access_condition(rule.condition)

    return ScopeRuleSpec(
        operation=op_map[rule.operation],
        condition=condition,
        personas=list(rule.personas),
    )
```

Add `_convert_via_condition()`:

```python
def _convert_via_condition(via: ir.ViaCondition) -> AccessConditionSpec:
    """Convert IR ViaCondition to BackendSpec AccessConditionSpec with kind='via_check'."""
    return AccessConditionSpec(
        kind="via_check",
        via_junction_entity=via.junction_entity,
        via_bindings=[
            {
                "junction_field": b.junction_field,
                "target": b.target,
                "operator": b.operator,
            }
            for b in via.bindings
        ],
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_scope_via.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/specs/auth.py src/dazzle_back/converters/entity_converter.py tests/unit/test_scope_via.py
git commit -m "feat(scope): add via_check backend spec and converter (#530)"
```

---

## Task 5: Query Builder — `IN_SUBQUERY` Operator

**Files:**
- Modify: `src/dazzle_back/runtime/query_builder.py`
- Modify: `tests/unit/test_scope_via.py` (add query builder tests)

Add the `IN_SUBQUERY` filter operator so the repository can execute subquery-based filters.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_scope_via.py`:

```python
from dazzle_back.runtime.query_builder import FilterCondition, FilterOperator


class TestInSubqueryOperator:
    def test_filter_operator_exists(self) -> None:
        assert FilterOperator.IN_SUBQUERY == "in_subquery"

    def test_parse_in_subquery_key(self) -> None:
        fc = FilterCondition.parse(
            "id__in_subquery",
            ('SELECT "contact" FROM "AgentAssignment" WHERE "agent" = %s', ["user-123"]),
        )
        assert fc.field == "id"
        assert fc.operator == FilterOperator.IN_SUBQUERY

    def test_to_sql_in_subquery(self) -> None:
        fc = FilterCondition(
            field="id",
            operator=FilterOperator.IN_SUBQUERY,
            value=('SELECT "contact" FROM "AgentAssignment" WHERE "agent" = %s', ["user-123"]),
        )
        sql, params = fc.to_sql()
        assert 'IN' in sql
        assert '"id"' in sql
        assert 'SELECT "contact"' in sql
        assert params == ["user-123"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_scope_via.py::TestInSubqueryOperator -v`
Expected: FAIL — `IN_SUBQUERY` not in `FilterOperator`

- [ ] **Step 3: Implement**

In `src/dazzle_back/runtime/query_builder.py`:

1. Add to `FilterOperator` enum:
```python
    IN_SUBQUERY = "in_subquery"  # IN subquery (for via-check scope rules)
```

2. In `FilterCondition.to_sql()`, add handling before the default case:

```python
        elif self.operator == FilterOperator.IN_SUBQUERY:
            # Value is (subquery_sql, params) tuple
            subquery_sql, subquery_params = self.value
            sql = f"{field_ref} IN ({subquery_sql})"
            return sql, list(subquery_params)
```

No entry needed in `OPERATOR_SQL` — handled as a special case in `to_sql()` (like `ISNULL` and `IN`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_scope_via.py::TestInSubqueryOperator -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/query_builder.py tests/unit/test_scope_via.py
git commit -m "feat(scope): add IN_SUBQUERY filter operator (#530)"
```

---

## Task 6: Route Generator — `_build_via_subquery()`

**Files:**
- Modify: `src/dazzle_back/runtime/route_generator.py`
- Modify: `tests/unit/test_scope_via.py` (add runtime tests)

Build the SQL subquery from a `via_check` condition and wire it into `_extract_condition_filters()`.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_scope_via.py`:

```python
from unittest.mock import MagicMock


class TestBuildViaSubquery:
    def test_basic_subquery(self) -> None:
        from dazzle_back.runtime.route_generator import _build_via_subquery

        bindings = [
            {"junction_field": "agent", "target": "current_user.contact", "operator": "="},
            {"junction_field": "contact", "target": "id", "operator": "="},
        ]
        auth_context = MagicMock()
        auth_context.user = MagicMock()
        auth_context.user.contact = "user-contact-123"

        entity_field, sql, params = _build_via_subquery(
            junction_entity="AgentAssignment",
            bindings=bindings,
            user_id="user-456",
            auth_context=auth_context,
        )

        assert entity_field == "id"
        assert '"AgentAssignment"' in sql
        assert '"contact"' in sql  # SELECT field
        assert '"agent"' in sql  # WHERE field
        assert len(params) >= 1

    def test_subquery_with_null_filter(self) -> None:
        from dazzle_back.runtime.route_generator import _build_via_subquery

        bindings = [
            {"junction_field": "agent", "target": "current_user", "operator": "="},
            {"junction_field": "contact", "target": "id", "operator": "="},
            {"junction_field": "revoked_at", "target": "null", "operator": "="},
        ]
        auth_context = MagicMock()

        entity_field, sql, params = _build_via_subquery(
            junction_entity="AgentAssignment",
            bindings=bindings,
            user_id="user-456",
            auth_context=auth_context,
        )

        assert "IS NULL" in sql
        assert entity_field == "id"

    def test_subquery_with_not_null_filter(self) -> None:
        from dazzle_back.runtime.route_generator import _build_via_subquery

        bindings = [
            {"junction_field": "user", "target": "current_user", "operator": "="},
            {"junction_field": "team", "target": "team", "operator": "="},
            {"junction_field": "active", "target": "null", "operator": "!="},
        ]
        auth_context = MagicMock()

        entity_field, sql, params = _build_via_subquery(
            junction_entity="TeamMembership",
            bindings=bindings,
            user_id="user-789",
            auth_context=auth_context,
        )

        assert "IS NOT NULL" in sql
        assert entity_field == "team"


class TestExtractViaCheckFilters:
    def test_via_check_produces_in_subquery_filter(self) -> None:
        from dazzle_back.runtime.route_generator import _extract_condition_filters

        condition = MagicMock()
        condition.kind = "via_check"
        condition.via_junction_entity = "AgentAssignment"
        condition.via_bindings = [
            {"junction_field": "agent", "target": "current_user.contact", "operator": "="},
            {"junction_field": "contact", "target": "id", "operator": "="},
        ]

        auth_context = MagicMock()
        auth_context.user = MagicMock()
        auth_context.user.contact = "user-contact-123"

        import logging
        filters: dict = {}
        _extract_condition_filters(condition, "user-456", filters, logging.getLogger(), auth_context)

        # Should produce an __in_subquery filter
        subquery_keys = [k for k in filters if k.endswith("__in_subquery")]
        assert len(subquery_keys) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_scope_via.py::TestBuildViaSubquery -v`
Expected: FAIL — `_build_via_subquery` not found

- [ ] **Step 3: Implement `_build_via_subquery()`**

In `src/dazzle_back/runtime/route_generator.py`, add:

```python
def _build_via_subquery(
    *,
    junction_entity: str,
    bindings: list[dict[str, str]],
    user_id: str,
    auth_context: Any = None,
) -> tuple[str, str, list[Any]]:
    """Build a SQL subquery for a via-check scope condition.

    Args:
        junction_entity: Name of the junction table entity.
        bindings: List of binding dicts with junction_field, target, operator.
        user_id: Authenticated user ID.
        auth_context: Auth context for resolving current_user.attr.

    Returns:
        (entity_field, subquery_sql, params) — entity_field is the field on the
        scoped entity to match against, subquery_sql is the SELECT statement,
        params is the list of parameterized values.
    """
    from dazzle_back.runtime.query_builder import quote_identifier, validate_sql_identifier

    # Defence-in-depth: validate identifiers even though they come from DSL source.
    # Protects against future codepaths that might deserialize via specs from JSON.
    validate_sql_identifier(junction_entity)
    for b in bindings:
        validate_sql_identifier(b["junction_field"])

    # Note: Uses %s placeholders (positional), matching the rest of query_builder.py.
    # The spec mentions $N (PostgreSQL-indexed) placeholders, but this codebase
    # consistently uses %s which the DB driver translates. No param_offset needed.
    junction_table = quote_identifier(junction_entity)
    select_field = None
    entity_field = None
    where_clauses: list[str] = []
    params: list[Any] = []

    for binding in bindings:
        jf = quote_identifier(binding["junction_field"])
        target = binding["target"]
        op = binding.get("operator", "=")

        if target == "null":
            if op == "=":
                where_clauses.append(f"{jf} IS NULL")
            else:
                where_clauses.append(f"{jf} IS NOT NULL")

        elif target.startswith("current_user"):
            if target == "current_user":
                resolved = user_id
            else:
                attr_name = target[len("current_user."):]
                resolved = _resolve_user_attribute(attr_name, auth_context)
            where_clauses.append(f"{jf} = %s")
            params.append(resolved)

        else:
            # Entity binding: target is a field name on the scoped entity
            select_field = jf
            entity_field = target

    if select_field is None or entity_field is None:
        raise ValueError("via condition must have at least one entity binding")

    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
    subquery_sql = f"SELECT {select_field} FROM {junction_table} WHERE {where_sql}"

    return entity_field, subquery_sql, params
```

- [ ] **Step 4: Wire into `_extract_condition_filters()`**

In `_extract_condition_filters()`, add after the `kind == "logical"` block (around line 324):

```python
    if kind == "via_check":
        junction_entity = getattr(condition, "via_junction_entity", None)
        bindings = getattr(condition, "via_bindings", None)
        if junction_entity and bindings:
            entity_field, subquery_sql, subquery_params = _build_via_subquery(
                junction_entity=junction_entity,
                bindings=bindings,
                user_id=user_id,
                auth_context=auth_context,
            )
            filters[f"{entity_field}__in_subquery"] = (subquery_sql, subquery_params)
        return
```

Also update `_is_field_condition()` (around line 991 in route_generator.py) to include `"via_check"`:

```python
# In _is_field_condition():
return kind in ("comparison", "grant_check", "via_check")
```

This prevents silent failures if a `via_check` is ever encountered outside the scope path.

Also add a similar branch for the IR `ConditionExpr` path (after the `logical_op` block, around line 379):

```python
    # Via-check condition (IR path)
    via_cond = getattr(condition, "via_condition", None)
    if via_cond is not None:
        bindings_dicts = [
            {"junction_field": b.junction_field, "target": b.target, "operator": b.operator}
            for b in via_cond.bindings
        ]
        entity_field, subquery_sql, subquery_params = _build_via_subquery(
            junction_entity=via_cond.junction_entity,
            bindings=bindings_dicts,
            user_id=user_id,
            auth_context=auth_context,
        )
        filters[f"{entity_field}__in_subquery"] = (subquery_sql, subquery_params)
        return
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_scope_via.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/runtime/route_generator.py tests/unit/test_scope_via.py
git commit -m "feat(scope): add via subquery builder and wire into filter extraction (#530)"
```

---

## Task 7: RBAC Matrix + Shapes Example + Documentation

**Files:**
- Modify: `tests/unit/test_scope_via.py` (add RBAC matrix test)
- Modify: `examples/shapes_validation/dsl/entities.dsl` (add via-scoped entity)
- Modify: `.claude/CLAUDE.md` (update DSL reference)

- [ ] **Step 1: Write RBAC matrix test**

Append to `tests/unit/test_scope_via.py`:

```python
class TestRbacMatrixVia:
    def test_via_scope_produces_permit_scoped(self) -> None:
        """A scope rule with a via condition should produce PERMIT_SCOPED."""
        dsl = '''
module test
app test "Test"

entity AgentAssignment "Assignment":
  agent: ref Contact required
  contact: ref Contact required

entity Contact "Contact":
  name: str(200) required

  permit:
    list: role(agent)

  scope:
    list: via AgentAssignment(agent = current_user.contact, contact = id)
      for: agent
'''
        fragment = _parse(dsl)
        contact = [e for e in fragment.entities if e.name == "Contact"][0]

        # Verify the scope rule has a via condition
        scope_rule = contact.access.scopes[0]
        assert scope_rule.condition.via_condition is not None
        assert scope_rule.personas == ["agent"]
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/unit/test_scope_via.py -v`
Expected: All PASS

- [ ] **Step 3: Add via example to shapes_validation**

In `examples/shapes_validation/dsl/entities.dsl`, add a junction-table entity and via-scoped entity after the existing entities. This exercises the full pipeline in the example app. (Read the file first to find the right insertion point and follow existing patterns.)

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/unit/test_scope_via.py tests/unit/test_scope_rules.py -v`
Expected: All PASS (both new and existing tests)

- [ ] **Step 5: Lint and type check**

Run: `ruff check src/dazzle/core/ir/conditions.py src/dazzle/core/dsl_parser_impl/entity.py src/dazzle_back/specs/auth.py src/dazzle_back/converters/entity_converter.py src/dazzle_back/runtime/route_generator.py src/dazzle_back/runtime/query_builder.py --fix && ruff format src/dazzle/core/ir/conditions.py src/dazzle/core/dsl_parser_impl/entity.py src/dazzle_back/specs/auth.py src/dazzle_back/converters/entity_converter.py src/dazzle_back/runtime/route_generator.py src/dazzle_back/runtime/query_builder.py`

Run: `mypy src/dazzle/core/ir/conditions.py`

- [ ] **Step 6: Update CLAUDE.md**

In `.claude/CLAUDE.md`, update the DSL Quick Reference to mention `via` in scope blocks.

- [ ] **Step 7: Commit**

```bash
git add tests/unit/test_scope_via.py examples/shapes_validation/dsl/entities.dsl .claude/CLAUDE.md
git commit -m "feat(scope): add RBAC test, shapes example, and docs for via clause (#530)"
```
