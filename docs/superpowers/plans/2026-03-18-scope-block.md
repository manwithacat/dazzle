# Scope Block Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `scope:` keyword to the DSL that separates authorization (permit: role-only) from row filtering (scope: field conditions with `for:` clauses), with default-deny at both layers.

**Architecture:** `permit:` blocks accept only role checks — field conditions become parser errors. New `scope:` blocks accept field conditions with mandatory `for:` clauses binding them to roles. The route generator gate evaluates permit-only rules (always gate-evaluable), then applies scope filters for the matched role. The access matrix gains `PERMIT_SCOPED` and `PERMIT_NO_SCOPE` decisions.

**Tech Stack:** Python 3.12+, Pydantic models, existing Dazzle parser/IR/converter/runtime infrastructure

**Spec:** `docs/superpowers/specs/2026-03-18-scope-block-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/dazzle/core/ir/domain.py` | Modify | Add `ScopeRule` dataclass, extend `AccessSpec` with `scopes` field |
| `src/dazzle/core/lexer.py` | Modify | Add `SCOPE` token type if not already present |
| `src/dazzle/core/dsl_parser_impl/entity.py` | Modify | Parse `scope:` blocks, reject field conditions in `permit:` |
| `src/dazzle_back/specs/auth.py` | Modify | Add `ScopeRuleSpec`, extend `EntityAccessSpec` |
| `src/dazzle_back/converters/entity_converter.py` | Modify | Convert `ScopeRule` → `ScopeRuleSpec` |
| `src/dazzle_back/runtime/route_generator.py` | Modify | Simplify gate (permit-only), add scope filter resolution |
| `src/dazzle_ui/runtime/page_routes.py` | Modify | Propagate scope to page data fetch |
| `src/dazzle/rbac/matrix.py` | Modify | Add `PERMIT_SCOPED`, `PERMIT_NO_SCOPE` decisions |
| `examples/shapes_validation/dsl/entities.dsl` | Modify | Migrate to scope: blocks |
| `src/dazzle/mcp/semantics_kb/logic.toml` | Modify | Update access_rules concept |
| `tests/unit/test_scope_rules.py` | Create | Parser + IR + enforcement tests |
| `tests/unit/test_rbac_matrix.py` | Modify | Add scope-aware matrix tests |
| `tests/unit/test_rbac_enforcement.py` | Modify | Add scope enforcement tests |

---

### Task 1: IR Types — `ScopeRule` and `AccessSpec.scopes`

**Files:**
- Modify: `src/dazzle/core/ir/domain.py:88-142`
- Create: `tests/unit/test_scope_rules.py`

- [ ] **Step 1: Write failing test for ScopeRule**

```python
"""Tests for scope: block IR types and parsing."""
import pytest
from dazzle.core.ir.domain import (
    AccessSpec,
    PermissionKind,
    ScopeRule,
)
from dazzle.core.ir.conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
)


class TestScopeRuleIR:
    def test_create_scope_rule_with_field_condition(self):
        condition = ConditionExpr(
            comparison=Comparison(
                field="school",
                operator=ComparisonOperator.EQ,
                value=ConditionValue(literal="current_user.school"),
            )
        )
        rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=condition,
            personas=["teacher", "school_admin"],
        )
        assert rule.operation == PermissionKind.LIST
        assert rule.personas == ["teacher", "school_admin"]
        assert rule.condition is not None

    def test_create_scope_rule_all(self):
        """scope: list: all for: oracle"""
        rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=None,  # None means 'all'
            personas=["oracle"],
        )
        assert rule.condition is None
        assert rule.personas == ["oracle"]

    def test_create_scope_rule_wildcard(self):
        """scope: list: owner = current_user for: *"""
        condition = ConditionExpr(
            comparison=Comparison(
                field="owner",
                operator=ComparisonOperator.EQ,
                value=ConditionValue(literal="current_user"),
            )
        )
        rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=condition,
            personas=["*"],
        )
        assert rule.personas == ["*"]

    def test_access_spec_has_scopes_field(self):
        spec = AccessSpec(scopes=[
            ScopeRule(operation=PermissionKind.LIST, condition=None, personas=["admin"]),
        ])
        assert len(spec.scopes) == 1
        assert spec.scopes[0].personas == ["admin"]

    def test_access_spec_scopes_default_empty(self):
        spec = AccessSpec()
        assert spec.scopes == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_scope_rules.py::TestScopeRuleIR -v`
Expected: FAIL (ScopeRule not defined)

- [ ] **Step 3: Add ScopeRule to domain.py and extend AccessSpec**

In `src/dazzle/core/ir/domain.py`, after `PermissionRule` (line ~111), add:

```python
class ScopeRule(BaseModel):
    """Row-filtering scope rule with persona binding.

    Defines which records a role can see after passing the permit gate.
    condition=None means 'all' (no filter). personas=["*"] means all
    authorized roles.
    """

    operation: PermissionKind
    condition: ConditionExpr | None = None
    personas: list[str] = Field(default_factory=list)
```

Extend `AccessSpec` (line ~114) to add:

```python
class AccessSpec(BaseModel):
    visibility: list[VisibilityRule] = Field(default_factory=list)
    permissions: list[PermissionRule] = Field(default_factory=list)
    scopes: list[ScopeRule] = Field(default_factory=list)  # NEW
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_scope_rules.py::TestScopeRuleIR -v`
Expected: ALL PASS

- [ ] **Step 5: Lint and commit**

```bash
ruff check src/dazzle/core/ir/domain.py tests/unit/test_scope_rules.py --fix
ruff format src/dazzle/core/ir/domain.py tests/unit/test_scope_rules.py
git add src/dazzle/core/ir/domain.py tests/unit/test_scope_rules.py
git commit -m "feat: add ScopeRule IR type and AccessSpec.scopes field"
```

---

### Task 2: Parser — `scope:` block + reject field conditions in `permit:`

**Files:**
- Modify: `src/dazzle/core/lexer.py` (add SCOPE token if needed)
- Modify: `src/dazzle/core/dsl_parser_impl/entity.py:349-504`
- Modify: `tests/unit/test_scope_rules.py`

- [ ] **Step 1: Write failing parser tests**

Add to `tests/unit/test_scope_rules.py`:

```python
from dazzle.core.parser import parse_dsl


class TestScopeBlockParsing:
    def test_parse_scope_block(self):
        dsl = """
module test
app test_app "Test"

entity Item "Item":
  id: uuid pk
  name: str(200) required
  school: ref School required

  permit:
    list: role(teacher)
    read: role(teacher)

  scope:
    list: school = current_user.school
      for: teacher
    read: school = current_user.school
      for: teacher
"""
        _, _, _, _, fragment = parse_dsl(dsl, "test.dsl")
        entity = fragment.entities[0]
        assert entity.access is not None
        assert len(entity.access.scopes) == 2
        assert entity.access.scopes[0].operation.value == "list"
        assert entity.access.scopes[0].personas == ["teacher"]

    def test_parse_scope_all(self):
        dsl = """
module test
app test_app "Test"

entity Item "Item":
  id: uuid pk
  name: str(200) required

  permit:
    list: role(admin)

  scope:
    list: all
      for: admin
"""
        _, _, _, _, fragment = parse_dsl(dsl, "test.dsl")
        entity = fragment.entities[0]
        assert len(entity.access.scopes) == 1
        assert entity.access.scopes[0].condition is None  # 'all' = no filter
        assert entity.access.scopes[0].personas == ["admin"]

    def test_parse_scope_wildcard_for(self):
        dsl = """
module test
app test_app "Test"

entity Item "Item":
  id: uuid pk
  owner: ref User required

  permit:
    list: authenticated

  scope:
    list: owner = current_user
      for: *
"""
        _, _, _, _, fragment = parse_dsl(dsl, "test.dsl")
        entity = fragment.entities[0]
        assert entity.access.scopes[0].personas == ["*"]

    def test_field_condition_in_permit_raises_error(self):
        dsl = """
module test
app test_app "Test"

entity Item "Item":
  id: uuid pk
  school: ref School required

  permit:
    list: school = current_user.school
"""
        with pytest.raises(Exception, match="Field condition.*scope"):
            parse_dsl(dsl, "test.dsl")

    def test_parse_scope_multiple_for_roles(self):
        dsl = """
module test
app test_app "Test"

entity Item "Item":
  id: uuid pk
  realm: ref Realm required

  permit:
    list: role(sovereign, architect)

  scope:
    list: realm = current_user.realm
      for: sovereign, architect
"""
        _, _, _, _, fragment = parse_dsl(dsl, "test.dsl")
        assert entity := fragment.entities[0]
        assert entity.access.scopes[0].personas == ["sovereign", "architect"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_scope_rules.py::TestScopeBlockParsing -v`
Expected: FAIL (scope: not recognized by parser)

- [ ] **Step 3: Add SCOPE token to lexer**

Read `src/dazzle/core/lexer.py` to check if `SCOPE` already exists in the `TokenType` enum or keyword map. If not, add it alongside `PERMIT`, `FORBID`, `AUDIT`.

- [ ] **Step 4: Implement scope: block parsing in entity.py**

In `src/dazzle/core/dsl_parser_impl/entity.py`:

1. In the entity block dispatch loop (around line 349), add a `scope:` branch alongside `permit:` and `forbid:`:
   ```python
   elif keyword == "scope":
       self._advance()  # consume 'scope'
       self._expect_token("COLON")
       scope_rules = []
       while self._check_indent_level(indent + 1):
           rule = self._parse_scope_rule()
           scope_rules.append(rule)
       # Add to access spec later
   ```

2. Create `_parse_scope_rule()` method that:
   - Parses operation keyword (list/read/create/update/delete)
   - Parses `:`
   - If next token is `all` → condition = None
   - Otherwise → parse condition expression (field conditions only)
   - Expects indented `for:` line with comma-separated role names (or `*`)
   - Returns `ir.ScopeRule(operation=op, condition=cond, personas=personas)`

3. In `_parse_policy_rule()` (line 667), add validation: if `effect == PolicyEffect.PERMIT` and the parsed condition contains a field comparison (not a role check), raise a parser error:
   ```
   Field condition '{field} = {value}' in permit: block.
   Field conditions define row filtering, not authorization.
   Move to a scope: block.
   ```

4. Wire `scope_rules` into the `AccessSpec` construction (line ~498-504):
   ```python
   ir.AccessSpec(
       visibility=visibility_rules,
       permissions=permission_rules,
       scopes=scope_rules,
   )
   ```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_scope_rules.py -v`
Expected: ALL PASS

Run: `pytest tests/unit/test_parser.py -v` (existing parser tests should still pass)

- [ ] **Step 6: Lint and commit**

```bash
ruff check src/dazzle/core/lexer.py src/dazzle/core/dsl_parser_impl/entity.py tests/unit/test_scope_rules.py --fix
ruff format src/dazzle/core/lexer.py src/dazzle/core/dsl_parser_impl/entity.py tests/unit/test_scope_rules.py
git add src/dazzle/core/lexer.py src/dazzle/core/dsl_parser_impl/entity.py tests/unit/test_scope_rules.py
git commit -m "feat: parse scope: blocks with for: clauses, reject field conditions in permit:"
```

---

### Task 3: Backend Specs — `ScopeRuleSpec` and Converter

**Files:**
- Modify: `src/dazzle_back/specs/auth.py`
- Modify: `src/dazzle_back/converters/entity_converter.py:648-675`
- Modify: `tests/unit/test_scope_rules.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_scope_rules.py`:

```python
class TestScopeRuleConversion:
    def test_convert_scope_rule(self):
        from dazzle.core.ir.domain import PermissionKind, ScopeRule
        from dazzle.core.ir.conditions import (
            Comparison, ComparisonOperator, ConditionExpr, ConditionValue,
        )
        from dazzle_back.converters.entity_converter import _convert_scope_rule

        ir_rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=ConditionExpr(
                comparison=Comparison(
                    field="school",
                    operator=ComparisonOperator.EQ,
                    value=ConditionValue(literal="current_user.school"),
                )
            ),
            personas=["teacher"],
        )
        spec = _convert_scope_rule(ir_rule)
        assert spec.operation.value == "list"
        assert spec.personas == ["teacher"]
        assert spec.condition is not None
        assert spec.condition.kind == "comparison"

    def test_convert_scope_rule_all(self):
        from dazzle.core.ir.domain import PermissionKind, ScopeRule
        from dazzle_back.converters.entity_converter import _convert_scope_rule

        ir_rule = ScopeRule(
            operation=PermissionKind.LIST,
            condition=None,
            personas=["oracle"],
        )
        spec = _convert_scope_rule(ir_rule)
        assert spec.condition is None
        assert spec.personas == ["oracle"]
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Add ScopeRuleSpec to auth.py**

In `src/dazzle_back/specs/auth.py`, after `PermissionRuleSpec`:

```python
class ScopeRuleSpec(BaseModel):
    """Row-filtering scope rule — converted from IR ScopeRule."""
    operation: AccessOperationKind
    condition: AccessConditionSpec | None = None  # None means 'all'
    personas: list[str] = Field(default_factory=list)
```

Extend `EntityAccessSpec`:
```python
class EntityAccessSpec(BaseModel):
    visibility: list[VisibilityRuleSpec] = Field(default_factory=list)
    permissions: list[PermissionRuleSpec] = Field(default_factory=list)
    scopes: list[ScopeRuleSpec] = Field(default_factory=list)  # NEW
```

- [ ] **Step 4: Add converter function**

In `src/dazzle_back/converters/entity_converter.py`, after `_convert_permission_rule`:

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
    return ScopeRuleSpec(
        operation=op_map[rule.operation],
        condition=_convert_access_condition(rule.condition) if rule.condition else None,
        personas=list(rule.personas),
    )
```

Update `_convert_access_spec` to include scopes:
```python
def _convert_access_spec(access: ir.AccessSpec) -> EntityAccessSpec:
    return EntityAccessSpec(
        visibility=[_convert_visibility_rule(v) for v in access.visibility],
        permissions=[_convert_permission_rule(p) for p in access.permissions],
        scopes=[_convert_scope_rule(s) for s in access.scopes],
    )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_scope_rules.py -v`

- [ ] **Step 6: Lint and commit**

```bash
git add src/dazzle_back/specs/auth.py src/dazzle_back/converters/entity_converter.py tests/unit/test_scope_rules.py
git commit -m "feat: add ScopeRuleSpec backend type and converter"
```

---

### Task 4: Enforcement — Simplified Gate + Scope Filter Resolution

**Files:**
- Modify: `src/dazzle_back/runtime/route_generator.py:139-214, 945-1024`
- Modify: `tests/unit/test_rbac_enforcement.py`

- [ ] **Step 1: Write failing enforcement tests**

Add to `tests/unit/test_rbac_enforcement.py`:

```python
class TestScopeEnforcement:
    """Tests for the scope: block enforcement in the LIST handler."""

    @pytest.fixture(autouse=True)
    def _require_fastapi(self):
        pytest.importorskip("fastapi")

    @pytest.mark.asyncio
    async def test_permit_only_rules_always_gate_evaluated(self):
        """With scope: separation, permit: rules are always role-only
        and always evaluable at the gate."""
        # ... test that pure role-check permit rules hit the gate

    @pytest.mark.asyncio
    async def test_scope_filters_applied_for_matching_role(self):
        """After passing permit gate, scope filters are applied
        based on the user's role matching a scope rule's for: clause."""
        # ... test that scope rule's field condition becomes SQL filter

    @pytest.mark.asyncio
    async def test_no_scope_rule_returns_empty(self):
        """If a role passes permit but has no matching scope rule,
        the result should be empty (default-deny at scope layer)."""
        # ... test that missing scope produces empty results

    @pytest.mark.asyncio
    async def test_scope_all_returns_unfiltered(self):
        """scope: list: all for: admin means no filter applied."""
        # ... test that scope with condition=None produces no SQL filter

    @pytest.mark.asyncio
    async def test_scope_wildcard_for_applies_to_all(self):
        """scope: list: owner = current_user for: * applies to any
        role that passes the permit gate."""
        # ... test that for: * matches any permitted role
```

- [ ] **Step 2: Implement scope-aware enforcement in route_generator.py**

The key changes:

1. **Simplify the LIST gate** (lines ~994-1015): Since `permit:` rules now contain only role checks, `_is_field_condition` should always return `False` for permit rules. The gate ALWAYS fires for permit rules. Remove the `has_field_conditions` bypass entirely.

2. **Add scope filter resolution** after the gate passes:
   ```python
   def _resolve_scope_filters(
       cedar_access_spec: Any,
       operation: str,
       user_roles: set[str],
       user_id: str,
       auth_context: Any | None = None,
   ) -> dict[str, Any] | None:
       """Resolve scope rules to SQL filters for the user's role.

       Returns:
           dict of SQL filters if a scope rule matches
           {} if scope is 'all' (no filter)
           None if no scope rule matches (default-deny: empty result)
       """
   ```

3. **Wire into `_list_handler_body`**: After the permit gate passes, call `_resolve_scope_filters`. If it returns `None`, return an empty list (no records). Otherwise merge the scope filters with existing SQL filters.

4. **Keep `_extract_cedar_row_filters` for backward compatibility** with apps that haven't migrated to `scope:` blocks yet. If `scopes` list is empty, fall back to the old behavior.

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_rbac_enforcement.py -v`

- [ ] **Step 4: Lint and commit**

```bash
git add src/dazzle_back/runtime/route_generator.py tests/unit/test_rbac_enforcement.py
git commit -m "feat: scope-aware enforcement — simplified gate + scope filter resolution (#526)"
```

---

### Task 5: Page Routes — Propagate Scope to UI

**Files:**
- Modify: `src/dazzle_ui/runtime/page_routes.py:195-340`

- [ ] **Step 1: Update page route Cedar gate to scope-aware logic**

The page route handler (the #527 fix) currently duplicates the `_is_field_condition` logic. Update it to match the new enforcement model:

1. Permit gate always fires (no field-condition bypass)
2. After permit passes, check scope rules for the user's role
3. If no scope matches, return 403 (or a "no access" page)

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/test_rbac_enforcement.py -v`

- [ ] **Step 3: Lint and commit**

```bash
git add src/dazzle_ui/runtime/page_routes.py
git commit -m "feat: propagate scope: rules to UI page route enforcement"
```

---

### Task 6: Access Matrix — `PERMIT_SCOPED` and `PERMIT_NO_SCOPE`

**Files:**
- Modify: `src/dazzle/rbac/matrix.py:25-38, 319+`
- Modify: `tests/unit/test_rbac_matrix.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/unit/test_rbac_matrix.py`:

```python
class TestScopeAwareMatrix:
    def test_permit_with_scope_all_is_permit(self):
        """Role has permit + scope: all → PERMIT"""
        # ... build appspec with permit + scope all

    def test_permit_with_scope_filter_is_permit_scoped(self):
        """Role has permit + scope: field condition → PERMIT_SCOPED"""
        # ... build appspec with permit + scope field

    def test_permit_without_scope_is_permit_no_scope(self):
        """Role passes permit but has no scope rule → PERMIT_NO_SCOPE (warning)"""
        # ... build appspec with permit but no matching scope

    def test_no_permit_is_deny(self):
        """Role has no permit rule → DENY (unchanged)"""
        # ...
```

- [ ] **Step 2: Add new PolicyDecision values**

In `src/dazzle/rbac/matrix.py`:

```python
class PolicyDecision(str, Enum):
    PERMIT = "PERMIT"
    PERMIT_SCOPED = "PERMIT_SCOPED"         # NEW
    PERMIT_NO_SCOPE = "PERMIT_NO_SCOPE"     # NEW (warning)
    DENY = "DENY"
    PERMIT_FILTERED = "PERMIT_FILTERED"     # DEPRECATED — use PERMIT_SCOPED
    PERMIT_UNPROTECTED = "PERMIT_UNPROTECTED"
```

- [ ] **Step 3: Update `generate_access_matrix` to evaluate scope rules**

After determining a role passes permit, check scope rules:
- If `access.scopes` is empty → fall back to old `PERMIT_FILTERED` behavior (backward compat)
- If scope rule matches with condition=None → `PERMIT`
- If scope rule matches with field condition → `PERMIT_SCOPED`
- If no scope rule matches the role → `PERMIT_NO_SCOPE` + warning

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_rbac_matrix.py -v`

- [ ] **Step 5: Lint and commit**

```bash
git add src/dazzle/rbac/matrix.py tests/unit/test_rbac_matrix.py
git commit -m "feat: add PERMIT_SCOPED and PERMIT_NO_SCOPE to access matrix"
```

---

### Task 7: Shapes Validation App + Knowledge Base

**Files:**
- Modify: `examples/shapes_validation/dsl/entities.dsl`
- Modify: `src/dazzle/mcp/semantics_kb/logic.toml`

- [ ] **Step 1: Migrate Shapes DSL to scope: blocks**

Rewrite `entities.dsl` per the spec: move all field conditions from `permit:` to `scope:` with `for:` clauses. Add `scope: list: all for: oracle` for unrestricted roles.

- [ ] **Step 2: Validate Shapes DSL**

Run: `cd examples/shapes_validation && dazzle validate`
Expected: Parse succeeds

- [ ] **Step 3: Verify RBAC matrix**

Run: `cd examples/shapes_validation && dazzle rbac matrix`
Expected: Matrix shows PERMIT, PERMIT_SCOPED, DENY — no PERMIT_UNPROTECTED or PERMIT_NO_SCOPE

- [ ] **Step 4: Update knowledge base**

In `src/dazzle/mcp/semantics_kb/logic.toml`, update the `access_rules` concept to show the two-block pattern (permit: for authorization, scope: for row filtering).

- [ ] **Step 5: Commit**

```bash
git add examples/shapes_validation/dsl/entities.dsl src/dazzle/mcp/semantics_kb/logic.toml
git commit -m "feat: migrate Shapes app to scope: blocks, update KB"
```

---

### Task 8: Bootstrap Workflow + Documentation

**Files:**
- Modify: `src/dazzle/mcp/server/handlers/bootstrap.py`
- Modify: `docs/reference/access-control.md`
- Modify: `docs/reference/rbac-verification.md`

- [ ] **Step 1: Update bootstrap step 7**

Split step 7 into 7a (permit: with role checks) and 7b (scope: with field conditions and for: clauses).

- [ ] **Step 2: Update access-control.md**

Add a "Scope Rules" section explaining the two-block pattern. Update the "Runtime Evaluation Model" section to show the new two-tier flow (permit gate → scope filter).

- [ ] **Step 3: Update rbac-verification.md**

Add `PERMIT_SCOPED` and `PERMIT_NO_SCOPE` to the decision table. Update the Shapes persona table.

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/mcp/server/handlers/bootstrap.py docs/reference/access-control.md docs/reference/rbac-verification.md
git commit -m "docs: update bootstrap workflow and reference docs for scope: block"
```

---

## Execution Dependencies

```
Task 1 (IR types)
    ↓
Task 2 (Parser) ──→ Task 7 (Shapes + KB)
    ↓
Task 3 (Backend specs + converter)
    ↓
Task 4 (Enforcement) ──→ Task 5 (Page routes)
    ↓
Task 6 (Access matrix) ──→ Task 7 (Shapes + KB)
                           Task 8 (Bootstrap + docs)
```

**Parallelism**: Tasks 1 and 2 are sequential (2 depends on 1). Tasks 4, 5, 6 depend on 3. Tasks 7 and 8 can run after 6 is complete. Task 5 depends on 4 (same enforcement pattern).
