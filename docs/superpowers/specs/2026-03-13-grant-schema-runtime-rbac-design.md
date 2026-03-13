# Grant Schema: Runtime RBAC Design

## Goal

Add runtime-configurable permissions to Dazzle via a `grant_schema` DSL construct that layers dynamic, instance-scoped grants over the existing Cedar-style static access rules. Grants are auditable, time-bounded, and managed through contextual UI actions on domain objects — not through a generic permissions panel.

## Architecture

Three-layer model:

1. **Static policy** (existing) — Cedar-style `permit`/`forbid` rules in entity DSL, evaluated at compile time. Unchanged.
2. **Dynamic grants** (new) — Runtime data in a typed tuple store, defined by `grant_schema` constructs. Queryable via `has_grant()` in condition expressions.
3. **Decision log** (new) — Immutable event log recording every grant lifecycle transition and access decision trace.

Static policy defines the permission *model*. Dynamic grants define what's *active*. The decision log records what was *decided*. Each layer is independently reviewable by a security auditor.

## Prerequisites

**`role_check` evaluation in condition_evaluator.py**: The current runtime condition evaluator (`condition_evaluator.py`) handles `comparison` conditions but silently passes `role_check` conditions as true (falls through to `return True`). This must be fixed before `has_grant()` is added, because `granted_by` expressions use `role()` and the grant creation endpoint must enforce them correctly. Implementation step 0 (before grant work begins): add `role_check` evaluation to both `evaluate_condition()` and `condition_to_sql_filter()`.

## Scope

**In scope:**
- `grant_schema` DSL construct with nested `relation` blocks
- IR types: `GrantSchemaSpec`, `GrantRelationSpec`, `GrantCheck`
- Parser mixin for `grant_schema`
- `has_grant()` condition function (parser, IR, evaluator, SQL filter)
- Runtime grant store (`_grants` table, `_grant_events` audit table)
- Contextual UI actions generated from grant schema metadata
- Grant lifecycle: create, approve, activate, expire, revoke
- Coherence and policy tool integration
- Grammar reference update (`docs/reference/grammar.md`)

**Out of scope (YAGNI, composes later):**
- Transitive grants (grant delegation chains)
- Group principals (grant to a role rather than individual user)
- Field/section visibility narrowing (#487 — separate feature that will compose via `has_grant()` in `visible:` conditions)
- Decision log for non-grant access decisions (valuable but independent)

## Relationship to #487 (Field-Level Surface Visibility)

Issue #487 requests field/section visibility rules scoped by role on surfaces. That is a **narrowing** operation (restrict within existing permissions). Grant schemas handle the **widening** case (runtime delegation, contextual access escalation).

The two features compose naturally: if section `visible:` conditions accept `has_grant()`, then `visible: role(admin) or has_grant("acting_hod", department)` works without coupling. This spec designs `has_grant()` to be available anywhere condition expressions are used, enabling that composition. But #487 itself is a separate, simpler implementation.

---

## DSL Construct

### `grant_schema`

Top-level construct grouping related delegation relations by scope entity.

```dsl
grant_schema department_delegation "Department Delegation":
  description: "Delegation of department-level responsibilities"
  scope: Department

  relation acting_hod "Assign covering HoD":
    description: "Temporarily assign HoD responsibilities to a staff member"
    principal_label: "Staff member"
    confirmation: "This will give {principal.name} full HoD access to {scope.name}"
    granted_by: role(senior_leadership)
    approved_by: role(principal)
    approval: required
    expiry: required
    max_duration: 90d
    revoke_verb: "Remove covering HoD"

  relation observer "Assign department observer":
    description: "Grant read-only access to department data"
    principal_label: "Observer"
    granted_by: role(hod) or has_grant("acting_hod", department)
    approval: none
    expiry: optional
```

### Field reference

| Field | Required | Default | Purpose |
|-------|----------|---------|---------|
| `name` | yes | — | Identifier (e.g. `department_delegation`) |
| `label` | yes | — | Human-readable title |
| `description` | no | — | Longer description for docs/audit |
| `scope` | yes | — | Entity type name — grants are scoped to instances of this entity |

### `relation` sub-block

| Field | Required | Default | Purpose |
|-------|----------|---------|---------|
| `name` | yes | — | Relation identifier (e.g. `acting_hod`) |
| `label` | yes | — | Action button text / grant verb |
| `description` | no | — | Explanation shown in audit view |
| `principal_label` | no | `"User"` | Label for person picker in UI |
| `confirmation` | no | — | Confirmation prompt template (see Interpolation below) |
| `revoke_verb` | no | `"Remove"` | Text for the revoke action button |
| `granted_by` | yes | — | Condition expression — who can create this grant |
| `approved_by` | no | same as `granted_by` | Condition expression — who can approve (only relevant when `approval: required`) |
| `approval` | no | `required` | `required` (no effect until approved), `immediate` (takes effect, flagged for review), `none` (no approval needed) |
| `expiry` | no | `required` | `required` (must specify end date), `optional` (may specify), `none` (permanent until revoked) |
| `max_duration` | no | — | Maximum grant duration (e.g. `90d`, `1y`). Enforced at creation time |

### Confirmation template interpolation

The `confirmation` field supports simple variable interpolation:
- `{principal.name}` — display name of the user being granted access (resolved from User entity's `name` field, falling back to `email`)
- `{scope.name}` — display name of the scoped entity instance (resolved via the entity's `ref_display` chain: `name` → `title` → `email` → ID)

No arbitrary dotted-path traversal. Only these two variables are supported. Unresolvable references render as the entity ID.

### Referencing grants in access rules

```dsl
entity AssessmentEvent:
  access:
    read: role(hod) or has_grant("acting_hod", department)
    update: role(hod) or has_grant("acting_hod", department)
```

`has_grant(relation_name, scope_field)`:
- `relation_name` — string literal, the relation to check
- `scope_field` — field name whose value is matched against `scope_id` in the grants table. In access rules, this is a field on the entity being accessed (e.g. `AssessmentEvent.department`). In `granted_by` expressions, this is a field on the scope entity instance where the grant action is being performed

### Self-referential `has_grant()` in `granted_by`

A relation's `granted_by` may reference other relations via `has_grant()` (e.g., an acting HoD can grant observer access). This creates ordering dependencies between relations. Circular references between relations must be detected at linker time and rejected as an error.

---

## IR Types

New file: `src/dazzle/core/ir/grants.py`

```python
class GrantApprovalMode(StrEnum):
    REQUIRED = "required"
    IMMEDIATE = "immediate"
    NONE = "none"

class GrantExpiryMode(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    NONE = "none"

class GrantRelationSpec(BaseModel):
    name: str
    label: str
    description: str | None = None
    principal_label: str | None = None
    confirmation: str | None = None
    revoke_verb: str | None = None
    granted_by: ConditionExpr
    approved_by: ConditionExpr | None = None  # Defaults to granted_by at link time
    approval: GrantApprovalMode = GrantApprovalMode.REQUIRED
    expiry: GrantExpiryMode = GrantExpiryMode.REQUIRED
    max_duration: str | None = None
    source_location: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)

class GrantSchemaSpec(BaseModel):
    name: str
    label: str
    description: str | None = None
    scope: str  # Entity type name
    relations: list[GrantRelationSpec]
    source_location: SourceLocation | None = None

    model_config = ConfigDict(frozen=True)
```

### `GrantCheck` condition type

Added to `src/dazzle/core/ir/conditions.py`:

```python
class GrantCheck(BaseModel):
    relation: str       # "acting_hod"
    scope_field: str    # "department" — field on entity being accessed

    model_config = ConfigDict(frozen=True)
```

Added as a field on `ConditionExpr`:

```python
class ConditionExpr(BaseModel):
    comparison: Comparison | None = None
    role_check: RoleCheck | None = None
    grant_check: GrantCheck | None = None      # NEW
    operator: LogicalOperator | None = None
    left: ConditionExpr | None = None
    right: ConditionExpr | None = None
```

### ModuleFragment and AppSpec registration

```python
# src/dazzle/core/ir/module.py
class ModuleFragment(BaseModel):
    # ... existing fields ...
    grant_schemas: list[GrantSchemaSpec] = Field(default_factory=list)
```

```python
# src/dazzle/core/ir/appspec.py
class AppSpec(BaseModel):
    # ... existing fields ...
    grant_schemas: list[GrantSchemaSpec] = Field(default_factory=list)
```

The linker merges `ModuleFragment.grant_schemas` into `AppSpec.grant_schemas` following the same pattern as other constructs (e.g., `rules`, `questions`).

---

## Parser

New mixin: `src/dazzle/core/dsl_parser_impl/grant.py` — `GrantParserMixin`

- `parse_grant_schema()` — parses the top-level construct header + indented body
- `parse_grant_relation()` — parses each `relation` sub-block
- Reuses existing `parse_condition_expr()` for `granted_by` and `approved_by`
- Reuses existing duration parsing for `max_duration`

New token: `GRANT_SCHEMA = "grant_schema"` in lexer keywords.

Grammar reference: Update `docs/reference/grammar.md` with the `grant_schema` production rules.

### `has_grant()` parsing

Extension to `_parse_primary_condition()` in `conditions.py`:
- When identifier is `has_grant`, parse `(relation_name, scope_field)` as two arguments
- Produces a `GrantCheck` node on the condition expression

---

## Runtime Grant Store

### Tables

Created automatically when any `grant_schema` exists in the AppSpec.

**`_grants`** — queryable current state:

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid pk | |
| `schema_name` | str | Which grant_schema |
| `relation` | str | Which relation |
| `principal_id` | uuid | Who receives the grant |
| `scope_entity` | str | Entity type of scope |
| `scope_id` | uuid | Which instance |
| `status` | str | `pending_approval`, `active`, `rejected`, `cancelled`, `expired`, `revoked` |
| `granted_by_id` | uuid | Who created |
| `approved_by_id` | uuid | Who approved (null if immediate/none) |
| `granted_at` | datetime | |
| `approved_at` | datetime | |
| `expires_at` | datetime | Null if no expiry |
| `revoked_at` | datetime | Null if not revoked |
| `revoked_by_id` | uuid | Null if not revoked |

**Composite index**: `(principal_id, relation, scope_id, status)` — this is the hot-path query for `has_active_grant()`.

**`_grant_events`** — immutable audit log:

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid pk | |
| `grant_id` | uuid fk | |
| `event_type` | str | `created`, `approved`, `rejected`, `cancelled`, `activated`, `expired`, `revoked` |
| `actor_id` | uuid | Who performed the action |
| `timestamp` | datetime | |
| `metadata` | jsonb | Additional context (e.g. rejection reason) |

### Status transitions

```
created (approval: required)  → pending_approval → approved → active → expired
                                                            → revoked
                                pending_approval → rejected (terminal)
                                pending_approval → cancelled (terminal, admin withdraws request)

created (approval: immediate) → active → expired
                                       → revoked

created (approval: none)      → active → expired
                                       → revoked
```

### Grant store API

New file: `src/dazzle_back/runtime/grant_store.py`

```python
class GrantStore:
    async def create_grant(schema_name, relation, principal_id, scope_entity, scope_id,
                           granted_by_id, expires_at=None) -> Grant
    async def approve_grant(grant_id, approved_by_id) -> Grant
    async def reject_grant(grant_id, rejected_by_id, reason=None) -> Grant
    async def revoke_grant(grant_id, revoked_by_id) -> Grant
    async def has_active_grant(principal_id, relation, scope_id) -> bool
    async def list_grants(scope_entity=None, scope_id=None, principal_id=None,
                          status=None) -> list[Grant]
    async def expire_stale_grants() -> int  # Called periodically or on access check
```

**Expiry enforcement**: `has_active_grant()` checks both `status = 'active'` AND `(expires_at IS NULL OR expires_at > NOW())`. This means grants are correctly excluded even if `expire_stale_grants()` has not yet run. The `expire_stale_grants()` method is a background cleanup that updates `status` to `expired` for audit consistency, but it is not required for correctness.

### `has_grant()` evaluation

**Context pre-fetching**: The grant store is async, but the condition evaluator is synchronous. To bridge this, active grants for the current user are pre-fetched into the filter context before evaluation begins (similar to how `current_user_id` and `current_user_entity` are resolved in `workspace_rendering.py` before filter evaluation).

```python
# In workspace_rendering.py or access evaluation setup:
if grant_store and _current_user_id:
    _active_grants = await grant_store.list_grants(
        principal_id=_current_user_id, status="active"
    )
    _filter_context["active_grants"] = _active_grants
```

**In-memory evaluation** (condition_evaluator.py):

```python
def _evaluate_grant_check(check: GrantCheck, record: dict, context: dict) -> bool:
    scope_value = record.get(check.scope_field)
    if not scope_value:
        return False
    active_grants = context.get("active_grants", [])
    now = datetime.utcnow()
    return any(
        g.relation == check.relation
        and str(g.scope_id) == str(scope_value)
        and (g.expires_at is None or g.expires_at > now)
        for g in active_grants
    )
```

**SQL filter generation**: The current `condition_to_sql_filter()` returns a flat `dict[str, Any]` which cannot express subqueries. This must be extended to support richer filter types. The approach:

- `condition_to_sql_filter()` returns a new type `SqlFilter` (or extended dict) that can contain both simple key-value filters and raw SQL clauses
- For `has_grant()`, the filter includes a subquery clause:

```sql
WHERE department IN (
    SELECT scope_id FROM _grants
    WHERE principal_id = :current_user_id
    AND relation = 'acting_hod'
    AND status = 'active'
    AND (expires_at IS NULL OR expires_at > NOW())
)
```

- The repository's `list()` method is extended to accept these richer filters alongside existing simple filters
- Simple filters continue to work unchanged — the extension is additive

---

## Contextual UI

### Grant actions on detail pages

When the runtime renders a detail page for an entity that is the `scope` target of any `grant_schema`, it generates contextual actions:

1. **Action buttons**: For each relation where the current user satisfies `granted_by`, render a button with the relation's `label`.

2. **Action flow**: Button opens a modal with:
   - Person picker (labelled with `principal_label`)
   - Date range picker (if `expiry` is `required` or `optional`, constrained by `max_duration`)
   - Confirmation text (interpolated `confirmation` template)
   - Submit creates the grant + event

3. **Active grants section**: Lists active grants for this scope instance, showing principal name, relation label, expiry, and revoke action (using `revoke_verb`).

4. **Pending approvals**: For `approval: required` grants, shows pending grants with approve/reject actions for users satisfying the relation's `approved_by` condition.

### Schema metadata → UI mapping

| Schema field | UI element |
|---|---|
| `relation.label` | Action button text |
| `principal_label` | Person picker label |
| `expiry` mode | Date picker presence/requirement |
| `max_duration` | Date picker max range constraint |
| `confirmation` | Confirmation dialog text |
| `revoke_verb` | Remove button text |
| `granted_by` | Controls action button visibility |
| `approved_by` | Controls approve/reject button visibility |

### Audit view

Read-only workspace region (or dedicated surface) querying `_grants` and `_grant_events`. Shows current state and full event history. Standard list surface over grant tables — no special UI components needed.

Management happens in context on the scoped entity page. Oversight happens centrally in the audit view.

---

## Validation & Coherence

### Parser-time validation

- `scope` references an entity that exists in the module
- `granted_by` and `approved_by` are syntactically valid condition expressions
- `max_duration` parses as a valid duration
- No duplicate relation names within a schema
- No duplicate schema names within a module

### Linker-time validation

- `has_grant()` `relation` argument matches a relation in some grant schema
- `has_grant()` `scope_field` argument is a field on the entity being accessed
- `scope_field` is a ref to the grant schema's scope entity (or the scope entity itself)
- No circular `has_grant()` references between relations (e.g., relation A's `granted_by` checks `has_grant("B")` and relation B's `granted_by` checks `has_grant("A")`)
- `approved_by` defaults to `granted_by` if not specified

### Policy tool extensions

- `coverage`: Include grant-based access paths in the persona × entity × operation matrix
- `simulate`: Trace `has_grant()` checks, report whether matching grant exists
- `conflicts`: Flag `forbid` rules that contradict grant-based `permit` paths

### Coherence checks

- Grant schema references an entity that exists
- `has_grant()` references a relation that exists in some grant schema
- `scope_field` references a field that is a ref to the schema's scope entity
- No orphaned grant schemas (defined but never referenced in any access rule) — warning, not error

---

## Testing Strategy

### Unit tests

- `has_grant()` parsing produces correct `GrantCheck` IR
- `has_grant()` evaluates to True/False against pre-fetched grant list in context
- `has_grant()` generates correct SQL subquery via extended filter interface
- Grant store CRUD: create, activate, expire, revoke with correct status transitions
- Grant store rejects invalid transitions (e.g. revoke a pending-approval grant directly)
- Expiry enforcement: expired grants don't satisfy `has_grant()` (both in-memory and SQL)
- Parser produces correct `GrantSchemaSpec` with nested `GrantRelationSpec`
- Validation: `scope` references a valid entity, `granted_by` is a valid condition expression
- Validation: invalid `scope` produces a parse/link error
- Validation: invalid `has_grant()` relation name produces a linker error
- Validation: `scope_field` that is not a ref to scope entity produces a coherence error
- Validation: circular `has_grant()` references between relations are rejected
- `max_duration` enforcement: grant creation rejects durations exceeding limit
- `approved_by` defaults to `granted_by` when not specified

### Integration tests (E2E)

- Create a grant via contextual action → verify `has_grant()` returns true
- Revoke a grant → verify `has_grant()` returns false
- Expired grant → verify access removed after expiry
- `approval: required` → verify grant has no effect until approved
- `approval: immediate` → verify grant takes effect before approval
- `granted_by` enforcement → verify non-authorized users can't create grants
- `approved_by` enforcement → verify only authorized approvers can approve
- Audit trail: verify `_grant_events` records all lifecycle transitions

---

## Implementation Order

0. **Prerequisite: `role_check` evaluation** — Fix `condition_evaluator.py` to evaluate `role_check` conditions (currently silently passes as true)
1. **IR types** — `GrantSchemaSpec`, `GrantRelationSpec`, `GrantCheck`, enums
2. **Parser** — `grant_schema` construct + `has_grant()` condition function + grammar.md update
3. **Grant store** — `_grants` and `_grant_events` tables, `GrantStore` API, composite index
4. **Condition evaluator** — `has_grant()` in-memory evaluation (pre-fetched context) and SQL subquery generation (extended filter interface)
5. **Access evaluator** — Wire grant pre-fetching into access evaluation context
6. **Contextual UI** — Action generation on detail pages, active grants display, approval flow
7. **Policy/coherence** — Extend existing tools to understand grant schemas

Each step is independently testable and shippable.

---

## Future Composition Points

- **#487 field/section visibility**: Once implemented, `visible: has_grant("acting_hod", department)` works with no additional grant-side changes
- **Transitive grants**: A relation could declare `transitive: true`, allowing grantees to further delegate. Requires cycle detection.
- **Group principals**: Grant to a role instead of a user. `has_grant()` evaluation checks group membership.
- **Decision logging**: Full access decision trace (not just grant lifecycle) for incident response.
