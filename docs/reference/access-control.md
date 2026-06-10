# Access Control

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

DAZZLE uses Cedar-style access rules with three layers: entity-level permit/forbid blocks, surface-level access restrictions, and workspace-level persona allow/deny lists. Default policy is deny. This page covers access rule syntax, authentication integration, and RBAC patterns.

---

## Access Rules

Inline access control rules on entities. Cedar-style syntax uses two separate blocks: permit: (WHO may access — role checks only) and scope: (WHAT they can see — row-level field conditions with as: clauses). Scope rules compile to a formal predicate algebra with static FK graph validation. Legacy access: blocks are still supported. Evaluation order: FORBID > PERMIT > default-deny. Field conditions in permit: are a parser error — they must live in scope: blocks.

### Syntax

```dsl
# Two-block pattern (recommended): separate WHO from WHAT
permit:
  <action>: role(<name>)        # WHO — pure role checks only

scope:
  <action>: <field-condition>   # WHAT — row-level filter
    as: <role>, <role>          # which roles this filter applies to
  <action>: all                 # 'all' means no filter (full table access)
    as: <role>

# forbid: block and audit: directive
forbid:
  <action>: role(<name>)        # separation-of-duty constraints

audit: all                      # compliance logging — or a subset:
audit: [create, update, delete]

# permit: expressions — role checks only (field conditions are a parser error here):
# role(<name>) - User has the specified role
# role(a) or role(b) - Either role

# scope: expressions — field conditions only (compile to predicate algebra):
# field = current_user - Field matches logged-in user
# field = current_user.field - Field matches a property of the logged-in user
# field = value - Field equals literal value
# parent.field = current_user - FK path traversal (depth-N, nested subquery)
# via Entity(field = current_user, field = id) - EXISTS subquery (junction table)
# not via Entity(field = current_user, field = id) - NOT EXISTS (exclusion)
# not (condition) - Parenthesised negation
# Combine with: and, or — all boolean logic compiles to SQL

# Valid actions in permit:/forbid: blocks: create, read, update, delete, list
# (model domain verbs like "prescribe"/"dispense" onto these CRUD operations)
# Cedar evaluation: FORBID rules override PERMIT; default is deny

# Legacy access: block (read/write permissions — still supported)
access:
  read: <condition>
  write: <condition>
```

### Example

```dsl
# Two-block pattern: permit: gates WHO, scope: gates WHAT
entity Shape "Shape":
  realm: ref Realm required
  creator: ref User required
  colour: enum[red,blue,green] required

  # WHO may access — role checks only
  permit:
    list: role(oracle)
    read: role(oracle)
    create: role(oracle) or role(forgemaster)
    update: role(oracle)
    delete: role(oracle)

  # Separation of duty
  forbid:
    delete: role(forgemaster)

  # WHAT they can see — row-level filters with as: clauses
  scope:
    list: all                              # oracle sees everything
      as: oracle
    read: all
      as: oracle
    create: all
      as: oracle
    create: realm = current_user.realm     # forgemaster scoped to their realm
      as: forgemaster
    update: all
      as: oracle
    delete: all
      as: oracle
    list: realm = current_user.realm or creator = current_user
      as: forgemaster
    read: realm = current_user.realm or creator = current_user
      as: forgemaster

# Cedar-style fine-grained RBAC with forbid: and audit:
entity Prescription "Prescription":
  patient: ref Patient required
  prescriber: ref Doctor required
  status: enum[draft,active,dispensed,cancelled]=draft

  permit:
    read: role(doctor) or role(pharmacist) or role(nurse)
    create: role(doctor)        # only doctors prescribe (create)
    update: role(pharmacist)    # only pharmacists dispense (update)

  forbid:
    create: role(pharmacist)    # pharmacists cannot prescribe
    update: role(doctor)        # doctors cannot dispense

  audit: [read, create, update]

# Legacy style (still supported)
entity Document "Document":
  owner: ref User required
  is_public: bool = false

  access:
    read: owner = current_user or is_public = true or role(admin)
    write: owner = current_user or role(admin)
```

### Best Practices

- Use = for equality (not ==)
- Start with restrictive rules, expand as needed
- permit: contains role checks only — field conditions belong in scope:
- scope: rules use as: clauses to bind row-level filters to specific roles
- Use 'all' in scope: for roles that should see the full table (e.g., admins)
- Use as: * in scope: to apply a filter to all permitted roles
- Cedar evaluation order: FORBID > PERMIT > default-deny
- Use audit: blocks for compliance logging of sensitive actions
- Use forbid: for separation-of-duty constraints (e.g., prescriber cannot dispense)

**Related:** [Entity](entities.md#entity), [Persona](ux.md#persona), [Invariant](entities.md#invariant), [Cedar Rbac](patterns.md#cedar-rbac)

---

## Ownership Pattern

Row-level ownership filtering for personal data. Uses scope: blocks (not permit:) because ownership is a row-level concern. The permit: block controls WHO (role checks), the scope: block controls WHICH ROWS (field conditions). There is no 'owner' keyword — use the actual field name with '= current_user'.

### Syntax

```dsl
entity ReadingProgress "Reading Progress":
  id: uuid pk
  user_id: ref User required
  work: ref Work required
  chapter: int = 1
  progress_pct: float = 0.0

  permit:
    create: role(reader) or role(author) or role(admin)
    read: role(reader) or role(author) or role(admin)
    update: role(reader) or role(author) or role(admin)
    delete: role(admin)

  scope:
    read: user_id = current_user
      as: reader, author
    update: user_id = current_user
      as: reader, author
    read: all
      as: admin
```

### Best Practices

- Always pair ownership permit: rules with a scope: block that filters by the owner field
- Use 'all as: admin' in scope: to give admins visibility to all rows
- Name the ownership field explicitly (user_id, not just 'user') for clarity
- Add a ref constraint on the ownership field to link to the User entity

**Related:** [Access Rules](access-control.md#access-rules), Scope Runtime, [Cedar Rbac](patterns.md#cedar-rbac)

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

## Authentication

Session-based authentication system in Dazzle. Uses cookie-based sessions backed by the configured PostgreSQL database. Auth is optional and can be enabled/disabled per project.

### Example

```dsl
# In DSL, use personas to define role-based access:
persona admin "Admin":
  role: admin

persona member "Member":
  role: member

entity Task "Task":
  owner: ref User required

  permit:
    read: role(admin) or role(member)
    update: role(admin) or role(member)

  scope:
    read: all
      as: admin
    read: owner = current_user
      as: member
    update: owner = current_user
      as: member

# API login:
POST /auth/login
Content-Type: application/json
{"username": "admin", "password": "secret"}

# Response sets session cookie automatically
```

**Related:** [Persona](ux.md#persona), [Scope](ux.md#scope)

---
