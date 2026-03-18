# Scope Block: Separating Authorization from Row Filtering

**Date**: 2026-03-18
**Status**: Design
**Issue**: #526 (reopened — field-condition rules bypass LIST gate)

## Problem

The DSL conflates two distinct security concepts in `permit:` blocks:

- **Authorization**: "Who may access this entity?" — answered by role checks
- **Scoping**: "What subset of records can they see?" — answered by field conditions

When a DSL author writes `permit: list: school = current_user.school`, the runtime treats the field condition as both authorization AND scoping. Any authenticated user at the same school gets full access — including students seeing staff records, exclusion records, and consent data.

The DSL author's intent was: "staff at the same school who have an appropriate role can see school-scoped data." But the language has no way to express "role + scope" as a compound requirement.

## Design Principle

Two layers, both explicit, both default-deny:

- **No permit → 403.** If a user's role doesn't match any permit rule, the request is rejected.
- **No scope → 0 records.** If a user passes the permit gate but no scope rule covers their role, they see nothing.

A missing rule at either layer is a bug surfaced by the access matrix, not a silent gap through which data leaks.

## New Keyword: `scope:`

### Syntax

```dsl
entity StaffMember "Staff Member":
  permit:
    list: role(teacher, school_admin, head_of_department, senior_leader)
    read: role(teacher, school_admin, head_of_department, senior_leader)
    list: role(trust_admin)
    read: role(trust_admin)

  scope:
    list: school = current_user.school
      for: teacher, school_admin, head_of_department, senior_leader
    list: all
      for: trust_admin
    read: school = current_user.school
      for: teacher, school_admin, head_of_department, senior_leader
    read: all
      for: trust_admin
```

### Semantics

**`permit:` blocks** — authorization gate. Evaluated without record data. Contains ONLY:
- `role()` checks
- `authenticated` (any logged-in user)
- Logical combinations of role checks (`role(a) or role(b)`)

Field conditions inside `permit:` are a **parser error**:
```
ERROR: permit: list: school = current_user.school
  Field conditions belong in scope:, not permit:.
```

**`scope:` blocks** — row filter. Evaluated with record data. Each rule has:
- A field condition (`school = current_user.school`, `owner = current_user`, `all`)
- A `for:` clause naming which roles this scope applies to

`scope: list: all` means "no filter — see all records." It is the explicit opt-out from scoping.

**`for:` clause** — binds a scope rule to specific roles. Required on every scope rule. A role that passes the permit gate but has no matching scope rule sees **zero records** (default-deny at the scope layer).

**`forbid:` blocks** — unchanged. Override permit (Cedar semantics: FORBID > PERMIT > default-deny).

**`visible:` blocks** — unchanged. Row-level visibility for anonymous/authenticated contexts (orthogonal to RBAC).

**`audit:` blocks** — unchanged. Compliance logging triggers.

### The `all` keyword

`scope: list: all` means "this role sees all records with no filter applied." It is NOT the same as omitting the scope rule — omission means default-deny (0 records).

```dsl
scope:
  list: all
    for: oracle, trust_admin
  list: realm = current_user.realm
    for: sovereign, architect
```

### Evaluation flow

```
Request arrives
  │
  ├─ Tier 1: permit/forbid gate (no record data)
  │   ├─ Collect permit/forbid rules for this operation
  │   ├─ Evaluate Cedar semantics: FORBID > PERMIT > default-deny
  │   ├─ FORBID match → 403
  │   ├─ PERMIT match → continue (note which role matched)
  │   └─ No match → 403
  │
  ├─ Tier 2: scope filter (SQL WHERE)
  │   ├─ Collect scope rules for this operation
  │   ├─ Find scope rules where for: includes the user's matched role
  │   ├─ If scope rule is `all` → no filter
  │   ├─ If scope rule has field condition → resolve to SQL filter
  │   ├─ If NO scope rule matches the user's role → empty result (0 records)
  │   └─ Merge scope filters with visibility filters
  │
  └─ Execute query with merged filters
```

### Role matching in scope

The `for:` clause uses role names, not persona IDs. A user may have multiple roles. The scope engine finds the first scope rule where any of the user's roles appears in `for:`. If multiple scope rules match, they are OR'd (the user sees the union of scoped results).

Example: a user with roles `[teacher, head_of_department]` and scope rules:
```dsl
scope:
  list: school = current_user.school
    for: teacher
  list: department = current_user.department
    for: head_of_department
```
The user sees records matching `school = their_school OR department = their_department`.

## Breaking Change

Field conditions in `permit:` blocks are no longer valid. The migration is mechanical:

```dsl
# Before (v0.43)
permit:
  list: owner = current_user
  list: role(admin)

# After (v0.44)
permit:
  list: authenticated
  list: role(admin)

scope:
  list: owner = current_user
    for: *
  list: all
    for: admin
```

`for: *` is shorthand for "all roles that pass the permit gate." It means "this scope applies to everyone who is authorized." This covers the common `owner = current_user` pattern where any authenticated user sees only their own records.

The parser produces a clear error message with the fix:
```
ERROR at line 5: Field condition 'owner = current_user' in permit: block.
  Field conditions define row filtering, not authorization.
  Move to a scope: block:
    scope:
      list: owner = current_user
        for: *
```

## Impact on Access Matrix

`PolicyDecision` values:

| Decision | Meaning |
|----------|---------|
| `PERMIT` | Role gate allows, scope is `all` (no filter) |
| `PERMIT_SCOPED` | Role gate allows, scope filters applied |
| `DENY` | Forbidden or default-deny at permit layer |
| `PERMIT_NO_SCOPE` | Role gate allows, but no scope rule covers this role (WARNING — 0 records) |
| `PERMIT_UNPROTECTED` | No permit rules defined (backward-compat allows all) |

`PERMIT_NO_SCOPE` is a warning, not an error — it indicates a likely DSL authoring gap. The matrix surfaces it:
```
WARNING: role 'intern' passes permit for StaffMember.list but has no matching scope rule — will see 0 records
```

## Impact on Shapes Validation App

```dsl
entity Shape "Shape":
  permit:
    list: role(oracle)
    read: role(oracle)
    create: role(oracle)
    update: role(oracle)
    delete: role(oracle)
    list: role(sovereign)
    read: role(sovereign)
    create: role(sovereign)
    update: role(sovereign)
    delete: role(sovereign)
    list: role(architect)
    read: role(architect)
    list: role(chromat)
    read: role(chromat)
    list: role(forgemaster)
    read: role(forgemaster)
    list: role(witness)
    read: role(witness)

  scope:
    list: all
      for: oracle
    read: all
      for: oracle
    list: realm = current_user.realm
      for: sovereign, architect, witness
    read: realm = current_user.realm
      for: sovereign, architect, witness
    list: colour = current_user.colour
      for: chromat
    read: colour = current_user.colour
      for: chromat
    list: material = metal or material = stone
      for: forgemaster
    read: material = metal or material = stone
      for: forgemaster

  forbid:
    list: material = shadow
    read: material = shadow
```

Outsider: no permit rule → 403. Oracle: permit + scope `all` → all records. Chromat: permit + scope by colour → filtered. Forgemaster: permit + scope by material + forbid shadow → filtered minus shadow.

## Impact on Bootstrap Workflow

Step 7 becomes:

```
7a. Add permit: blocks with ONLY role() checks to every entity.
7b. Add scope: blocks with field conditions and for: clauses.
    Every role that passes a permit: gate must have a matching scope: rule.
    Use scope: list: all for: <role> for roles that see all records.
    Use scope: list: <field> = current_user.<attr> for: <role> for scoped access.
```

The access matrix (step 14) now checks for `PERMIT_NO_SCOPE` warnings in addition to `PERMIT_UNPROTECTED`.

## Impact on Knowledge Base

The `access_rules` concept in the semantics KB must be updated to explain the two-block pattern. The `knowledge(operation='concept', term='access_rules')` response should show:

```
Access control uses two blocks:

  permit: — WHO may access (roles only)
    list: role(teacher, admin)
    read: role(teacher, admin)

  scope: — WHAT they can see (field filters)
    list: school = current_user.school
      for: teacher
    list: all
      for: admin
```

## IR Changes

### New IR type: `ScopeRule`

```python
@dataclass
class ScopeRule:
    operation: PermissionKind  # list, read, create, update, delete
    condition: ConditionExpr | None  # None means `all`
    personas: list[str]  # from `for:` clause; ["*"] means all authorized
```

### Entity AccessSpec extension

```python
@dataclass
class AccessSpec:
    permissions: list[PermissionRule]  # permit/forbid — existing
    scopes: list[ScopeRule]  # NEW — scope rules
    visibility: list[VisibilityRule]  # existing
```

### Backend spec extension

`EntityAccessSpec` gains a `scopes: list[ScopeRuleSpec]` field, parallel to `permissions`.

## Parser Changes

The parser mixin for entities (`_parse_policy_block`) handles `scope:` as a new block type alongside `permit:`, `forbid:`, and `audit:`. Within `scope:`, each rule accepts:
- An operation keyword (`list`, `read`, `create`, `update`, `delete`)
- A condition expression (field conditions, `all`, logical combinations)
- An indented `for:` line naming roles

Field conditions inside `permit:` blocks trigger a parser error with migration guidance.

## Enforcement Changes

### Route generator (`route_generator.py`)

The LIST gate logic simplifies dramatically:

1. `permit:` rules are ALL role-check-only → always evaluable at the gate
2. If denied → 403
3. If permitted → look up `scope:` rules for the matched role(s)
4. If scope is `all` → no SQL filter
5. If scope has a field condition → resolve to SQL filter
6. If no scope rule matches → empty result set

The `_is_field_condition` function becomes unnecessary — field conditions can't appear in `permit:` blocks.

### Page routes (`page_routes.py`)

Same two-tier evaluation. The page handler checks permit at the gate (same as today's #527 fix), then passes scope rules to the data fetch layer.

## Implementation Order

1. **IR types** — add `ScopeRule` to `ir/access.py`, extend `AccessSpec`
2. **Parser** — add `scope:` block parsing, reject field conditions in `permit:`
3. **Backend spec** — add `ScopeRuleSpec`, extend `EntityAccessSpec`
4. **Converter** — convert `ScopeRule` to `ScopeRuleSpec`
5. **Route generator** — simplify gate (permit-only), add scope filter resolution
6. **Page routes** — propagate scope filters to UI data fetch
7. **Access matrix** — add `PERMIT_SCOPED` and `PERMIT_NO_SCOPE` decisions
8. **Shapes app** — update DSL with scope blocks
9. **Knowledge base** — update access_rules concept
10. **Bootstrap** — update step 7 instructions

## Non-Goals

- Scope inheritance (child entity inherits parent scope) — separate feature
- Dynamic scope rules (grant-based runtime scoping) — the `grant_schema` system handles this
- Write-operation scoping (scope on create/update/delete) — initially support only list/read scoping; write operations use permit-only semantics
