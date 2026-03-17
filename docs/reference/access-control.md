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

Access rules evaluate in two tiers at runtime. Understanding this distinction is critical when writing rules that mix role checks with field conditions.

### Tier 1: Entity-Level Gate

Before any database query runs, the route handler performs a **gate check**: "Does this user have permission to access this endpoint at all?" This check calls `evaluate_permission(operation, record=None, context)` — note `record=None`, meaning no row data is available.

**Only pure role-check rules can be evaluated at the gate.** A rule like `list: role(teacher)` can be resolved with just the user's roles. A rule like `list: school = current_user.school` cannot — it references a field on the record, and there is no record yet.

The gate therefore **skips rules that contain field conditions** and only enforces rules where every condition is a role check. If all LIST rules have field conditions, the gate passes everyone through and lets Tier 2 handle enforcement.

### Tier 2: Row-Level Filters

After the gate, the handler builds SQL filters from two sources:

1. **Visibility rules** (`visible:` blocks) — converted to SQL WHERE clauses based on auth state
2. **Cedar row filters** — field conditions from `permit:` rules (e.g., `school = current_user.school`) are extracted and merged into the query

These filters ensure only authorized rows are returned. They run at query time, when record data is available.

### Evaluation Flow

```
Request arrives
  │
  ├─ Tier 1: Gate check (no record)
  │   ├─ Collect LIST/READ rules
  │   ├─ Any field conditions? → skip gate, pass through
  │   └─ All pure role checks? → evaluate_permission(LIST, None, ctx)
  │       ├─ FORBID match → 403
  │       ├─ PERMIT match → continue
  │       └─ No match → 403 (default-deny)
  │
  ├─ Build SQL filters
  │   ├─ Visibility filters (visible: blocks)
  │   └─ Cedar row filters (field conditions from permit: rules)
  │
  ├─ Execute query with merged filters
  │
  └─ Tier 2: Post-fetch check (per record, for detail/update/delete)
      └─ evaluate_permission(op, record, ctx) — full condition evaluation
```

### Why This Matters

A rule like `permit: list: school = current_user.school` grants LIST access, but **only to rows matching the condition**. If the gate tried to evaluate this rule with `record=None`, it would fail (the field lookup returns `None`), and the user would get a 403 even though they should see a filtered result set.

This is why #503 was a regression: #502 added a LIST gate that evaluated *all* rules — including field-condition rules — against `record=None`. Field-condition rules always failed at the gate, blocking legitimate access. The fix was to make the gate skip any rule with field conditions, deferring enforcement to the row-level filter stage.

### Rule Type Summary

| Rule Pattern | Gate Evaluable? | Enforcement Point |
|---|---|---|
| `list: role(admin)` | Yes | Tier 1 gate |
| `list: school = current_user.school` | No | Tier 2 row filter |
| `list: role(teacher) or school = current_user.school` | No (has field condition) | Tier 2 row filter |
| `read: role(doctor)` | Yes | Tier 1 gate (detail) |
| `read: patient = current_user` | No | Tier 2 per-record check |

### Best Practices

- **Pure role gates are fast** — they reject unauthorized users before touching the DB. Prefer `list: role(X)` when the role alone determines access.
- **Field-condition rules are filters** — they allow the endpoint but restrict which rows are returned. Use these for multi-tenant or ownership-scoped access.
- **Mixing both** — if you need both a gate and a filter, write separate rules: one pure role rule for the gate, and a field-condition rule for row filtering. They compose via Cedar's FORBID > PERMIT > default-deny semantics.
- **OR conditions with mixed types** — `list: role(admin) or owner = current_user` has a field condition, so the gate skips it entirely. The admin gets through via the row filter (which sees the unconditional role match and returns all rows). This works but is less efficient than separate rules.

**Related:** [Access Rules](access-control.md#access-rules), [Cedar Rbac](patterns.md#cedar-rbac), [Visibility Rules](access-control.md#visibility-rules)

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
