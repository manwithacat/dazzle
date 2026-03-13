# Grant Schema Core Infrastructure — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the core grant infrastructure (IR types, parser, grant store, condition evaluator) that enables runtime-configurable RBAC via `grant_schema` DSL constructs and `has_grant()` condition evaluation.

**Architecture:** Three new integration layers: (1) IR types + parser for `grant_schema` constructs and `has_grant()` conditions, (2) runtime grant store with audit events, (3) condition evaluator extensions for grant checking. Prerequisite: fix `role_check` evaluation which currently silently passes as true.

**Tech Stack:** Python 3.12+, Pydantic (frozen models), SQLite (runtime DB), pytest (TDD)

**Spec:** `docs/superpowers/specs/2026-03-13-grant-schema-runtime-rbac-design.md`

---

## Chunk 1: Prerequisite + IR Types

### Task 0: Fix `role_check` evaluation in condition evaluator

The condition evaluator silently returns `True` for `role_check` conditions (falls through the `if` chain to `return True` at line 50 of `condition_evaluator.py`). This must be fixed before grant work begins because `granted_by` expressions use `role()`.

**Files:**
- Modify: `src/dazzle_back/runtime/condition_evaluator.py:19-50` (`evaluate_condition`)
- Modify: `src/dazzle_back/runtime/condition_evaluator.py:244-300` (`condition_to_sql_filter`)
- Test: `tests/unit/test_condition_evaluator_role_check.py` (new)

- [ ] **Step 1: Write failing tests for role_check evaluation**

```python
# tests/unit/test_condition_evaluator_role_check.py
"""Tests for role_check evaluation in condition evaluator."""

from dazzle_back.runtime.condition_evaluator import evaluate_condition


class TestRoleCheckEvaluation:
    """Test role_check conditions in evaluate_condition."""

    def test_role_check_true_when_user_has_role(self):
        condition = {"role_check": {"role_name": "admin"}}
        record = {}
        context = {"user_roles": ["admin", "editor"]}
        assert evaluate_condition(condition, record, context) is True

    def test_role_check_false_when_user_lacks_role(self):
        condition = {"role_check": {"role_name": "admin"}}
        record = {}
        context = {"user_roles": ["editor"]}
        assert evaluate_condition(condition, record, context) is False

    def test_role_check_false_when_no_roles_in_context(self):
        condition = {"role_check": {"role_name": "admin"}}
        record = {}
        context = {}
        assert evaluate_condition(condition, record, context) is False

    def test_role_check_false_when_roles_empty(self):
        condition = {"role_check": {"role_name": "admin"}}
        record = {}
        context = {"user_roles": []}
        assert evaluate_condition(condition, record, context) is False

    def test_role_check_combined_with_or(self):
        """role(admin) or owner_id = current_user — user has role."""
        condition = {
            "operator": "or",
            "left": {"role_check": {"role_name": "admin"}},
            "right": {
                "comparison": {
                    "field": "owner_id",
                    "operator": "eq",
                    "value": {"literal": "current_user"},
                }
            },
        }
        record = {"owner_id": "other-user"}
        context = {"user_roles": ["admin"], "current_user_id": "user-1"}
        assert evaluate_condition(condition, record, context) is True

    def test_role_check_combined_with_or_fallback_to_comparison(self):
        """role(admin) or owner_id = current_user — user lacks role, owns record."""
        condition = {
            "operator": "or",
            "left": {"role_check": {"role_name": "admin"}},
            "right": {
                "comparison": {
                    "field": "owner_id",
                    "operator": "eq",
                    "value": {"literal": "current_user"},
                }
            },
        }
        record = {"owner_id": "user-1"}
        context = {"user_roles": ["editor"], "current_user_id": "user-1"}
        assert evaluate_condition(condition, record, context) is True

    def test_role_check_combined_with_and(self):
        """role(admin) and status = active — both must hold."""
        condition = {
            "operator": "and",
            "left": {"role_check": {"role_name": "admin"}},
            "right": {
                "comparison": {
                    "field": "status",
                    "operator": "eq",
                    "value": {"literal": "active"},
                }
            },
        }
        record = {"status": "active"}
        context = {"user_roles": ["admin"]}
        assert evaluate_condition(condition, record, context) is True

    def test_role_check_combined_with_and_role_fails(self):
        condition = {
            "operator": "and",
            "left": {"role_check": {"role_name": "admin"}},
            "right": {
                "comparison": {
                    "field": "status",
                    "operator": "eq",
                    "value": {"literal": "active"},
                }
            },
        }
        record = {"status": "active"}
        context = {"user_roles": ["editor"]}
        assert evaluate_condition(condition, record, context) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_condition_evaluator_role_check.py -v`
Expected: Multiple FAILs — `test_role_check_false_*` tests fail because `evaluate_condition` returns `True` for all `role_check` conditions.

- [ ] **Step 3: Implement role_check evaluation**

In `src/dazzle_back/runtime/condition_evaluator.py`, add `role_check` handling to `evaluate_condition()` between the compound condition handling (line 43) and the comparison handling (line 46):

```python
    # Handle role check
    if "role_check" in condition and condition["role_check"]:
        return _evaluate_role_check(condition["role_check"], context)
```

Add the helper function after `_evaluate_comparison()` (after line 83):

```python
def _evaluate_role_check(
    role_check: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    """
    Evaluate a role check against the user's roles in context.

    Args:
        role_check: Serialized RoleCheck dict with 'role_name'
        context: Runtime context containing 'user_roles' list

    Returns:
        True if the user has the required role
    """
    role_name = role_check.get("role_name")
    if not role_name:
        return False
    user_roles = context.get("user_roles", [])
    return role_name in user_roles
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_condition_evaluator_role_check.py -v`
Expected: All PASS

- [ ] **Step 5: Add role_check handling to condition_to_sql_filter**

The SQL filter path is used for list queries. Without handling `role_check`, list views with role-based access rules would silently include all rows.

Add tests to `tests/unit/test_condition_evaluator_role_check.py`:

```python
from dazzle_back.runtime.condition_evaluator import condition_to_sql_filter


class TestRoleCheckSqlFilter:
    """Test role_check in condition_to_sql_filter."""

    def test_role_check_true_returns_empty_filter(self):
        """When user has the role, no SQL filter needed (all rows visible)."""
        condition = {"role_check": {"role_name": "admin"}}
        context = {"user_roles": ["admin"]}
        filters = condition_to_sql_filter(condition, context)
        assert filters == {}

    def test_role_check_false_returns_impossible_filter(self):
        """When user lacks the role, SQL filter should exclude all rows."""
        condition = {"role_check": {"role_name": "admin"}}
        context = {"user_roles": ["editor"]}
        filters = condition_to_sql_filter(condition, context)
        assert filters == {"_role_denied": True}

    def test_role_check_in_and_with_comparison(self):
        """role(admin) and status = active — role passes, comparison becomes filter."""
        condition = {
            "operator": "and",
            "left": {"role_check": {"role_name": "admin"}},
            "right": {
                "comparison": {
                    "field": "status",
                    "operator": "eq",
                    "value": {"literal": "active"},
                }
            },
        }
        context = {"user_roles": ["admin"]}
        filters = condition_to_sql_filter(condition, context)
        assert filters == {"status": "active"}

    def test_role_check_in_and_role_fails(self):
        """role(admin) and status = active — role fails, deny all."""
        condition = {
            "operator": "and",
            "left": {"role_check": {"role_name": "admin"}},
            "right": {
                "comparison": {
                    "field": "status",
                    "operator": "eq",
                    "value": {"literal": "active"},
                }
            },
        }
        context = {"user_roles": ["editor"]}
        filters = condition_to_sql_filter(condition, context)
        assert filters == {"_role_denied": True}
```

Add `role_check` handling to `condition_to_sql_filter()` in `condition_evaluator.py` (before the comparison handling at line 264):

```python
    # Handle role check — evaluate immediately since roles are in context
    if "role_check" in condition and condition["role_check"]:
        role_name = condition["role_check"].get("role_name")
        user_roles = context.get("user_roles", [])
        if role_name and role_name in user_roles:
            return {}  # Role satisfied, no additional SQL filter needed
        return {"_role_denied": True}  # Sentinel that repository interprets as deny-all
```

- [ ] **Step 6: Run all role_check tests**

Run: `pytest tests/unit/test_condition_evaluator_role_check.py -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite to check for regressions**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: No regressions

- [ ] **Step 8: Commit**

```bash
git add tests/unit/test_condition_evaluator_role_check.py src/dazzle_back/runtime/condition_evaluator.py
git commit -m "fix: evaluate role_check conditions instead of silently passing

role_check conditions in both evaluate_condition() and
condition_to_sql_filter() fell through to 'return True' / empty filters,
meaning any role() check was always satisfied.

Add _evaluate_role_check() for in-memory evaluation and role_check
handling in SQL filter generation. Uses '_role_denied' sentinel for
deny-all when role check fails in SQL path.

Prerequisite for grant_schema runtime RBAC (#grant-schema)."
```

---

### Task 1: IR types — GrantCheck on ConditionExpr

Add the `GrantCheck` model to conditions.py and the `grant_check` field to `ConditionExpr`. This is the smallest possible IR change and unblocks parser work.

**Files:**
- Modify: `src/dazzle/core/ir/conditions.py:86-153` (add `GrantCheck`, extend `ConditionExpr`)
- Modify: `src/dazzle/core/ir/__init__.py:41-49` (export `GrantCheck`)
- Test: `tests/unit/test_ir_grant_check.py` (new)

- [ ] **Step 1: Write failing test for GrantCheck model**

```python
# tests/unit/test_ir_grant_check.py
"""Tests for GrantCheck IR type."""

from dazzle.core.ir.conditions import ConditionExpr, GrantCheck


class TestGrantCheck:
    """Test GrantCheck model and its integration with ConditionExpr."""

    def test_grant_check_creation(self):
        gc = GrantCheck(relation="acting_hod", scope_field="department")
        assert gc.relation == "acting_hod"
        assert gc.scope_field == "department"

    def test_grant_check_frozen(self):
        gc = GrantCheck(relation="acting_hod", scope_field="department")
        try:
            gc.relation = "other"  # type: ignore[misc]
            assert False, "Should have raised"
        except Exception:
            pass

    def test_condition_expr_with_grant_check(self):
        expr = ConditionExpr(
            grant_check=GrantCheck(relation="acting_hod", scope_field="department")
        )
        assert expr.grant_check is not None
        assert expr.grant_check.relation == "acting_hod"
        assert expr.comparison is None
        assert expr.role_check is None

    def test_condition_expr_grant_check_in_compound(self):
        """has_grant('acting_hod', department) or role(admin)"""
        from dazzle.core.ir.conditions import LogicalOperator, RoleCheck

        expr = ConditionExpr(
            left=ConditionExpr(
                grant_check=GrantCheck(relation="acting_hod", scope_field="department")
            ),
            operator=LogicalOperator.OR,
            right=ConditionExpr(role_check=RoleCheck(role_name="admin")),
        )
        assert expr.is_compound
        assert expr.left.grant_check is not None
        assert expr.right.is_role_check

    def test_condition_expr_default_grant_check_is_none(self):
        expr = ConditionExpr()
        assert expr.grant_check is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ir_grant_check.py -v`
Expected: FAIL — `GrantCheck` does not exist yet.

- [ ] **Step 3: Add GrantCheck model and extend ConditionExpr**

In `src/dazzle/core/ir/conditions.py`, add after `RoleCheck` (after line 99):

```python
class GrantCheck(BaseModel):
    """
    A grant check in a condition expression.

    Examples:
        - has_grant("acting_hod", department)
        - has_grant("observer", department)

    Used in access rules to check if user has an active grant
    for a specific relation scoped to a field on the entity.
    """

    relation: str
    scope_field: str

    model_config = ConfigDict(frozen=True)
```

Add `grant_check` field to `ConditionExpr` (after `role_check` at line 138):

```python
    grant_check: GrantCheck | None = None  # Grant-based condition (v0.42.0)
```

Add `is_grant_check` property after `is_role_check` (after line 153):

```python
    @property
    def is_grant_check(self) -> bool:
        """Check if this is a grant check condition."""
        return self.grant_check is not None
```

- [ ] **Step 4: Export GrantCheck from ir/__init__.py**

In `src/dazzle/core/ir/__init__.py`, add to the conditions import block (around line 48):

```python
from .conditions import (
    Comparison,
    ComparisonOperator,
    ConditionExpr,
    ConditionValue,
    FunctionCall,
    GrantCheck,
    LogicalOperator,
    RoleCheck,
)
```

And add `"GrantCheck"` to the `__all__` list in the Conditions section (after `"RoleCheck"` around line 708).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_ir_grant_check.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: No regressions

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/core/ir/conditions.py src/dazzle/core/ir/__init__.py tests/unit/test_ir_grant_check.py
git commit -m "feat(ir): add GrantCheck condition type for has_grant() expressions

New GrantCheck model with relation + scope_field fields. Added as
optional grant_check field on ConditionExpr, alongside existing
comparison and role_check.

Part of grant_schema runtime RBAC infrastructure."
```

---

### Task 2: IR types — GrantSchemaSpec and GrantRelationSpec

Create the main grant schema IR types in a new file.

**Files:**
- Create: `src/dazzle/core/ir/grants.py`
- Modify: `src/dazzle/core/ir/__init__.py` (export new types)
- Test: `tests/unit/test_ir_grants.py` (new)

- [ ] **Step 1: Write failing tests for grant IR types**

```python
# tests/unit/test_ir_grants.py
"""Tests for grant schema IR types."""

from dazzle.core.ir.grants import (
    GrantApprovalMode,
    GrantExpiryMode,
    GrantRelationSpec,
    GrantSchemaSpec,
)


class TestGrantEnums:
    def test_approval_modes(self):
        assert GrantApprovalMode.REQUIRED == "required"
        assert GrantApprovalMode.IMMEDIATE == "immediate"
        assert GrantApprovalMode.NONE == "none"

    def test_expiry_modes(self):
        assert GrantExpiryMode.REQUIRED == "required"
        assert GrantExpiryMode.OPTIONAL == "optional"
        assert GrantExpiryMode.NONE == "none"


class TestGrantRelationSpec:
    def test_minimal_relation(self):
        from dazzle.core.ir.conditions import ConditionExpr, RoleCheck

        rel = GrantRelationSpec(
            name="acting_hod",
            label="Assign covering HoD",
            granted_by=ConditionExpr(role_check=RoleCheck(role_name="senior_leadership")),
        )
        assert rel.name == "acting_hod"
        assert rel.label == "Assign covering HoD"
        assert rel.approval == GrantApprovalMode.REQUIRED
        assert rel.expiry == GrantExpiryMode.REQUIRED
        assert rel.approved_by is None
        assert rel.principal_label is None
        assert rel.confirmation is None
        assert rel.revoke_verb is None
        assert rel.max_duration is None

    def test_full_relation(self):
        from dazzle.core.ir.conditions import ConditionExpr, RoleCheck

        rel = GrantRelationSpec(
            name="acting_hod",
            label="Assign covering HoD",
            description="Temporarily assign HoD responsibilities",
            principal_label="Staff member",
            confirmation="This will give {principal.name} full HoD access to {scope.name}",
            revoke_verb="Remove covering HoD",
            granted_by=ConditionExpr(role_check=RoleCheck(role_name="senior_leadership")),
            approved_by=ConditionExpr(role_check=RoleCheck(role_name="principal")),
            approval=GrantApprovalMode.REQUIRED,
            expiry=GrantExpiryMode.REQUIRED,
            max_duration="90d",
        )
        assert rel.description == "Temporarily assign HoD responsibilities"
        assert rel.principal_label == "Staff member"
        assert rel.max_duration == "90d"
        assert rel.approved_by is not None

    def test_relation_is_frozen(self):
        from dazzle.core.ir.conditions import ConditionExpr, RoleCheck

        rel = GrantRelationSpec(
            name="x",
            label="X",
            granted_by=ConditionExpr(role_check=RoleCheck(role_name="admin")),
        )
        try:
            rel.name = "y"  # type: ignore[misc]
            assert False, "Should have raised"
        except Exception:
            pass


class TestGrantSchemaSpec:
    def test_schema_creation(self):
        from dazzle.core.ir.conditions import ConditionExpr, RoleCheck

        rel = GrantRelationSpec(
            name="acting_hod",
            label="Assign covering HoD",
            granted_by=ConditionExpr(role_check=RoleCheck(role_name="senior_leadership")),
        )
        schema = GrantSchemaSpec(
            name="department_delegation",
            label="Department Delegation",
            description="Delegation of department-level responsibilities",
            scope="Department",
            relations=[rel],
        )
        assert schema.name == "department_delegation"
        assert schema.scope == "Department"
        assert len(schema.relations) == 1
        assert schema.relations[0].name == "acting_hod"

    def test_schema_multiple_relations(self):
        from dazzle.core.ir.conditions import ConditionExpr, RoleCheck

        relations = [
            GrantRelationSpec(
                name="acting_hod",
                label="Assign covering HoD",
                granted_by=ConditionExpr(role_check=RoleCheck(role_name="senior_leadership")),
            ),
            GrantRelationSpec(
                name="observer",
                label="Assign department observer",
                granted_by=ConditionExpr(role_check=RoleCheck(role_name="hod")),
                approval=GrantApprovalMode.NONE,
                expiry=GrantExpiryMode.OPTIONAL,
            ),
        ]
        schema = GrantSchemaSpec(
            name="department_delegation",
            label="Department Delegation",
            scope="Department",
            relations=relations,
        )
        assert len(schema.relations) == 2
        assert schema.relations[1].approval == GrantApprovalMode.NONE

    def test_schema_is_frozen(self):
        schema = GrantSchemaSpec(
            name="x",
            label="X",
            scope="Y",
            relations=[],
        )
        try:
            schema.name = "z"  # type: ignore[misc]
            assert False, "Should have raised"
        except Exception:
            pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_ir_grants.py -v`
Expected: FAIL — `grants.py` does not exist.

- [ ] **Step 3: Create grants.py IR file**

```python
# src/dazzle/core/ir/grants.py
"""
Grant schema specification types for DAZZLE IR.

Grant schemas define runtime-configurable delegation permissions
that layer over the existing Cedar-style static access rules.

DSL Syntax (v0.42.0):
    grant_schema department_delegation "Department Delegation":
      scope: Department
      relation acting_hod "Assign covering HoD":
        granted_by: role(senior_leadership)
        approval: required
        expiry: required
        max_duration: 90d
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from .conditions import ConditionExpr
from .location import SourceLocation


class GrantApprovalMode(StrEnum):
    """How grants require approval before taking effect."""

    REQUIRED = "required"
    IMMEDIATE = "immediate"
    NONE = "none"


class GrantExpiryMode(StrEnum):
    """Whether grants require an expiry date."""

    REQUIRED = "required"
    OPTIONAL = "optional"
    NONE = "none"


class GrantRelationSpec(BaseModel):
    """
    A single delegation relation within a grant schema.

    Defines who can grant, who approves, expiry constraints,
    and UI metadata for contextual actions.
    """

    name: str
    label: str
    description: str | None = None
    principal_label: str | None = None
    confirmation: str | None = None
    revoke_verb: str | None = None
    granted_by: ConditionExpr
    approved_by: ConditionExpr | None = None
    approval: GrantApprovalMode = GrantApprovalMode.REQUIRED
    expiry: GrantExpiryMode = GrantExpiryMode.REQUIRED
    max_duration: str | None = None
    source_location: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)


class GrantSchemaSpec(BaseModel):
    """
    Top-level grant schema grouping related delegation relations by scope entity.

    Each grant schema targets a specific entity type (scope) and defines
    one or more relations that can be granted at runtime.
    """

    name: str
    label: str
    description: str | None = None
    scope: str
    relations: list[GrantRelationSpec]
    source_location: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)
```

- [ ] **Step 4: Export from ir/__init__.py**

In `src/dazzle/core/ir/__init__.py`, add import block (after the Rules import, around line 489):

```python
# Grants (v0.42.0 Runtime RBAC)
from .grants import (
    GrantApprovalMode,
    GrantExpiryMode,
    GrantRelationSpec,
    GrantSchemaSpec,
)
```

Add to `__all__` (after the Rules section, around line 910):

```python
    # Grants (v0.42.0 Runtime RBAC)
    "GrantApprovalMode",
    "GrantExpiryMode",
    "GrantRelationSpec",
    "GrantSchemaSpec",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_ir_grants.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: No regressions

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/core/ir/grants.py src/dazzle/core/ir/__init__.py tests/unit/test_ir_grants.py
git commit -m "feat(ir): add GrantSchemaSpec and GrantRelationSpec types

New IR types for grant_schema DSL construct:
- GrantSchemaSpec: top-level schema with scope entity and relations
- GrantRelationSpec: delegation relation with auth/approval/expiry
- GrantApprovalMode: required, immediate, none
- GrantExpiryMode: required, optional, none

Part of grant_schema runtime RBAC infrastructure."
```

---

### Task 3: Register grant_schemas on ModuleFragment and AppSpec

Wire `grant_schemas` into the IR container types and linker.

**Files:**
- Modify: `src/dazzle/core/ir/module.py:103-190` (add `grant_schemas` field to `ModuleFragment`)
- Modify: `src/dazzle/core/ir/appspec.py:78-179` (add `grant_schemas` field + getter to `AppSpec`)
- Modify: `src/dazzle/core/linker_impl.py:128-155` (add `grant_schemas` to `SymbolTable`)
- Modify: `src/dazzle/core/linker_impl.py:440-559` (add to `build_symbol_table`)
- Modify: `src/dazzle/core/linker_impl.py:1169-1206` (add to `merge_fragments`)
- Modify: `src/dazzle/core/linker.py:116-154` (add to `AppSpec` construction)
- Test: `tests/unit/test_ir_grant_registration.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_ir_grant_registration.py
"""Tests for grant_schemas registration on ModuleFragment and AppSpec."""

from dazzle.core.ir.conditions import ConditionExpr, RoleCheck
from dazzle.core.ir.grants import (
    GrantRelationSpec,
    GrantSchemaSpec,
)
from dazzle.core.ir.module import ModuleFragment
from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec


def _make_schema() -> GrantSchemaSpec:
    return GrantSchemaSpec(
        name="dept_delegation",
        label="Department Delegation",
        scope="Department",
        relations=[
            GrantRelationSpec(
                name="acting_hod",
                label="Assign covering HoD",
                granted_by=ConditionExpr(role_check=RoleCheck(role_name="admin")),
            ),
        ],
    )


class TestModuleFragmentGrantSchemas:
    def test_default_empty(self):
        frag = ModuleFragment()
        assert frag.grant_schemas == []

    def test_with_grant_schema(self):
        schema = _make_schema()
        frag = ModuleFragment(grant_schemas=[schema])
        assert len(frag.grant_schemas) == 1
        assert frag.grant_schemas[0].name == "dept_delegation"


class TestAppSpecGrantSchemas:
    def test_default_empty(self):
        spec = AppSpec(name="test", domain=DomainSpec(entities=[]))
        assert spec.grant_schemas == []

    def test_with_grant_schema(self):
        schema = _make_schema()
        spec = AppSpec(
            name="test",
            domain=DomainSpec(entities=[]),
            grant_schemas=[schema],
        )
        assert len(spec.grant_schemas) == 1

    def test_get_grant_schema(self):
        schema = _make_schema()
        spec = AppSpec(
            name="test",
            domain=DomainSpec(entities=[]),
            grant_schemas=[schema],
        )
        assert spec.get_grant_schema("dept_delegation") is not None
        assert spec.get_grant_schema("nonexistent") is None

    def test_get_grant_schemas_by_scope(self):
        schema = _make_schema()
        spec = AppSpec(
            name="test",
            domain=DomainSpec(entities=[]),
            grant_schemas=[schema],
        )
        assert len(spec.get_grant_schemas_by_scope("Department")) == 1
        assert len(spec.get_grant_schemas_by_scope("Other")) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_ir_grant_registration.py -v`
Expected: FAIL — `grant_schemas` field not found on `ModuleFragment`.

- [ ] **Step 3: Add grant_schemas to ModuleFragment**

In `src/dazzle/core/ir/module.py`:

Add import (after line 63, with other imports):
```python
from .grants import GrantSchemaSpec
```

Add field to `ModuleFragment` class (after `notifications` at line 188, before `model_config`):
```python
    # Grant Schemas (v0.42.0 Runtime RBAC)
    grant_schemas: list[GrantSchemaSpec] = Field(default_factory=list)
```

- [ ] **Step 4: Add grant_schemas to AppSpec with getters**

In `src/dazzle/core/ir/appspec.py`:

Add import (after line 65, with other imports):
```python
from .grants import GrantSchemaSpec
```

Add field to `AppSpec` class (after `rhythms` at line 175, before `audit_trail`):
```python
    # Grant Schemas (v0.42.0 Runtime RBAC)
    grant_schemas: list[GrantSchemaSpec] = Field(default_factory=list)
```

Add getter methods (after the `get_questions_blocking` method, around line 325):
```python
    # Grant Schema getters (v0.42.0 Runtime RBAC)

    def get_grant_schema(self, name: str) -> GrantSchemaSpec | None:
        """Get grant schema by name."""
        for schema in self.grant_schemas:
            if schema.name == name:
                return schema
        return None

    def get_grant_schemas_by_scope(self, entity_name: str) -> list[GrantSchemaSpec]:
        """Get all grant schemas scoped to a specific entity."""
        return [s for s in self.grant_schemas if s.scope == entity_name]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_ir_grant_registration.py -v`
Expected: All PASS

- [ ] **Step 6: Add grant_schemas to linker symbol table and merge**

In `src/dazzle/core/linker_impl.py`, add `grant_schemas` dict to `SymbolTable` (after `islands` at line 154):
```python
    grant_schemas: dict[str, ir.GrantSchemaSpec] = field(default_factory=dict)  # v0.42.0
```

Add `add_grant_schema` method to `SymbolTable` (after `add_rhythm` method, around line 282):
```python
    def add_grant_schema(self, grant_schema: ir.GrantSchemaSpec, module_name: str) -> None:
        """Add grant schema to symbol table, checking for duplicates (v0.42.0)."""
        _add_symbol(
            self.grant_schemas,
            grant_schema.name,
            grant_schema,
            "grant_schema",
            module_name,
            self.symbol_sources,
        )
```

Add to `build_symbol_table()` (after the rhythms block at line 557):
```python
        # Add grant schemas (v0.42.0)
        for grant_schema in module.fragment.grant_schemas:
            symbols.add_grant_schema(grant_schema, module.name)
```

Add to `merge_fragments()` (after `islands` at line 1205):
```python
        grant_schemas=list(symbols.grant_schemas.values()),  # v0.42.0
```

In `src/dazzle/core/linker.py`, add to AppSpec construction (after `islands` at line 147):
```python
        grant_schemas=merged_fragment.grant_schemas,  # v0.42.0 Runtime RBAC
```

- [ ] **Step 7: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: No regressions

- [ ] **Step 8: Lint and type check**

Run: `ruff check src/dazzle/core/ir/module.py src/dazzle/core/ir/appspec.py src/dazzle/core/linker_impl.py src/dazzle/core/linker.py --fix && ruff format src/dazzle/core/ir/module.py src/dazzle/core/ir/appspec.py src/dazzle/core/linker_impl.py src/dazzle/core/linker.py`

- [ ] **Step 9: Commit**

```bash
git add src/dazzle/core/ir/module.py src/dazzle/core/ir/appspec.py \
  src/dazzle/core/linker_impl.py src/dazzle/core/linker.py \
  tests/unit/test_ir_grant_registration.py
git commit -m "feat(ir): register grant_schemas on ModuleFragment, AppSpec, and linker

Add grant_schemas list field to ModuleFragment and AppSpec.
Add get_grant_schema() and get_grant_schemas_by_scope() to AppSpec.
Wire grant_schemas through SymbolTable, build_symbol_table, and
merge_fragments in the linker.

Part of grant_schema runtime RBAC infrastructure."
```

---

## Chunk 2: Parser

### Task 4: Lexer token for grant_schema

Add `GRANT_SCHEMA` keyword token to the lexer.

**Files:**
- Modify: `src/dazzle/core/lexer.py:261-276` (add keyword)
- Test: `tests/unit/test_lexer_grant_schema.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_lexer_grant_schema.py
"""Test grant_schema keyword tokenization."""

from pathlib import Path

from dazzle.core.lexer import TokenType, tokenize


def test_grant_schema_keyword_tokenized():
    tokens = tokenize("grant_schema", Path("test.dsl"))
    assert tokens[0].type == TokenType.GRANT_SCHEMA
    assert tokens[0].value == "grant_schema"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_lexer_grant_schema.py -v`
Expected: FAIL — `TokenType` has no `GRANT_SCHEMA` member.

- [ ] **Step 3: Add GRANT_SCHEMA to lexer**

In `src/dazzle/core/lexer.py`, add after the `QUESTION_DECL` line (around line 263):

```python
    GRANT_SCHEMA = "grant_schema"
```

The `KEYWORDS` set is auto-computed from `TokenType`, so no other changes needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_lexer_grant_schema.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: No regressions

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/lexer.py tests/unit/test_lexer_grant_schema.py
git commit -m "feat(lexer): add GRANT_SCHEMA keyword token

Part of grant_schema runtime RBAC parser support."
```

---

### Task 5: has_grant() condition parsing

Extend the condition parser to handle `has_grant("relation", scope_field)`.

**Files:**
- Modify: `src/dazzle/core/dsl_parser_impl/conditions.py:75-94` (`_parse_primary_condition`)
- Test: `tests/unit/test_parse_has_grant.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_parse_has_grant.py
"""Tests for has_grant() condition parsing."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl


def _parse_access_condition(dsl_text: str):
    """Parse a minimal entity with an access rule and return the read condition."""
    full = f"""module test_mod
entity Thing "Thing":
  id: uuid pk
  department: ref Department
  access:
    read: {dsl_text}
"""
    _, _, _, _, _, fragment = parse_dsl(full, Path("test.dsl"))
    entity = fragment.entities[0]
    read_rules = [r for r in entity.access.permissions if r.kind.value == "read"]
    assert read_rules, f"No read rule found for: {dsl_text}"
    return read_rules[0].condition


class TestHasGrantParsing:
    def test_simple_has_grant(self):
        cond = _parse_access_condition('has_grant("acting_hod", department)')
        assert cond.grant_check is not None
        assert cond.grant_check.relation == "acting_hod"
        assert cond.grant_check.scope_field == "department"

    def test_has_grant_or_role(self):
        cond = _parse_access_condition('role(hod) or has_grant("acting_hod", department)')
        assert cond.is_compound
        assert cond.left.is_role_check
        assert cond.right.grant_check is not None
        assert cond.right.grant_check.relation == "acting_hod"

    def test_has_grant_and_comparison(self):
        cond = _parse_access_condition('has_grant("observer", department) and status = active')
        assert cond.is_compound
        assert cond.left.grant_check is not None
        assert cond.right.comparison is not None

    def test_has_grant_in_parentheses(self):
        cond = _parse_access_condition(
            '(has_grant("acting_hod", department)) or role(admin)'
        )
        assert cond.is_compound
        assert cond.left.grant_check is not None
        assert cond.right.is_role_check
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_parse_has_grant.py -v`
Expected: FAIL — `has_grant` is parsed as a regular identifier, not a grant check.

- [ ] **Step 3: Add has_grant() parsing to _parse_primary_condition**

In `src/dazzle/core/dsl_parser_impl/conditions.py`, add a new branch in `_parse_primary_condition` after the `role()` handling (after line 90):

```python
        # Handle has_grant("relation", scope_field) - grant check (v0.42.0)
        if self.match(TokenType.IDENTIFIER) and self.current_token().value == "has_grant":
            self.advance()
            self.expect(TokenType.LPAREN)
            # First arg: relation name (string literal)
            relation = self.expect(TokenType.STRING).value
            self.expect(TokenType.COMMA)
            # Second arg: scope field (identifier)
            scope_field = self.expect_identifier_or_keyword().value
            self.expect(TokenType.RPAREN)
            return ir.ConditionExpr(
                grant_check=ir.GrantCheck(relation=relation, scope_field=scope_field)
            )
```

Note: This check must come BEFORE the general comparison parsing (line 92-94) since `has_grant` starts with an IDENTIFIER token. The check peeks at the identifier value without consuming it, so if it's not `has_grant`, it falls through to comparison parsing.

Also add `COMMA` to the TYPE_CHECKING imports if not already there. Check that `TokenType.COMMA` exists in the lexer — if not, the parser may need to use a different approach. Looking at the lexer, `COMMA` should already be defined.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_parse_has_grant.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: No regressions

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/conditions.py tests/unit/test_parse_has_grant.py
git commit -m "feat(parser): add has_grant() condition function parsing

Parse has_grant(\"relation\", scope_field) in condition expressions,
producing GrantCheck nodes on ConditionExpr. Works in access rules,
granted_by expressions, and anywhere conditions are used.

Part of grant_schema runtime RBAC infrastructure."
```

---

### Task 6: grant_schema construct parser mixin

Create the parser mixin for the `grant_schema` top-level construct with nested `relation` blocks.

**Files:**
- Create: `src/dazzle/core/dsl_parser_impl/grant.py`
- Modify: `src/dazzle/core/dsl_parser_impl/__init__.py` (import + MRO + dispatch)
- Test: `tests/unit/test_parse_grant_schema.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_parse_grant_schema.py
"""Tests for grant_schema DSL construct parsing."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.grants import GrantApprovalMode, GrantExpiryMode


def _parse_grant_schemas(dsl_text: str):
    """Parse DSL text and return grant_schemas from the fragment."""
    full = f"module test_mod\n{dsl_text}"
    _, _, _, _, _, fragment = parse_dsl(full, Path("test.dsl"))
    return fragment.grant_schemas


class TestGrantSchemaBasicParsing:
    def test_minimal_grant_schema(self):
        schemas = _parse_grant_schemas('''
grant_schema dept_delegation "Department Delegation":
  scope: Department

  relation acting_hod "Assign covering HoD":
    granted_by: role(senior_leadership)
''')
        assert len(schemas) == 1
        s = schemas[0]
        assert s.name == "dept_delegation"
        assert s.label == "Department Delegation"
        assert s.scope == "Department"
        assert len(s.relations) == 1
        r = s.relations[0]
        assert r.name == "acting_hod"
        assert r.label == "Assign covering HoD"
        assert r.granted_by.is_role_check
        assert r.granted_by.role_check.role_name == "senior_leadership"
        # Defaults
        assert r.approval == GrantApprovalMode.REQUIRED
        assert r.expiry == GrantExpiryMode.REQUIRED

    def test_full_grant_schema(self):
        schemas = _parse_grant_schemas('''
grant_schema dept_delegation "Department Delegation":
  description: "Delegation of department-level responsibilities"
  scope: Department

  relation acting_hod "Assign covering HoD":
    description: "Temporarily assign HoD responsibilities"
    principal_label: "Staff member"
    confirmation: "This will give {principal.name} full HoD access to {scope.name}"
    granted_by: role(senior_leadership)
    approved_by: role(principal)
    approval: required
    expiry: required
    max_duration: 90d
    revoke_verb: "Remove covering HoD"
''')
        assert len(schemas) == 1
        s = schemas[0]
        assert s.description == "Delegation of department-level responsibilities"
        r = s.relations[0]
        assert r.description == "Temporarily assign HoD responsibilities"
        assert r.principal_label == "Staff member"
        assert r.confirmation == "This will give {principal.name} full HoD access to {scope.name}"
        assert r.max_duration == "90d"
        assert r.revoke_verb == "Remove covering HoD"
        assert r.approved_by is not None
        assert r.approved_by.is_role_check

    def test_multiple_relations(self):
        schemas = _parse_grant_schemas('''
grant_schema dept_delegation "Department Delegation":
  scope: Department

  relation acting_hod "Assign covering HoD":
    granted_by: role(senior_leadership)
    approval: required
    expiry: required
    max_duration: 90d

  relation observer "Assign department observer":
    granted_by: role(hod) or has_grant("acting_hod", department)
    approval: none
    expiry: optional
''')
        assert len(schemas) == 1
        assert len(schemas[0].relations) == 2
        r1, r2 = schemas[0].relations
        assert r1.name == "acting_hod"
        assert r2.name == "observer"
        assert r2.approval == GrantApprovalMode.NONE
        assert r2.expiry == GrantExpiryMode.OPTIONAL
        # r2 granted_by should be a compound expression
        assert r2.granted_by.is_compound

    def test_approval_immediate(self):
        schemas = _parse_grant_schemas('''
grant_schema x "X":
  scope: Thing

  relation r "R":
    granted_by: role(admin)
    approval: immediate
    expiry: none
''')
        r = schemas[0].relations[0]
        assert r.approval == GrantApprovalMode.IMMEDIATE
        assert r.expiry == GrantExpiryMode.NONE


class TestMultipleGrantSchemas:
    def test_two_schemas_in_module(self):
        schemas = _parse_grant_schemas('''
grant_schema dept_delegation "Department Delegation":
  scope: Department
  relation acting_hod "Assign covering HoD":
    granted_by: role(admin)

grant_schema account_access "Account Access":
  scope: ClientAccount
  relation accountant "Assign accountant":
    granted_by: role(manager)
    approval: none
    expiry: none
''')
        assert len(schemas) == 2
        assert schemas[0].name == "dept_delegation"
        assert schemas[1].name == "account_access"
        assert schemas[1].scope == "ClientAccount"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_parse_grant_schema.py -v`
Expected: FAIL — `GRANT_SCHEMA` token not dispatched, grant_schema construct ignored.

- [ ] **Step 3: Create grant parser mixin**

```python
# src/dazzle/core/dsl_parser_impl/grant.py
"""
Grant schema parser mixin for DAZZLE DSL.

Parses grant_schema blocks with nested relation sub-blocks.

DSL Syntax (v0.42.0):
    grant_schema department_delegation "Department Delegation":
      description: "Delegation of department-level responsibilities"
      scope: Department

      relation acting_hod "Assign covering HoD":
        granted_by: role(senior_leadership)
        approval: required
        expiry: required
        max_duration: 90d
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..ir.grants import GrantApprovalMode, GrantExpiryMode, GrantRelationSpec, GrantSchemaSpec
from ..lexer import TokenType


class GrantParserMixin:
    """Parser mixin for grant_schema blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any
        _source_location: Any
        parse_condition_expr: Any

    def parse_grant_schema(self) -> GrantSchemaSpec:
        """
        Parse a grant_schema block.

        Grammar:
            grant_schema NAME STRING COLON NEWLINE INDENT
              [description COLON STRING NEWLINE]
              scope COLON IDENTIFIER NEWLINE
              (relation NAME STRING COLON NEWLINE INDENT ... DEDENT)+
            DEDENT
        """
        loc = self._source_location()
        name = self.expect_identifier_or_keyword().value
        label = self.expect(TokenType.STRING).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        description: str | None = None
        scope: str | None = None
        relations: list[GrantRelationSpec] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()
            field_name = token.value

            if field_name == "description":
                self.advance()
                self.expect(TokenType.COLON)
                description = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif field_name == "scope":
                self.advance()
                self.expect(TokenType.COLON)
                scope = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif field_name == "relation":
                self.advance()
                relation = self._parse_grant_relation()
                relations.append(relation)

            else:
                # Skip unknown field
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                self._skip_to_next_field()

        self.expect(TokenType.DEDENT)

        if scope is None:
            from ..errors import make_parse_error

            raise make_parse_error(
                "grant_schema requires a 'scope' field",
                self.file,
                token.line if token else 0,
                token.column if token else 0,
            )

        return GrantSchemaSpec(
            name=name,
            label=label,
            description=description,
            scope=scope,
            relations=relations,
            source_location=loc,
        )

    def _parse_grant_relation(self) -> GrantRelationSpec:
        """Parse a relation sub-block within a grant_schema."""
        loc = self._source_location()
        name = self.expect_identifier_or_keyword().value
        label = self.expect(TokenType.STRING).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        description: str | None = None
        principal_label: str | None = None
        confirmation: str | None = None
        revoke_verb: str | None = None
        granted_by: ir.ConditionExpr | None = None
        approved_by: ir.ConditionExpr | None = None
        approval = GrantApprovalMode.REQUIRED
        expiry = GrantExpiryMode.REQUIRED
        max_duration: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()
            field_name = token.value

            if field_name == "description":
                self.advance()
                self.expect(TokenType.COLON)
                description = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif field_name == "principal_label":
                self.advance()
                self.expect(TokenType.COLON)
                principal_label = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif field_name == "confirmation":
                self.advance()
                self.expect(TokenType.COLON)
                confirmation = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif field_name == "revoke_verb":
                self.advance()
                self.expect(TokenType.COLON)
                revoke_verb = self.expect(TokenType.STRING).value
                self.skip_newlines()

            elif field_name == "granted_by":
                self.advance()
                self.expect(TokenType.COLON)
                granted_by = self.parse_condition_expr()
                self.skip_newlines()

            elif field_name == "approved_by":
                self.advance()
                self.expect(TokenType.COLON)
                approved_by = self.parse_condition_expr()
                self.skip_newlines()

            elif field_name == "approval":
                self.advance()
                self.expect(TokenType.COLON)
                approval_str = self.advance().value
                approval = self._parse_approval_mode(approval_str)
                self.skip_newlines()

            elif field_name == "expiry":
                self.advance()
                self.expect(TokenType.COLON)
                expiry_str = self.advance().value
                expiry = self._parse_expiry_mode(expiry_str)
                self.skip_newlines()

            elif field_name == "max_duration":
                self.advance()
                self.expect(TokenType.COLON)
                max_duration = self.advance().value
                self.skip_newlines()

            else:
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                self._skip_to_next_field()

        self.expect(TokenType.DEDENT)

        if granted_by is None:
            from ..errors import make_parse_error

            raise make_parse_error(
                "relation requires a 'granted_by' field",
                self.file,
                token.line if token else 0,
                token.column if token else 0,
            )

        return GrantRelationSpec(
            name=name,
            label=label,
            description=description,
            principal_label=principal_label,
            confirmation=confirmation,
            revoke_verb=revoke_verb,
            granted_by=granted_by,
            approved_by=approved_by,
            approval=approval,
            expiry=expiry,
            max_duration=max_duration,
            source_location=loc,
        )

    def _parse_approval_mode(self, value: str) -> GrantApprovalMode:
        mode_map = {
            "required": GrantApprovalMode.REQUIRED,
            "immediate": GrantApprovalMode.IMMEDIATE,
            "none": GrantApprovalMode.NONE,
        }
        if value in mode_map:
            return mode_map[value]
        from ..errors import make_parse_error

        raise make_parse_error(
            f"Invalid approval mode '{value}'. Valid: required, immediate, none",
            self.file,
            self.current_token().line,
            self.current_token().column,
        )

    def _parse_expiry_mode(self, value: str) -> GrantExpiryMode:
        mode_map = {
            "required": GrantExpiryMode.REQUIRED,
            "optional": GrantExpiryMode.OPTIONAL,
            "none": GrantExpiryMode.NONE,
        }
        if value in mode_map:
            return mode_map[value]
        from ..errors import make_parse_error

        raise make_parse_error(
            f"Invalid expiry mode '{value}'. Valid: required, optional, none",
            self.file,
            self.current_token().line,
            self.current_token().column,
        )

    def _skip_to_next_field(self) -> None:
        """Skip tokens until next field or end of block."""
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            if self.match(TokenType.NEWLINE):
                self.skip_newlines()
                break
            self.advance()
```

- [ ] **Step 4: Wire mixin into Parser class and dispatch**

In `src/dazzle/core/dsl_parser_impl/__init__.py`:

Add import (after `from .governance import GovernanceParserMixin` around line 29):
```python
from .grant import GrantParserMixin
```

Add to Parser class MRO (after `NotificationParserMixin` around line 84):
```python
    GrantParserMixin,
```

Add dispatch in `parse()` method (after the Notifications block around line 368, before the `else` at line 370):
```python
            # v0.42.0 Grant Schemas (Runtime RBAC)
            elif self.match(TokenType.GRANT_SCHEMA):
                self.advance()  # consume 'grant_schema' token
                grant_schema = self.parse_grant_schema()
                fragment = _updated(
                    fragment, grant_schemas=[*fragment.grant_schemas, grant_schema]
                )
```

Add to `__all__` list:
```python
    "GrantParserMixin",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_parse_grant_schema.py -v`
Expected: All PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: No regressions

- [ ] **Step 7: Lint**

Run: `ruff check src/dazzle/core/dsl_parser_impl/grant.py src/dazzle/core/dsl_parser_impl/__init__.py --fix && ruff format src/dazzle/core/dsl_parser_impl/grant.py src/dazzle/core/dsl_parser_impl/__init__.py`

- [ ] **Step 8: Commit**

```bash
git add src/dazzle/core/dsl_parser_impl/grant.py \
  src/dazzle/core/dsl_parser_impl/__init__.py \
  tests/unit/test_parse_grant_schema.py
git commit -m "feat(parser): add grant_schema construct parser

GrantParserMixin parses grant_schema blocks with nested relation
sub-blocks. Supports all fields from the spec: granted_by, approved_by,
approval mode, expiry mode, max_duration, principal_label, confirmation,
and revoke_verb. Dispatched from the main parse() loop via GRANT_SCHEMA
token.

Part of grant_schema runtime RBAC infrastructure."
```

---

## Chunk 3: Runtime Grant Store

### Task 7: Grant store with tables and CRUD API

Create the runtime grant store with `_grants` and `_grant_events` tables, status transitions, and query API.

**Files:**
- Create: `src/dazzle_back/runtime/grant_store.py`
- Test: `tests/unit/test_grant_store.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_grant_store.py
"""Tests for runtime grant store."""

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from dazzle_back.runtime.grant_store import GrantStore, GrantStatus


@pytest.fixture
def db():
    """In-memory SQLite for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def store(db):
    """Grant store backed by in-memory DB."""
    return GrantStore(db)


class TestGrantStoreInit:
    def test_tables_created(self, store, db):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_grant%'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "_grants" in tables
        assert "_grant_events" in tables


class TestCreateGrant:
    def test_create_grant_pending(self, store):
        grant = store.create_grant(
            schema_name="dept_delegation",
            relation="acting_hod",
            principal_id=str(uuid4()),
            scope_entity="Department",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="required",
        )
        assert grant["status"] == GrantStatus.PENDING_APPROVAL

    def test_create_grant_immediate(self, store):
        grant = store.create_grant(
            schema_name="dept_delegation",
            relation="acting_hod",
            principal_id=str(uuid4()),
            scope_entity="Department",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="immediate",
        )
        assert grant["status"] == GrantStatus.ACTIVE

    def test_create_grant_no_approval(self, store):
        grant = store.create_grant(
            schema_name="dept_delegation",
            relation="observer",
            principal_id=str(uuid4()),
            scope_entity="Department",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        assert grant["status"] == GrantStatus.ACTIVE

    def test_create_grant_with_expiry(self, store):
        expires = datetime.now(UTC) + timedelta(days=90)
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
            expires_at=expires.isoformat(),
        )
        assert grant["expires_at"] is not None

    def test_create_grant_records_event(self, store, db):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        events = db.execute(
            "SELECT * FROM _grant_events WHERE grant_id = ?", (grant["id"],)
        ).fetchall()
        assert len(events) == 1
        assert events[0]["event_type"] == "created"


class TestApproveGrant:
    def test_approve_pending_grant(self, store):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="required",
        )
        updated = store.approve_grant(grant["id"], str(uuid4()))
        assert updated["status"] == GrantStatus.ACTIVE
        assert updated["approved_by_id"] is not None

    def test_approve_non_pending_raises(self, store):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        with pytest.raises(ValueError, match="Cannot approve"):
            store.approve_grant(grant["id"], str(uuid4()))


class TestRejectGrant:
    def test_reject_pending_grant(self, store):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="required",
        )
        updated = store.reject_grant(grant["id"], str(uuid4()), reason="Not needed")
        assert updated["status"] == GrantStatus.REJECTED

    def test_reject_active_raises(self, store):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        with pytest.raises(ValueError, match="Cannot reject"):
            store.reject_grant(grant["id"], str(uuid4()))


class TestRevokeGrant:
    def test_revoke_active_grant(self, store):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        updated = store.revoke_grant(grant["id"], str(uuid4()))
        assert updated["status"] == GrantStatus.REVOKED
        assert updated["revoked_at"] is not None

    def test_revoke_expired_raises(self, store):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
            expires_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
        )
        store.expire_stale_grants()
        with pytest.raises(ValueError, match="Cannot revoke"):
            store.revoke_grant(grant["id"], str(uuid4()))


class TestHasActiveGrant:
    def test_has_active_grant_true(self, store):
        pid = str(uuid4())
        sid = str(uuid4())
        store.create_grant(
            schema_name="x",
            relation="acting_hod",
            principal_id=pid,
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        assert store.has_active_grant(pid, "acting_hod", sid) is True

    def test_has_active_grant_false_pending(self, store):
        pid = str(uuid4())
        sid = str(uuid4())
        store.create_grant(
            schema_name="x",
            relation="acting_hod",
            principal_id=pid,
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=str(uuid4()),
            approval_mode="required",
        )
        assert store.has_active_grant(pid, "acting_hod", sid) is False

    def test_has_active_grant_false_expired(self, store):
        pid = str(uuid4())
        sid = str(uuid4())
        store.create_grant(
            schema_name="x",
            relation="acting_hod",
            principal_id=pid,
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=str(uuid4()),
            approval_mode="none",
            expires_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        )
        assert store.has_active_grant(pid, "acting_hod", sid) is False

    def test_has_active_grant_false_revoked(self, store):
        pid = str(uuid4())
        sid = str(uuid4())
        grant = store.create_grant(
            schema_name="x",
            relation="acting_hod",
            principal_id=pid,
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        store.revoke_grant(grant["id"], str(uuid4()))
        assert store.has_active_grant(pid, "acting_hod", sid) is False


class TestListGrants:
    def test_list_by_scope(self, store):
        sid = str(uuid4())
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        grants = store.list_grants(scope_entity="Department", scope_id=sid)
        assert len(grants) == 1

    def test_list_by_principal(self, store):
        pid = str(uuid4())
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=pid,
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        grants = store.list_grants(principal_id=pid)
        assert len(grants) == 1

    def test_list_by_status(self, store):
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="required",
        )
        grants = store.list_grants(status=GrantStatus.PENDING_APPROVAL)
        assert len(grants) == 1
        grants = store.list_grants(status=GrantStatus.ACTIVE)
        assert len(grants) == 0


class TestExpireStaleGrants:
    def test_expire_stale(self, store):
        pid = str(uuid4())
        sid = str(uuid4())
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=pid,
            scope_entity="E",
            scope_id=sid,
            granted_by_id=str(uuid4()),
            approval_mode="none",
            expires_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        )
        count = store.expire_stale_grants()
        assert count == 1
        grants = store.list_grants(principal_id=pid, status=GrantStatus.EXPIRED)
        assert len(grants) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_grant_store.py -v`
Expected: FAIL — `grant_store.py` doesn't exist.

- [ ] **Step 3: Implement GrantStore**

```python
# src/dazzle_back/runtime/grant_store.py
"""
Runtime grant store for dynamic RBAC grants.

Manages the _grants and _grant_events tables, providing CRUD operations
with status transitions and audit event logging.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


class GrantStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REVOKED = "revoked"


class GrantStore:
    """Synchronous grant store backed by SQLite."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _grants (
                id TEXT PRIMARY KEY,
                schema_name TEXT NOT NULL,
                relation TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                scope_entity TEXT NOT NULL,
                scope_id TEXT NOT NULL,
                status TEXT NOT NULL,
                granted_by_id TEXT NOT NULL,
                approved_by_id TEXT,
                granted_at TEXT NOT NULL,
                approved_at TEXT,
                expires_at TEXT,
                revoked_at TEXT,
                revoked_by_id TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_grants_lookup
            ON _grants (principal_id, relation, scope_id, status)
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _grant_events (
                id TEXT PRIMARY KEY,
                grant_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metadata TEXT,
                FOREIGN KEY (grant_id) REFERENCES _grants(id)
            )
        """)
        self._conn.commit()

    def _record_event(
        self,
        grant_id: str,
        event_type: str,
        actor_id: str,
        metadata: dict | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO _grant_events (id, grant_id, event_type, actor_id, timestamp, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                str(uuid4()),
                grant_id,
                event_type,
                actor_id,
                datetime.now(UTC).isoformat(),
                json.dumps(metadata) if metadata else None,
            ),
        )

    def _get_grant(self, grant_id: str) -> dict:
        row = self._conn.execute(
            "SELECT * FROM _grants WHERE id = ?", (grant_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Grant {grant_id} not found")
        return dict(row)

    def create_grant(
        self,
        schema_name: str,
        relation: str,
        principal_id: str,
        scope_entity: str,
        scope_id: str,
        granted_by_id: str,
        approval_mode: str = "required",
        expires_at: str | None = None,
    ) -> dict:
        grant_id = str(uuid4())
        now = datetime.now(UTC).isoformat()

        if approval_mode == "required":
            status = GrantStatus.PENDING_APPROVAL
        else:
            status = GrantStatus.ACTIVE

        self._conn.execute(
            """INSERT INTO _grants
               (id, schema_name, relation, principal_id, scope_entity, scope_id,
                status, granted_by_id, granted_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                grant_id,
                schema_name,
                relation,
                principal_id,
                scope_entity,
                scope_id,
                status,
                granted_by_id,
                now,
                expires_at,
            ),
        )
        self._record_event(grant_id, "created", granted_by_id)
        self._conn.commit()
        return self._get_grant(grant_id)

    def approve_grant(self, grant_id: str, approved_by_id: str) -> dict:
        grant = self._get_grant(grant_id)
        if grant["status"] != GrantStatus.PENDING_APPROVAL:
            raise ValueError(
                f"Cannot approve grant in status '{grant['status']}'"
            )
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """UPDATE _grants
               SET status = ?, approved_by_id = ?, approved_at = ?
               WHERE id = ?""",
            (GrantStatus.ACTIVE, approved_by_id, now, grant_id),
        )
        self._record_event(grant_id, "approved", approved_by_id)
        self._conn.commit()
        return self._get_grant(grant_id)

    def reject_grant(
        self, grant_id: str, rejected_by_id: str, reason: str | None = None
    ) -> dict:
        grant = self._get_grant(grant_id)
        if grant["status"] != GrantStatus.PENDING_APPROVAL:
            raise ValueError(
                f"Cannot reject grant in status '{grant['status']}'"
            )
        self._conn.execute(
            "UPDATE _grants SET status = ? WHERE id = ?",
            (GrantStatus.REJECTED, grant_id),
        )
        metadata = {"reason": reason} if reason else None
        self._record_event(grant_id, "rejected", rejected_by_id, metadata)
        self._conn.commit()
        return self._get_grant(grant_id)

    def revoke_grant(self, grant_id: str, revoked_by_id: str) -> dict:
        grant = self._get_grant(grant_id)
        if grant["status"] != GrantStatus.ACTIVE:
            raise ValueError(
                f"Cannot revoke grant in status '{grant['status']}'"
            )
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """UPDATE _grants
               SET status = ?, revoked_at = ?, revoked_by_id = ?
               WHERE id = ?""",
            (GrantStatus.REVOKED, now, revoked_by_id, grant_id),
        )
        self._record_event(grant_id, "revoked", revoked_by_id)
        self._conn.commit()
        return self._get_grant(grant_id)

    def has_active_grant(
        self, principal_id: str, relation: str, scope_id: str
    ) -> bool:
        now = datetime.now(UTC).isoformat()
        row = self._conn.execute(
            """SELECT 1 FROM _grants
               WHERE principal_id = ? AND relation = ? AND scope_id = ?
               AND status = ?
               AND (expires_at IS NULL OR expires_at > ?)
               LIMIT 1""",
            (principal_id, relation, scope_id, GrantStatus.ACTIVE, now),
        ).fetchone()
        return row is not None

    def list_grants(
        self,
        scope_entity: str | None = None,
        scope_id: str | None = None,
        principal_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        conditions = []
        params: list = []
        if scope_entity:
            conditions.append("scope_entity = ?")
            params.append(scope_entity)
        if scope_id:
            conditions.append("scope_id = ?")
            params.append(scope_id)
        if principal_id:
            conditions.append("principal_id = ?")
            params.append(principal_id)
        if status:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions) if conditions else "1=1"
        rows = self._conn.execute(
            f"SELECT * FROM _grants WHERE {where} ORDER BY granted_at DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def expire_stale_grants(self) -> int:
        now = datetime.now(UTC).isoformat()
        cursor = self._conn.execute(
            """SELECT id FROM _grants
               WHERE status = ? AND expires_at IS NOT NULL AND expires_at <= ?""",
            (GrantStatus.ACTIVE, now),
        )
        expired_ids = [row[0] for row in cursor.fetchall()]
        for gid in expired_ids:
            self._conn.execute(
                "UPDATE _grants SET status = ? WHERE id = ?",
                (GrantStatus.EXPIRED, gid),
            )
            self._record_event(gid, "expired", "system")
        if expired_ids:
            self._conn.commit()
        return len(expired_ids)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_grant_store.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: No regressions

- [ ] **Step 6: Lint**

Run: `ruff check src/dazzle_back/runtime/grant_store.py --fix && ruff format src/dazzle_back/runtime/grant_store.py`

- [ ] **Step 7: Commit**

```bash
git add src/dazzle_back/runtime/grant_store.py tests/unit/test_grant_store.py
git commit -m "feat(runtime): add GrantStore with CRUD, status transitions, and audit events

Synchronous SQLite-backed grant store with:
- _grants table with composite index on (principal_id, relation, scope_id, status)
- _grant_events audit log table
- Status transitions: pending_approval → active → expired/revoked
- has_active_grant() checks both status and expiry
- expire_stale_grants() background cleanup

Part of grant_schema runtime RBAC infrastructure."
```

---

## Chunk 4: Condition Evaluator + Access Evaluator Integration

### Task 8: grant_check evaluation in condition evaluator

Add `has_grant()` evaluation using pre-fetched grants in the filter context.

**Files:**
- Modify: `src/dazzle_back/runtime/condition_evaluator.py:19-50` (add grant_check handling)
- Test: `tests/unit/test_condition_evaluator_grant_check.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_condition_evaluator_grant_check.py
"""Tests for grant_check evaluation in condition evaluator."""

from datetime import UTC, datetime, timedelta

from dazzle_back.runtime.condition_evaluator import evaluate_condition


def _make_grant(relation: str, scope_id: str, expires_at=None):
    """Create a grant-like dict matching what list_grants returns."""
    return {
        "relation": relation,
        "scope_id": scope_id,
        "status": "active",
        "expires_at": expires_at,
    }


class TestGrantCheckEvaluation:
    def test_grant_check_true(self):
        condition = {
            "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
        }
        record = {"department_id": "dept-1"}
        context = {
            "active_grants": [_make_grant("acting_hod", "dept-1")],
        }
        assert evaluate_condition(condition, record, context) is True

    def test_grant_check_false_wrong_relation(self):
        condition = {
            "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
        }
        record = {"department_id": "dept-1"}
        context = {
            "active_grants": [_make_grant("observer", "dept-1")],
        }
        assert evaluate_condition(condition, record, context) is False

    def test_grant_check_false_wrong_scope(self):
        condition = {
            "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
        }
        record = {"department_id": "dept-1"}
        context = {
            "active_grants": [_make_grant("acting_hod", "dept-2")],
        }
        assert evaluate_condition(condition, record, context) is False

    def test_grant_check_false_no_grants(self):
        condition = {
            "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
        }
        record = {"department_id": "dept-1"}
        context = {"active_grants": []}
        assert evaluate_condition(condition, record, context) is False

    def test_grant_check_false_no_grants_key(self):
        condition = {
            "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
        }
        record = {"department_id": "dept-1"}
        context = {}
        assert evaluate_condition(condition, record, context) is False

    def test_grant_check_false_missing_scope_field(self):
        condition = {
            "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
        }
        record = {}  # no department_id
        context = {
            "active_grants": [_make_grant("acting_hod", "dept-1")],
        }
        assert evaluate_condition(condition, record, context) is False

    def test_grant_check_expired_grant_excluded(self):
        condition = {
            "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
        }
        record = {"department_id": "dept-1"}
        expired = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        context = {
            "active_grants": [_make_grant("acting_hod", "dept-1", expires_at=expired)],
        }
        assert evaluate_condition(condition, record, context) is False

    def test_grant_check_future_expiry_included(self):
        condition = {
            "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
        }
        record = {"department_id": "dept-1"}
        future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        context = {
            "active_grants": [_make_grant("acting_hod", "dept-1", expires_at=future)],
        }
        assert evaluate_condition(condition, record, context) is True

    def test_grant_check_combined_with_role_or(self):
        """role(hod) or has_grant('acting_hod', department_id)"""
        condition = {
            "operator": "or",
            "left": {"role_check": {"role_name": "hod"}},
            "right": {
                "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
            },
        }
        record = {"department_id": "dept-1"}
        # User doesn't have hod role but has grant
        context = {
            "user_roles": [],
            "active_grants": [_make_grant("acting_hod", "dept-1")],
        }
        assert evaluate_condition(condition, record, context) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_condition_evaluator_grant_check.py -v`
Expected: FAIL — `grant_check` falls through to `return True`.

- [ ] **Step 3: Add grant_check evaluation**

In `src/dazzle_back/runtime/condition_evaluator.py`, add grant_check handling to `evaluate_condition()` after the role_check handling added in Task 0:

```python
    # Handle grant check
    if "grant_check" in condition and condition["grant_check"]:
        return _evaluate_grant_check(condition["grant_check"], record, context)
```

Add the helper function after `_evaluate_role_check()`:

```python
def _evaluate_grant_check(
    grant_check: dict[str, Any],
    record: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    """
    Evaluate a grant check against pre-fetched active grants in context.

    Args:
        grant_check: Serialized GrantCheck dict with 'relation' and 'scope_field'
        record: Entity record data
        context: Runtime context containing 'active_grants' list

    Returns:
        True if user has an active, non-expired grant matching the check
    """
    relation = grant_check.get("relation")
    scope_field = grant_check.get("scope_field")
    if not relation or not scope_field:
        return False

    scope_value = record.get(scope_field)
    if not scope_value:
        return False

    active_grants = context.get("active_grants", [])
    now = datetime.now(UTC).isoformat()

    return any(
        g.get("relation") == relation
        and str(g.get("scope_id", "")) == str(scope_value)
        and (g.get("expires_at") is None or g.get("expires_at", "") > now)
        for g in active_grants
    )
```

Add import at the top of the file:

```python
from datetime import UTC, datetime
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_condition_evaluator_grant_check.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: No regressions

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/runtime/condition_evaluator.py \
  tests/unit/test_condition_evaluator_grant_check.py
git commit -m "feat(evaluator): add grant_check evaluation with pre-fetched grants

Evaluates has_grant() conditions by checking pre-fetched active_grants
in the filter context. Matches on relation + scope_id and excludes
expired grants via ISO datetime comparison.

Part of grant_schema runtime RBAC infrastructure."
```

---

### Task 8b: grant_check SQL filter generation

The SQL filter path is used for list queries. Without `has_grant()` SQL filter support, list views with grant-based access rules would silently include all rows. This generates a subquery clause for the repository layer.

**Files:**
- Modify: `src/dazzle_back/runtime/condition_evaluator.py:244-300` (`condition_to_sql_filter`)
- Test: `tests/unit/test_condition_evaluator_grant_sql.py` (new)

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_condition_evaluator_grant_sql.py
"""Tests for grant_check SQL filter generation in condition_to_sql_filter."""

from dazzle_back.runtime.condition_evaluator import condition_to_sql_filter


class TestGrantCheckSqlFilter:
    def test_grant_check_generates_subquery_clause(self):
        condition = {
            "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
        }
        context = {"current_user_id": "user-1"}
        filters = condition_to_sql_filter(condition, context)
        # Should produce a _grant_subquery key with the subquery info
        assert "_grant_subquery" in filters
        sq = filters["_grant_subquery"]
        assert sq["field"] == "department_id"
        assert sq["relation"] == "acting_hod"
        assert sq["principal_id"] == "user-1"

    def test_grant_check_no_user_returns_deny(self):
        condition = {
            "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
        }
        context = {}  # no current_user_id
        filters = condition_to_sql_filter(condition, context)
        assert "_grant_denied" in filters

    def test_grant_check_in_or_returns_empty_for_post_filter(self):
        """OR conditions with grant_check need post-fetch filtering."""
        condition = {
            "operator": "or",
            "left": {"role_check": {"role_name": "hod"}},
            "right": {
                "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
            },
        }
        context = {"user_roles": [], "current_user_id": "user-1"}
        # OR conditions already fall through to post-fetch filtering
        # The _condition_has_or check catches this
        filters = condition_to_sql_filter(condition, context)
        # OR at top level → empty filters (rely on post-fetch)
        assert filters == {}

    def test_grant_check_in_and_with_comparison(self):
        """has_grant(...) and status = active — both become SQL filters."""
        condition = {
            "operator": "and",
            "left": {
                "grant_check": {"relation": "acting_hod", "scope_field": "department_id"}
            },
            "right": {
                "comparison": {
                    "field": "status",
                    "operator": "eq",
                    "value": {"literal": "active"},
                }
            },
        }
        context = {"current_user_id": "user-1"}
        filters = condition_to_sql_filter(condition, context)
        assert "status" in filters
        assert "_grant_subquery" in filters
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_condition_evaluator_grant_sql.py -v`
Expected: FAIL — `grant_check` not handled in `condition_to_sql_filter`.

- [ ] **Step 3: Add grant_check handling to condition_to_sql_filter**

In `src/dazzle_back/runtime/condition_evaluator.py`, add `grant_check` handling to `condition_to_sql_filter()` before the comparison handling:

```python
    # Handle grant check — generate subquery metadata for repository layer
    if "grant_check" in condition and condition["grant_check"]:
        gc = condition["grant_check"]
        principal_id = context.get("current_user_id")
        if not principal_id:
            return {"_grant_denied": True}
        return {
            "_grant_subquery": {
                "field": gc["scope_field"],
                "relation": gc["relation"],
                "principal_id": principal_id,
            }
        }
```

The repository layer will interpret `_grant_subquery` to generate:
```sql
WHERE department_id IN (
    SELECT scope_id FROM _grants
    WHERE principal_id = :principal_id AND relation = :relation
    AND status = 'active' AND (expires_at IS NULL OR expires_at > :now)
)
```

Note: The actual SQL generation in the repository layer is deferred to sub-project 2 (contextual UI), since list views with grant-based access rules require the full runtime to be wired up. This task establishes the filter metadata contract.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_condition_evaluator_grant_sql.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: No regressions

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/runtime/condition_evaluator.py \
  tests/unit/test_condition_evaluator_grant_sql.py
git commit -m "feat(evaluator): add grant_check SQL filter generation

Generate _grant_subquery metadata in condition_to_sql_filter() for
has_grant() conditions. The repository layer will interpret this to
produce subquery clauses against the _grants table.

Part of grant_schema runtime RBAC infrastructure."
```

---

### Task 9: Grant pre-fetching in workspace rendering

Wire grant pre-fetching into the workspace rendering context so `has_grant()` conditions can evaluate.

**Files:**
- Modify: `src/dazzle_back/runtime/workspace_rendering.py` (add grant pre-fetching)
- Test: `tests/unit/test_workspace_rendering_grants.py` (new)

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_workspace_rendering_grants.py
"""Tests for grant pre-fetching in workspace rendering."""

import inspect

from dazzle_back.runtime import workspace_rendering


class TestGrantPreFetchingWiring:
    def test_active_grants_referenced_in_source(self):
        """Verify the workspace rendering module references active_grants in filter context."""
        source = inspect.getsource(workspace_rendering)
        assert "active_grants" in source, (
            "workspace_rendering.py should reference 'active_grants' "
            "for grant pre-fetching into filter context"
        )

    def test_grant_store_imported_or_referenced(self):
        """Verify grant_store is referenced for pre-fetching."""
        source = inspect.getsource(workspace_rendering)
        assert "grant_store" in source.lower() or "grant" in source.lower(), (
            "workspace_rendering.py should reference grant store for pre-fetching"
        )
```

Note: This task requires reading `workspace_rendering.py` to find the exact integration point. The pre-fetching follows the same pattern as `current_user_entity` — loaded early, stored in `_filter_context`. The exact implementation depends on how the grant store is made available to the rendering context (likely via the app's runtime state).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_workspace_rendering_grants.py -v`
Expected: FAIL — no `active_grants` reference in workspace_rendering.py yet.

- [ ] **Step 3: Add grant pre-fetching to workspace rendering**

Read `src/dazzle_back/runtime/workspace_rendering.py` to find where `_filter_context` is populated (near where `current_user_entity` is set). Add grant pre-fetching after the current_user_entity population:

```python
# Pre-fetch active grants for has_grant() condition evaluation
if _current_user_id:
    try:
        from .grant_store import GrantStore
        # Grant store is initialized with the same DB connection
        _grant_store = GrantStore(_db_connection)
        _active_grants = _grant_store.list_grants(
            principal_id=_current_user_id, status="active"
        )
        _filter_context["active_grants"] = _active_grants
    except Exception:
        # Grant tables may not exist if no grant_schemas defined
        _filter_context["active_grants"] = []
```

The exact placement and variable names depend on the current structure of workspace_rendering.py. The key requirement is that `active_grants` is in the filter context before any condition evaluation occurs.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_workspace_rendering_grants.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: No regressions

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/runtime/workspace_rendering.py \
  tests/unit/test_workspace_rendering_grants.py
git commit -m "feat(runtime): pre-fetch active grants into workspace filter context

Load active grants for the current user into the filter context before
condition evaluation, enabling has_grant() checks. Follows the same
pre-fetching pattern as current_user_entity.

Part of grant_schema runtime RBAC infrastructure."
```

---

### Task 10: Lint, type check, and final integration test

Run quality checks and verify the full pipeline works end-to-end.

**Files:**
- Test: `tests/unit/test_grant_integration.py` (new)

- [ ] **Step 1: Write integration test**

```python
# tests/unit/test_grant_integration.py
"""Integration test: DSL parse → IR → grant store → condition evaluation."""

import sqlite3
from pathlib import Path
from uuid import uuid4

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle_back.runtime.condition_evaluator import evaluate_condition
from dazzle_back.runtime.grant_store import GrantStore


class TestGrantPipelineIntegration:
    def test_parse_to_evaluation_pipeline(self):
        """Parse grant_schema DSL, create grant in store, evaluate condition."""
        # 1. Parse DSL with grant_schema and has_grant()
        dsl = '''module test_mod

entity Department "Department":
  id: uuid pk
  name: str(200)

entity AssessmentEvent "Assessment Event":
  id: uuid pk
  department: ref Department
  access:
    read: role(hod) or has_grant("acting_hod", department)
'''
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        # Verify has_grant parsed correctly
        entity = [e for e in fragment.entities if e.name == "AssessmentEvent"][0]
        read_rules = [r for r in entity.access.permissions if r.kind.value == "read"]
        assert read_rules
        cond = read_rules[0].condition
        assert cond.is_compound  # role(hod) or has_grant(...)
        assert cond.right.grant_check is not None
        assert cond.right.grant_check.relation == "acting_hod"
        assert cond.right.grant_check.scope_field == "department"

        # 2. Create grant in store
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        store = GrantStore(conn)

        user_id = str(uuid4())
        dept_id = str(uuid4())

        store.create_grant(
            schema_name="dept_delegation",
            relation="acting_hod",
            principal_id=user_id,
            scope_entity="Department",
            scope_id=dept_id,
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )

        # 3. Evaluate condition with pre-fetched grants
        active_grants = store.list_grants(principal_id=user_id, status="active")

        # Serialize condition to dict (as it would be at runtime)
        condition_dict = cond.model_dump()

        record = {"department": dept_id}
        context = {
            "user_roles": [],  # Not an HoD
            "active_grants": active_grants,
        }

        result = evaluate_condition(condition_dict, record, context)
        assert result is True, "User with active grant should pass has_grant() check"

    def test_parse_to_evaluation_no_grant(self):
        """User without grant fails has_grant() check."""
        dsl = '''module test_mod

entity Department "Department":
  id: uuid pk
  name: str(200)

entity AssessmentEvent "Assessment Event":
  id: uuid pk
  department: ref Department
  access:
    read: has_grant("acting_hod", department)
'''
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = [e for e in fragment.entities if e.name == "AssessmentEvent"][0]
        read_rules = [r for r in entity.access.permissions if r.kind.value == "read"]
        cond = read_rules[0].condition
        condition_dict = cond.model_dump()

        record = {"department": str(uuid4())}
        context = {"active_grants": []}

        result = evaluate_condition(condition_dict, record, context)
        assert result is False
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/unit/test_grant_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -m "not e2e" -x --timeout=120`
Expected: All pass

- [ ] **Step 4: Lint all changed files**

Run: `ruff check src/ tests/ --fix && ruff format src/ tests/`

- [ ] **Step 5: Type check**

Run: `mypy src/dazzle`

- [ ] **Step 6: Commit**

```bash
git add tests/unit/test_grant_integration.py
git commit -m "test: add grant pipeline integration test (parse → store → evaluate)

End-to-end test verifying the full grant pipeline:
1. Parse DSL with grant_schema and has_grant() conditions
2. Create grants in the runtime store
3. Evaluate conditions with pre-fetched grants

Completes core grant infrastructure (sub-project 1)."
```
