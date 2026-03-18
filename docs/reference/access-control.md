# Access Control

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

DAZZLE uses Cedar-style access rules with three layers: entity-level permit/forbid blocks, surface-level access restrictions, and workspace-level persona allow/deny lists. Default policy is deny. This page covers access rule syntax, authentication integration, and RBAC patterns.

---

## Access Rules

Inline access control rules on entities. Legacy syntax uses access: blocks with read/write permissions. Cedar-style syntax (v0.21+) uses permit:/forbid:/audit: blocks for fine-grained RBAC with NIST SP 800-162 alignment. Evaluation order: FORBID > PERMIT > default-deny.

### Syntax

```dsl
# Legacy access: block (read/write permissions)
access:
  read: <condition>
  write: <condition>

# Cedar-style blocks (v0.21+)
permit:
  <action>: <condition>

forbid:
  <action>: <condition>

audit:
  <action>: <condition>

# Expressions:
# field = current_user - Field matches logged-in user
# role(<name>) - User has the specified role
# field = value - Field equals literal value
# Combine with: and, or

# Cedar-style actions: read, write, create, update, delete, approve, prescribe, etc.
# Cedar evaluation: FORBID rules override PERMIT; default is deny
```

### Example

```dsl
# Legacy style
entity Document "Document":
  owner: ref User required
  is_public: bool = false

  access:
    read: owner = current_user or is_public = true or role(admin)
    write: owner = current_user or role(admin)

# Cedar-style (v0.21+) - fine-grained RBAC
entity Prescription "Prescription":
  patient: ref Patient required
  prescriber: ref Doctor required
  status: enum[draft,active,dispensed,cancelled]=draft

  permit:
    read: role(doctor) or role(pharmacist) or role(nurse)
    prescribe: role(doctor)
    dispense: role(pharmacist)

  forbid:
    prescribe: role(pharmacist)
    dispense: role(doctor)

  audit:
    read: role(admin)
    prescribe: role(compliance_officer)
    dispense: role(compliance_officer)
```

### Best Practices

- Use = for equality (not ==)
- Start with restrictive rules, expand as needed
- Use role() for administrative access
- Combine with persona scopes for UI filtering
- Cedar evaluation order: FORBID > PERMIT > default-deny
- Use audit: blocks for compliance logging of sensitive actions
- Use forbid: for separation-of-duty constraints (e.g., prescriber cannot dispense)

**Related:** [Entity](entities.md#entity), [Persona](ux.md#persona), [Invariant](entities.md#invariant), [Cedar Rbac](patterns.md#cedar-rbac)

---

## Scope Rules

Row-level filtering rules on entities. `scope:` blocks control **what rows** a permitted role sees — they are separate from `permit:` blocks, which control **whether** a role may access an endpoint at all.

The two-block pattern is mandatory:

- `permit:` — authorization gate. Contains **only** `role()` checks. Field conditions inside `permit:` are a parser error.
- `scope:` — row filter. Contains field conditions with `for:` clauses. Evaluated at query time, not at the gate.

Every role that passes a `permit:` gate must have a matching `scope:` rule, or `scope: all` for unrestricted row access.

### Syntax

```dsl
scope:
  for role(<name>): <field_condition>
  for role(<name>): all
  *

# for role(<name>): <condition>  — rows matching condition are visible to role
# for role(<name>): all          — all rows are visible to role (unrestricted)
# *                              — all rows visible to every permitted role (wildcard)

# Field conditions use standard ConditionExpr:
#   field = current_user
#   field = value
#   field != value
#   Combine with: and, or
```

### Example

```dsl
entity Task "Task":
  id: uuid pk
  title: str(200) required
  owner: ref User required
  team: ref Team required
  status: enum[open,closed]=open

  # Authorization: who may access this entity
  permit:
    list: role(admin) or role(manager) or role(member)
    read: role(admin) or role(manager) or role(member)
    create: role(admin) or role(manager)
    update: role(admin) or role(manager) or role(member)
    delete: role(admin)

  # Row filtering: what each permitted role sees
  scope:
    for role(admin): all
    for role(manager): team = current_user.team
    for role(member): owner = current_user

entity Shape "Shape":
  id: uuid pk
  colour: enum[red,blue,green]
  realm: ref Realm required

  permit:
    list: role(oracle) or role(sovereign)
    read: role(oracle) or role(sovereign)

  # Wildcard: all permitted roles see all rows
  scope:
    *
```

### The `all` keyword and `*` wildcard

- `for role(admin): all` — the named role sees every row, no filter applied.
- `*` on its own line — every permitted role sees every row. Use when no per-role scoping is needed. Equivalent to writing `all` for each permitted role individually.

### Default-deny at both layers

- If a role has no matching `permit:` rule, the endpoint gate rejects it with HTTP 403.
- If a role passes the gate but has no `scope:` rule (and no `*`), it sees zero rows. This is intentional default-deny at the row level.

### Best Practices

- Never put field conditions inside `permit:` — they are a parser error.
- Every permitted role needs an explicit `scope:` entry or a `*` wildcard.
- Use `for role(admin): all` to grant unrestricted access to administrative roles.
- Prefer named `for:` clauses over `*` when different roles need different row visibility.

**Related:** [Access Rules](access-control.md#access-rules), [Entity](entities.md#entity), [Runtime Evaluation Model](access-control.md#runtime-evaluation-model)

---

## Visibility Rules

Row-level visibility rules on entities. Controls which records are visible based on authentication state (anonymous or authenticated). Evaluated before permission rules to determine which records a user can see in list/query results. Uses ConditionExpr for the filter condition.

### Syntax

```dsl
visible:
  when anonymous: <condition>
  when authenticated: <condition>

# Auth contexts:
#   anonymous     - User is not logged in
#   authenticated - Any logged-in user

# Condition is a standard ConditionExpr:
#   field = value, field != value, role(name), field = current_user
#   Combine with: and, or
```

### Example

```dsl
entity Document "Document":
  id: uuid pk
  title: str(200) required
  is_public: bool = false
  created_by: ref User

  visible:
    when anonymous: is_public = true
    when authenticated: is_public = true or created_by = current_user

entity Post "Blog Post":
  id: uuid pk
  published: bool = false
  author: ref User required

  visible:
    when anonymous: published = true
    when authenticated: published = true or author = current_user
```

### Best Practices

- Use anonymous visibility for public-facing content
- Authenticated visibility should include the owner check (created_by = current_user)
- Combine with permission rules for full access control
- Visibility filters apply at query time - no data leaks in list views

**Related:** [Access Rules](access-control.md#access-rules), [Entity](entities.md#entity), [Persona](ux.md#persona), [Surface Access](access-control.md#surface-access)

---

## Surface Access

Access control on surfaces (UI screens). Controls who can view and interact with a surface. Three levels: public (no auth), authenticated (any logged-in user), or persona-restricted (named personas only). Used by E2E test generators to create protected-route tests.

### Syntax

```dsl
surface <name> "<Title>":
  ...
  access: public
  access: authenticated
  access: persona(<name1>, <name2>, ...)

# access: public          → require_auth=false, anyone can access
# access: authenticated   → require_auth=true, any logged-in user
# access: persona(Admin, Manager) → require_auth=true, only listed personas
```

### Example

```dsl
# Public surface - no login required
surface landing_page "Welcome":
  uses entity Page
  mode: view
  access: public

# Authenticated - any logged-in user
surface my_tasks "My Tasks":
  uses entity Task
  mode: list
  access: authenticated

# Persona-restricted - only these roles
surface admin_panel "Admin Panel":
  uses entity User
  mode: list
  access: persona(Admin, SuperAdmin)
```

### Best Practices

- Default to authenticated when auth is enabled globally
- Use persona() for admin-only or role-specific screens
- Public surfaces should only show non-sensitive data
- Pair with entity-level access rules for defense in depth

**Related:** [Access Rules](access-control.md#access-rules), [Surface](surfaces.md#surface), [Persona](ux.md#persona), [Workspace Access](access-control.md#workspace-access), [Visibility Rules](access-control.md#visibility-rules)

---

## Workspace Access

Access control on workspaces. Defines who can access a workspace dashboard. Three levels: public, authenticated, or persona-restricted. Default is authenticated when auth is enabled globally. Syntax is the same as surface access.

### Syntax

```dsl
workspace <name> "<Title>":
  ...
  access: public
  access: authenticated
  access: persona(<name1>, <name2>, ...)

# access: public          → level=public, no login required
# access: authenticated   → level=authenticated, any logged-in user (default)
# access: persona(Admin)  → level=persona, only listed personas can access
```

### Example

```dsl
# Public dashboard - visible without login
workspace public_metrics "Public Metrics":
  purpose: "Public-facing KPI dashboard"
  access: public

  metrics:
    aggregate:
      total_users: count(User)
    display: metrics

# Admin-only workspace
workspace admin_dashboard "Admin Dashboard":
  purpose: "System administration"
  access: persona(Admin, SuperAdmin)

  users:
    source: User
    display: list
    action: user_edit

# Default: authenticated (explicit for clarity)
workspace team_board "Team Board":
  purpose: "Team task overview"
  access: authenticated

  tasks:
    source: Task
    filter: status != closed
    sort: priority desc
    display: list
```

### Best Practices

- Use persona() for role-specific dashboards
- Public workspaces should aggregate non-sensitive data only
- Default is authenticated - omit access: if that is sufficient

**Related:** [Access Rules](access-control.md#access-rules), [Workspace](workspaces.md#workspace), [Persona](ux.md#persona), [Surface Access](access-control.md#surface-access)

---

## Runtime Evaluation Model

Access rules evaluate in two tiers at runtime. The `permit:` and `scope:` blocks map directly onto these two tiers.

### Tier 1: Entity-Level Gate (permit: blocks)

Before any database query runs, the route handler performs a **gate check**: "Does this user have permission to access this endpoint at all?" This check calls `evaluate_permission(operation, record=None, context)` — note `record=None`, meaning no row data is available.

**`permit:` blocks are evaluated here.** They contain only `role()` checks, which can be resolved with just the user's roles. Field conditions cannot appear in `permit:` (they are a parser error), so the gate is always unambiguous.

If a role has no matching `permit:` rule, the gate returns HTTP 403 immediately.

### Tier 2: Row-Level Filters (scope: blocks)

After the gate, the handler builds SQL filters from two sources:

1. **Visibility rules** (`visible:` blocks) — converted to SQL WHERE clauses based on auth state
2. **Scope rules** (`scope:` blocks) — the `for role(<name>): <condition>` clause matching the authenticated user's role is extracted and merged into the query

These filters ensure only authorized rows are returned. They run at query time, when record data is available. A role with no matching `scope:` entry (and no `*` wildcard) sees zero rows by default.

### Evaluation Flow

```
Request arrives
  │
  ├─ Tier 1: Gate check (permit: blocks only — no record available)
  │   ├─ Does any permit: rule match the user's roles?
  │   │   ├─ FORBID match → 403
  │   │   ├─ PERMIT match → continue to Tier 2
  │   │   └─ No match → 403 (default-deny)
  │   └─ Note: field conditions inside permit: are a parser error, never reached here
  │
  ├─ Build SQL filters
  │   ├─ Visibility filters (visible: blocks)
  │   └─ Scope filters (scope: blocks — for role(<name>): <condition>)
  │       ├─ Matching for: clause found → apply field condition as WHERE clause
  │       ├─ for role(<name>): all → no WHERE clause added (all rows)
  │       └─ * wildcard → no WHERE clause for any role (all rows)
  │
  ├─ Execute query with merged filters
  │
  └─ Tier 2: Post-fetch check (per record, for detail/update/delete)
      └─ evaluate_permission(op, record, ctx) — full condition evaluation
```

### Why Two Separate Blocks?

The gate (Tier 1) runs before any database query, so it cannot evaluate field conditions — there is no record yet. Putting field conditions inside `permit:` would force the gate to fail them (field lookup returns `None`), causing legitimate users to receive HTTP 403 even when they should see a filtered result set.

`scope:` blocks exist precisely to express "this role may access the endpoint, but only sees rows matching this condition." They are evaluated at query time (Tier 2), where record data is available.

This was the lesson of PR #503: a LIST gate that evaluated all `permit:` rules against `record=None` broke field-condition rules. The fix separated the concern — `permit:` for who, `scope:` for what.

### Rule Type Summary

| Block | Pattern | Enforcement Point | Notes |
|-------|---------|-------------------|-------|
| `permit:` | `list: role(admin)` | Tier 1 gate | Fast — no DB touch |
| `permit:` | `list: role(teacher) or role(admin)` | Tier 1 gate | Multiple roles in one rule |
| `scope:` | `for role(teacher): school = current_user.school` | Tier 2 row filter | Applied as SQL WHERE |
| `scope:` | `for role(admin): all` | Tier 2 (no-op) | No filter added |
| `scope:` | `*` | Tier 2 (no-op) | All permitted roles see all rows |
| `visible:` | `when authenticated: owner = current_user` | Tier 2 row filter | Auth-state filter |

### Best Practices

- **`permit:` is for who, `scope:` is for what.** Never mix them. Field conditions in `permit:` are a parser error.
- **Every permitted role needs a scope entry.** Either a named `for role(X):` clause or a `*` wildcard. A role with no scope entry sees zero rows.
- **Use `for role(admin): all`** to grant unrestricted row access to administrative roles.
- **Pure role gates are fast** — the gate rejects unauthorized users before touching the DB.
- **`*` wildcard** simplifies entities where all permitted roles see all rows with no per-role distinction.

**Related:** [Access Rules](access-control.md#access-rules), [Scope Rules](access-control.md#scope-rules), [Cedar Rbac](patterns.md#cedar-rbac), [Visibility Rules](access-control.md#visibility-rules)

---

## Authentication

Session-based authentication system in Dazzle. Uses cookie-based sessions with SQLite storage. Auth is optional and can be enabled/disabled per project.

### Example

```dsl
# In DSL, use personas to define role-based access:
ux:
  for admin:
    scope: all
  for member:
    scope: owner = current_user

# API login:
POST /auth/login
Content-Type: application/json
{"username": "admin", "password": "secret"}

# Response sets session cookie automatically
```

**Related:** [Persona](ux.md#persona), [Scope](ux.md#scope)

---
