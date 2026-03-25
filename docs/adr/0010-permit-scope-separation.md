# ADR-0010: Permit/Scope Separation

**Status:** Accepted
**Date:** 2026-03-18

## Context

Before this decision, Dazzle's access control used a single `permit:` block that mixed two distinct concerns:

1. **Role authorization** — which personas may perform an action at all
2. **Row filtering** — which rows a permitted user may see or modify

Issue #526 identified that placing field conditions inside `permit:` blocks produced a critical security flaw: a user matching the field condition was granted access regardless of their role. For example:

```dsl
# UNSAFE — pre-ADR-0010
permit: admin or (teacher and school_id = current_user.school)
```

A user with no role but a matching `school_id` would pass the field condition branch and be authorized. The permit block evaluated field conditions as an alternative to role checks rather than as an additional constraint.

The fix requires architectural separation: role checks and row filters must be enforced in sequence, not as alternatives.

## Decision

Access control is split into two strictly separated layers:

**`permit:` blocks** — role-only authorization (pure RBAC):
- Accept only persona/role names and boolean combinations thereof
- Field conditions are a **parse error** inside `permit:`
- Default-deny: if no `permit:` block matches, access is refused

**`scope:` blocks** — row filtering (ABAC field conditions):
- Mandatory `for:` clause naming the personas the scope applies to
- Field conditions compile to the predicate algebra (ADR-0009)
- Default-deny: rows not matching an active scope are hidden
- Applied only after `permit:` has already granted access

The two layers are enforced in order: permit gates on role first, scope filters rows second. A user must pass both layers to access a row.

## Consequences

### Positive

- Field conditions can never substitute for role checks — privilege escalation via field match is structurally impossible
- Each layer is independently auditable: RBAC matrix covers `permit:`, predicate algebra covers `scope:`
- RBAC static matrix verification (CI gate) operates cleanly on `permit:` blocks alone
- Scope predicates can be compiled to Postgres RLS policies without tangling with role logic

### Negative

- Existing DSL files using field conditions in `permit:` blocks require migration — this is a breaking change
- Two separate blocks increase DSL verbosity for simple cases
- `for:` clause on `scope:` is mandatory, not inferred — slightly more typing

### Neutral

- Both layers default-deny, so omitting either is safe (restrictive) rather than permissive
- The RBAC verifier (`src/dazzle/rbac/`) validates `permit:` blocks; the scope validator validates `scope:` blocks

## Alternatives Considered

### 1. Field Conditions in Permit Blocks

Allow field conditions to continue appearing in `permit:` blocks, but require an explicit role check alongside them.

**Rejected:** The parser cannot statically enforce "role check required alongside field condition" without introducing complex validation rules that are easy to misread. Structural separation is unambiguous.

### 2. Single Unified Authorization Layer

Merge permit and scope into one block that handles both roles and field conditions.

**Rejected:** A unified layer cannot be independently compiled to RBAC matrix (role-only) and RLS policy (row filter). Static analysis of the RBAC matrix requires isolating role predicates.

### 3. Implicit Scope Defaults

Infer scope rules from entity ownership conventions (e.g., automatically scope to `current_user` for owned entities).

**Rejected:** Implicit defaults hide authorization logic from static analysis and DSL audits. Every access control decision must be explicit in the DSL.

## Implementation

- DSL parser: field conditions in `permit:` are rejected with a descriptive error referencing this ADR
- `for:` clause on `scope:` blocks is validated at parse time — missing `for:` is a hard error
- Runtime enforces permit check before scope filter in all query paths
- `dazzle lint` reports any `permit:` blocks that were valid before this change (migration aid)
- See `src/dazzle/rbac/` for static matrix verification and `src/dazzle/core/ir/predicates.py` for scope IR
