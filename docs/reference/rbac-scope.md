# RBAC scope rules — operation-by-operation reference

> **Status:** canonical reference as of v0.71.19.
> Closes the discoverability gap surfaced in
> [#1123](https://github.com/manwithacat/dazzle/issues/1123).

`scope:` rules on an entity declare **row-level authorization** —
which rows a permitted user is allowed to operate on. They sit
alongside `permit:` rules, which declare **operation-level
authorization** (which user roles may perform an op at all).

The two-block split is mandatory per ADR-0010. This document covers
the second half — what `scope:` does for each of the five operations,
when it enforces at runtime, and what the canonical idiom looks like.

## The decision table

| Op | Where the predicate is evaluated | Lint message when missing | Status |
|---|---|---|---|
| `list` | Pre-query — folded into the SQL `WHERE` of the LIST endpoint. | "will see 0 records" | ✅ Enforced since v0.45.0 |
| `read` | Pre-query — folded into the WHERE of the read-by-id query. (Plumbed via the same path as `list` in v0.71.19.) | "will see 0 records" | ✅ Enforced since v0.71.19 |
| `update` | Pre-write — folded into the WHERE of the pre-read that the permit-gate uses; if the predicate rejects the target row, the request 404s before the update SQL runs. | "the request will 404 at runtime — add a `scope: update:` rule or `scope: all as: <persona>`" | ✅ Enforced since v0.71.19 |
| `delete` | Same as `update`. | Same as `update`. | ✅ Enforced since v0.71.19 |
| `create` | Pre-write — predicate is evaluated against the payload AFTER framework defaulting (`current_user` injection, persona-backed refs) but BEFORE service insert. 403 with `scope_create_denied` detail if the predicate rejects. v1 supports ColumnCheck / UserAttrCheck / PathCheck depth 1 / BoolComposite; FK-path (depth > 1) and ExistsCheck are rejected at link time (see #1124 for the v2 roadmap). | "the inserted row will 403 at runtime — add a `scope: create:` rule or `scope: all as: <persona>`" | ✅ Enforced since v0.71.22 (simple predicates) |

The `update` / `delete` enforcement landed in v0.71.19 as part of
closing #1123 ("RBAC no_scope_rule lint fires 56× across own
example DSLs"). Pre-v0.71.19, write-op scope rules were
parsed-but-not-enforced — the framework gave the appearance of
expressiveness it didn't deliver. SOC2 CC6.1 / ISO 27001 A.9.4.1
require row-level authorization on write ops in multi-tenant
systems; this release closes that gap for `update` and `delete`.

## How `create` enforcement works

`create` predicates are conceptually different from `read` / `list` /
`update` / `delete`: there's no existing row to filter against —
there's a payload waiting to become a row. v0.71.22 (#1124) ships
enforcement for the simple-predicate subset:

- **What's supported:** `ColumnCheck` (`field op literal`),
  `UserAttrCheck` (`field op current_user[.attr]`), `PathCheck`
  depth 1, `Tautology` / `Contradiction`, and `BoolComposite`
  (`and` / `or` / `not`) over those. This covers ~80% of real-world
  scope-create rules.
- **What's rejected at link time:** `PathCheck` with depth > 1
  (FK-path predicates like `manuscript.school_id = current_user.school`)
  and `ExistsCheck` / `NotExistsCheck` (junction-table predicates
  like `via TeamMembership(...)`). These need a payload-time SQL
  probe that v1 doesn't implement; tracked under #1124 v2.

Predicate evaluation runs AFTER framework defaulting — specifically
after `inject_current_user_refs` (#774) has filled `current_user`
into any missing `ref User` columns. This means
`scope: create: created_by = current_user as: member` evaluates
against the resolved payload, so members can omit `created_by` from
the request body and the framework's auto-injection brings the
predicate to True.

When the v1 supported set isn't enough, express the constraint via:

- **`invariant:` blocks** — predicate-style checks the framework
  evaluates at insert time. Good for "the new row's `X` must equal
  `Y`" rules that don't depend on user context.
- **Service-layer hooks** — register a pre-create hook on the
  service that rejects payloads failing your check. Good for rules
  that need FK-path or junction-table semantics until #1124 v2
  lands.

## Syntax

```dsl
entity Task "Task":
  ...
  permit:
    list: role(admin) or role(manager) or role(member)
    read: role(admin) or role(manager) or role(member)
    create: role(admin) or role(manager) or role(member)
    update: role(admin) or role(manager) or role(member)
    delete: role(admin)

  scope:
    # Row visibility — who sees which rows in list endpoints
    list: assigned_to = current_user or created_by = current_user
      as: member
    list: all
      as: admin, manager

    # Detail visibility — typically mirrors list
    read: assigned_to = current_user or created_by = current_user
      as: member
    read: all
      as: admin, manager

    # Create — declared but not yet enforced (#1124). The framework
    # treats this as documentation-of-intent for now.
    create: all
      as: admin, manager, member

    # Update — enforces at request time. Members can update tasks
    # they created or are assigned to; admins/managers can update any.
    update: assigned_to = current_user or created_by = current_user
      as: member
    update: all
      as: admin, manager

    # Delete — admin-only (mirrors the permit gate; `all` because
    # there's no further row-level restriction once the role-gate passes).
    delete: all
      as: admin
```

## Canonical patterns

### Pattern A — Public read, admin-only writes

The simplest pattern. Use when all permitted users see all rows on
read paths, and writes are restricted to admins by the `permit:`
gate.

```dsl
scope:
  list: all
    as: viewer, admin
  read: all
    as: viewer, admin
  create: all
    as: admin
  update: all
    as: admin
  delete: all
    as: admin
```

Example: `examples/simple_task/`'s `User` entity. Admin-only user
management; everyone else can list/read.

### Pattern B — Per-user ownership

Row creator owns the row. Each user sees and edits only their own;
admin overrides see all. The most common multi-tenant SaaS pattern.

```dsl
scope:
  list: created_by = current_user
    as: member
  list: all
    as: admin
  read: created_by = current_user
    as: member
  read: all
    as: admin
  create: all
    as: member, admin
  update: created_by = current_user
    as: member
  update: all
    as: admin
  delete: all
    as: admin
```

Example: `examples/simple_task/`'s `Task` entity — members own the
tasks they created or are assigned to.

### Pattern C — Per-tenant partition

Multi-tenant SaaS where each user belongs to a tenant (school,
org, workspace) and rows are partitioned by that FK. The scope
predicate compares against `current_user.<attr>` rather than
against the user ID directly.

```dsl
scope:
  list: school_id = current_user.school
    as: teacher
  list: all
    as: super_admin
  read: school_id = current_user.school
    as: teacher
  read: all
    as: super_admin
  create: all
    as: teacher, super_admin
  update: school_id = current_user.school
    as: teacher
  update: all
    as: super_admin
  delete: all
    as: super_admin
```

The `school_id = current_user.school` predicate is the same shape
on all four enforced ops (list/read/update/delete). FK-path
predicates (e.g. `manuscript.assessment_event.school_id =
current_user.school`) are also supported — see ADR-0009.

### Pattern D — Append-only (audit-friendly)

Users can create rows but can't update or delete them. Useful for
audit-trail-style entities.

```dsl
permit:
  list: role(user) or role(admin)
  read: role(user) or role(admin)
  create: role(user) or role(admin)
  update: role(admin)
  delete: role(admin)

scope:
  list: all
    as: user, admin
  read: all
    as: user, admin
  create: all
    as: user, admin
  update: all
    as: admin
  delete: all
    as: admin
```

Members can't update or delete because the `permit:` gate rejects
them. The scope rules document the policy and silence the
`no_scope_rule` lint without needing a per-op carve-out.

## Runtime behaviour

When a request hits an UPDATE or DELETE endpoint, the framework
runs (in order):

1. **Auth** — auth_dep extracts the user and roles from the session.
2. **Permit gate** — `evaluate_permission` checks the role-only
   `permit:` rule. If no rule matches, returns 403.
3. **Scoped pre-read (#1123)** — resolves `scope: <op>:` rules for
   the user's role. If no matching rule, returns 404. If `scope:
   all`, falls through to the unscoped read. Otherwise refetches
   the target row with the scope predicate as part of the SQL
   `WHERE` clause; if no row comes back, returns 404.
4. **Operation** — runs the actual UPDATE/DELETE on the validated row.

The 404 (rather than 403) on scope rejection is deliberate: it
makes scope-denied rows indistinguishable from non-existent rows,
preventing row-existence leaks via IDOR-style probing. Same shape
as the LIST endpoint's default-deny behaviour.

## Default-deny semantics

If an entity has a `scope:` block at all but no rule matches the
caller's (role, operation) pair, the operation defaults to deny
(returns 404 / yields zero rows). This is the design choice from
ADR-0010 — explicit positive grants only.

Specifically:

- If an entity has **no `scope:` block**, all operations pass
  through unfiltered (the `permit:` gate is the only check).
  The framework lint warns about this as `unprotected_entity` for
  entities that do have `permit:` rules — see
  `docs/reference/rbac-verification.md`.
- If an entity has a `scope:` block but **no rule matches the
  current (role, op)** → default-deny.
- If a matching rule has `all as: <persona>` → unrestricted access
  for that persona (no predicate filter applied).
- If a matching rule has a field condition → predicate evaluated
  against the row.

## Migration from pre-ADR-0010 `permissions:` blocks

The pre-ADR-0010 `permissions:` block style enforced field
conditions directly on `permit:` rules — e.g.
`update: owner_id = current_user`. Apps migrated to the new
`permit:` / `scope:` split before v0.71.19 lost write-op
enforcement during the migration without being told (silent
regression). v0.71.19 closes that gap — apps with
`scope: update:` rules will now see them enforce, which may
expose authorization bugs that were silently passing under the
gap.

**Audit checklist for v0.71.19 upgraders:**

1. Run `dazzle lint --format=json | jq '.warnings[] | select(.kind == "no_scope_rule")'`
   on your DSL. Pre-#1123 these warnings used the same misleading
   "will see 0 records" message regardless of op; post-#1123 the
   message is op-specific.
2. For each warning, confirm the rule's intent. If you wanted
   default-deny, add `scope: <op>: all as: <persona>` to make it
   explicit (and silence the lint). If you wanted row-filtering,
   add the predicate.
3. Test write paths against role-restricted users to confirm the
   new 404s match expectations.

## Further reading

- **ADR-0009** — predicate algebra (`docs/adr/0009-predicate-algebra.md`)
- **ADR-0010** — permit/scope separation (`docs/adr/0010-permit-scope-separation.md`)
- **ADR-0010 amendment** for v0.71.19 — write-op scope enforcement
- `docs/reference/access-control.md` — the broader access-control
  reference (permit/scope grammar)
- `docs/reference/rbac-verification.md` — `dazzle rbac matrix` /
  static verification of the access matrix
- `examples/simple_task/`, `examples/support_tickets/`,
  `examples/ops_dashboard/`, `examples/fieldtest_hub/` — every
  framework example demonstrates Pattern A or B with full
  write-op scope rules as of v0.71.19.
