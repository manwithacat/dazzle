# Scope `via` Clause: Junction-Table Access Control

**Date**: 2026-03-18
**Status**: Design
**Issue**: #530

## Problem

The `scope:` block system only supports simple field equality conditions (`field = current_user.attr`) and nested ref traversals (`shape.realm = current_user.realm`). This is insufficient for multi-tenant RBAC where access is mediated through junction tables.

Real-world example: a bookkeeping practice assigns agents to client contacts through an `AgentAssignment` entity. The agent should only see contacts they're assigned to. This requires a subquery through the junction table — `WHERE id IN (SELECT contact FROM AgentAssignment WHERE agent = $current_user_contact)` — which the current scope system cannot express.

Forcing denormalized FKs (e.g., `assigned_agent` directly on Contact) limits the relationship to 1:1 and loses assignment metadata (scope, revocation, audit trail).

## Design

### DSL Syntax

New `via` keyword in scope conditions. Add `VIA = "via"` to the `TokenType` enum in `lexer.py` and to the keyword table so it's recognized as a reserved keyword token.

Syntax:

```dsl
scope:
  list: via JunctionEntity(binding, binding, ...)
    for: role1, role2
```

Each **binding** is one of:

| Binding type | Syntax | Purpose |
|---|---|---|
| Entity binding | `junction_field = id` or `junction_field = field_name` | Links junction table back to scoped entity |
| User binding | `junction_field = current_user` or `junction_field = current_user.attr` | Filters junction table by authenticated user |
| Literal filter | `junction_field = null` or `junction_field != null` | Filters the junction table itself (soft-delete, status) |

Full example:

```dsl
entity AgentAssignment:
  agent: ref Contact required
  contact: ref Contact required
  scope_level: enum[full, accounts, tax, payroll]
  revoked_at: datetime

entity Contact:
  name: str(200) required
  email: email required

  permit:
    list: role(agent), role(admin)
    read: role(agent), role(admin)

  scope:
    list: via AgentAssignment(agent = current_user.contact, contact = id, revoked_at = null)
      for: agent
    list: all
      for: admin
```

This generates:

```sql
-- For agent role:
WHERE "id" IN (
  SELECT "contact" FROM "AgentAssignment"
  WHERE "agent" = $1
  AND "revoked_at" IS NULL
)
```

### Constraints

- **No composition**: `via` is the entire condition. No `and`/`or` mixing with field comparisons in the same scope rule. Use separate scope rules if multiple conditions are needed (they OR together as today).
- **Single hop only**: One junction table per `via` clause. No chaining (`via A through B`).
- **Non-PK matching supported**: The entity binding can reference any field on the scoped entity, not just `id`. Example: `via TeamMembership(user = current_user, team = team)` matches on the `team` field.

---

## IR Model

### New Types

```python
class ViaBinding(BaseModel):
    """A single binding inside a via() clause."""
    junction_field: str          # column on the junction table
    target: str                  # "id", "field_name", "current_user", "current_user.attr", or "null"
    operator: str = "="          # "=" or "!="

class ViaCondition(BaseModel):
    """Subquery condition through a junction table."""
    junction_entity: str         # e.g. "AgentAssignment"
    bindings: list[ViaBinding]
```

`ConditionExpr` in `src/dazzle/core/ir/conditions.py` is a discriminated-by-presence model (not a Union type). Add a new optional field:

```python
class ConditionExpr(BaseModel):
    # ... existing fields (comparison, role_check, grant_check, left, operator, right) ...
    via_condition: ViaCondition | None = None  # NEW
```

When `via_condition` is set, it is the entire condition — the other fields are None. A `ScopeRule` with a `ViaCondition` means the rule's condition is a subquery.

No separate `SubQuery` abstraction — `ViaCondition` is the subquery. If a second subquery source appears later, extract the abstraction then (YAGNI).

### Parser Validation (at parse time)

- At least one binding must reference `id` or a field on the scoped entity (the "entity binding")
- At least one binding must reference `current_user` (the "user binding")
- Literal filters (`= null`, `!= null`) are optional
- Junction entity name is captured as a string; existence validated post-parse during linking

---

## Backend Spec & Converter

### New Backend Type

```python
class ViaBindingSpec(BaseModel):
    junction_field: str
    target: str
    operator: str = "="

class ViaConditionSpec(BaseModel):
    junction_entity: str
    bindings: list[ViaBindingSpec]
```

The `ScopeRuleSpec.condition` field type widens to accept either type:

```python
class ScopeRuleSpec(BaseModel):
    operation: AccessOperationKind
    condition: AccessConditionSpec | ViaConditionSpec | None = None  # widened
    personas: list[str] = Field(default_factory=list)
```

### Converter

`_convert_scope_rule()` in `entity_converter.py` branches before calling `_convert_access_condition()`. If the IR `ScopeRule.condition` has `via_condition` set, call a new `_convert_via_condition()` function directly. This avoids widening `_convert_access_condition()`'s return type:

```python
def _convert_scope_rule(rule: ir.ScopeRule) -> ScopeRuleSpec:
    if rule.condition and rule.condition.via_condition:
        condition = _convert_via_condition(rule.condition.via_condition)
    elif rule.condition:
        condition = _convert_access_condition(rule.condition)
    else:
        condition = None
    return ScopeRuleSpec(operation=..., condition=condition, personas=...)
```

`_convert_via_condition()` maps `ViaCondition` → `ViaConditionSpec` with bindings mapping 1:1.

---

## Runtime SQL Generation

### Route Generator

`_extract_condition_filters()` in `route_generator.py` gets a new branch for `ViaConditionSpec`. It calls `_build_via_subquery()`:

```python
def _build_via_subquery(
    via: ViaConditionSpec,
    user_id: str,
    auth_context: AuthContext | None,
    param_offset: int = 0,
) -> tuple[str, str, list[Any]]:
    """Build a SQL subquery for a via condition.

    Args:
        via: The via condition spec.
        user_id: Authenticated user ID.
        auth_context: Full auth context (needed for _resolve_user_attribute() on user bindings like current_user.contact).
        param_offset: Starting parameter index (for $N placeholders) to avoid conflicts with outer query params.

    Returns:
        (entity_field, subquery_sql, params)
        e.g. ("id", 'SELECT "contact" FROM "AgentAssignment" WHERE "agent" = $1 AND "revoked_at" IS NULL', [user_contact_id])
    """
```

The function:
1. Identifies the entity binding (determines which junction field to SELECT and which entity field to match)
2. Resolves user bindings via the existing `_resolve_user_attribute()` function (which requires `AuthContext`, not a plain dict)
3. Builds WHERE clauses from user bindings and literal filters
4. Returns parameterized SQL — user values go through `$N` placeholders (offset by `param_offset` to avoid conflicts with outer query params), identifiers through `quote_id()`

### Repository Layer

Add `IN_SUBQUERY = "in_subquery"` to the `FilterOperator` enum in `query_builder.py` and add the corresponding SQL template to `OPERATOR_SQL`.

The filter dict uses a new key suffix `__in_subquery` which the repository interprets as `WHERE "field" IN (subquery)`. The value is a tuple of `(subquery_sql, params)`:

```python
{"id__in_subquery": ('SELECT "contact" FROM "AgentAssignment" WHERE "agent" = $1', [user_contact_id])}
```

**Parameter merging:** The subquery's parameter list is appended to the outer query's parameter list. The subquery SQL uses placeholder indices offset from the outer query's current parameter count. For example, if the outer query already has 2 parameters, the subquery's `$1` becomes `$3`. The `_build_via_subquery()` function accepts a `param_offset` argument for this purpose; the caller passes `len(existing_params)`.

This keeps subquery generation in the access control layer and SQL execution in the repository.

---

## RBAC Matrix

**No new decision types.** A scope rule with a `ViaCondition` produces `PERMIT_SCOPED` — the matrix already handles this. The `via` condition is transparent to the matrix: it sees "this role has a scoped condition."

---

## Static Validation (Lint)

Post-parse validation during linking:

- Junction entity named in `via` must exist in the AppSpec
- Junction fields referenced in bindings must exist on that entity
- Entity field referenced (e.g., `id`) must exist on the scoped entity
- **Warning** if the junction entity has no `ref` field pointing back to the scoped entity (likely a mistake)

---

## Error Messages

**Parse errors:**
- "Expected entity name after `via`"
- "Expected `(` after junction entity name"
- "via binding must contain `=` or `!=`"
- "via condition requires at least one entity binding (e.g., `contact = id`)"
- "via condition requires at least one user binding (e.g., `agent = current_user`)"

**Validation errors (post-parse):**
- "Junction entity 'Foo' not found"
- "Field 'bar' not found on entity 'Foo'"

**Runtime:** If the junction table doesn't exist in the database, the subquery fails with a standard SQL error. No special handling.

---

## Testing Strategy

| Layer | What to test |
|---|---|
| Parser | Parse `via` clauses, verify IR `ViaCondition` nodes, test all error cases (missing entity binding, missing user binding, malformed syntax) |
| Converter | `ViaCondition` → `ViaConditionSpec` round-trip |
| Runtime | Mock connection, verify generated SQL contains correct subquery with parameterized values, test literal filters (`revoked_at = null`) |
| RBAC matrix | Verify `PERMIT_SCOPED` for roles with via conditions |
| Shapes example | Add a junction-table scoped entity to `examples/shapes_validation/` exercising the full pipeline |

---

## Non-Goals

- **Composition with `and`/`or`**: `via` is the entire condition. Scope rule intersection semantics are a separate concern.
- **Multi-hop chaining**: `via A through B` is not supported. Single junction table only.
- **Aggregation conditions**: No `count`, `sum`, or other aggregate filters on the junction table.
- **Explicit SubQuery abstraction**: The `ViaCondition` IR node is the subquery. No generic SubQuery type.

## Scope

This completes the RBAC story: `permit:` for gate authorization, `scope:` for row-level filtering including junction-table relationships via the new `via` clause.
