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
| `update` | Pre-write, **two-sided** (#1312, ADR-0028): (1) **source** — folded into the WHERE of the permit-gate pre-read; if it rejects the target row the request 404s before the update SQL runs. (2) **destination** — the row's would-be-final state (`existing ⊕ changed fields`) is re-validated against the same `scope: update:` rule before the write, so an update can't repoint an FK to move an in-scope row INTO a foreign scope. Destination denial is a 404 (indistinguishable from a missing row). | "the request will 404 at runtime — add a `scope: update:` rule or `scope: all as: <persona>`" | ✅ Source since v0.71.19; destination since #1312 |
| `delete` | Same as `update`. | Same as `update`. | ✅ Enforced since v0.71.19 |
| `create` | Pre-write — predicate is evaluated against the payload AFTER framework defaulting (`current_user` injection, persona-backed refs) but BEFORE service insert. 403 with `scope_create_denied` detail if the predicate rejects. Simple leaves (ColumnCheck / UserAttrCheck / PathCheck depth 1 / BoolComposite) evaluate in-Python against the payload; FK-path (depth > 1) and ExistsCheck/NotExistsCheck resolve via a payload-time SQL probe (#1311, ADR-0028). | "the inserted row will 403 at runtime — add a `scope: create:` rule or `scope: all as: <persona>`" | ✅ Enforced since v0.71.22 (simple) / #1311 (FK-path + EXISTS) |

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
there's a payload waiting to become a row. Enforcement is a **hybrid**
walker (#1124 v0.71.22 for the simple subset; #1311 / ADR-0028 for
FK-path + EXISTS):

- **Evaluated in-Python against the payload (no DB roundtrip):**
  `ColumnCheck` (`field op literal`), `UserAttrCheck`
  (`field op current_user[.attr]`), `PathCheck` depth 1,
  `Tautology` / `Contradiction`, and `BoolComposite`
  (`and` / `or` / `not`) over those.
- **Resolved via a payload-time SQL probe (#1311):** `PathCheck` with
  depth > 1 (FK-path predicates like
  `teaching_group.department = current_user.department`) and
  `ExistsCheck` / `NotExistsCheck` (junction-table predicates like
  `via TeamMembership(user = current_user, team = team)`). The probe
  resolves the FK chain / junction membership against the DB *using
  the payload's FK value* — `%s IN (SELECT … WHERE …)` /
  `EXISTS (SELECT 1 FROM junction WHERE …)` — BEFORE the insert,
  fail-closed. This keeps the boundary **in the predicate algebra**
  (ADR-0009): statically validated, RBAC-matrix-visible, and
  conformance-checked, rather than buried in handler code. FK paths
  are bounded (≤ 4 hops); a deeper path is rejected at link time.

Predicate evaluation runs AFTER framework defaulting — specifically
after `inject_current_user_refs` (#774) has filled `current_user`
into any missing `ref User` columns. This means
`scope: create: created_by = current_user as: member` evaluates
against the resolved payload, so members can omit `created_by` from
the request body and the framework's auto-injection brings the
predicate to True.

> **Do NOT denormalize a scope key onto the entity to "simplify" a
> create boundary** (e.g. copying `department` onto a row to write
> `scope: create: department = current_user.department` instead of the
> FK-path form). A client-settable denormalized column is
> **spoofable** — a depth-1 ColumnCheck reads the payload value
> verbatim and never re-derives it from the source FK, so a caller
> sends `department=mine` with a foreign `teaching_group` and the row
> lands in the wrong scope. Express the real boundary as the FK-path
> predicate (`scope: create: teaching_group.department =
> current_user.department`) — the #1311 probe derives the destination's
> department from the FK against the DB, closing the spoof. When the
> operation is a multi-step "move" that touches a source *and* a
> destination, follow the **guarded transactional action** pattern and
> its normative rules (derive scope keys from the authenticated
> principal; validate every touched entity; one transaction; fail
> closed). See
> [ADR-0028](../adr/0028-guarded-transactional-actions.md).

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

    # Create — enforced at request time (#1124 simple shapes; #1311
    # FK-path + EXISTS via payload-time probe). `all` = unrestricted
    # create for these personas.
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

## `current_tenant` — host-tenant row scoping (#1394)

In a `tenant_host:` app (#1289), `current_tenant` binds the **host-resolved
tenant** — the tenant the request's `<slug>.host` Host header resolved to
(`request.state.tenant`). Use it to scope rows to the tenant whose host the
user is on:

```dsl
scope:
  list: org = current_tenant
    as: member
  read: org = current_tenant
    as: member
  create: org = current_tenant
    as: member
```

Key properties:

- **Id-only in scope.** `field = current_tenant` (and the explicit
  `field = current_tenant.id`) bind the tenant **id**. Tenant *attributes*
  (`current_tenant.slug` / `.kind` / `.name`) are **display-gate only** (see
  below) — not valid in a `scope:` predicate.
- **Distinct from the RLS row-tenancy `dazzle.tenant_id`.** `current_tenant`
  binds the *host* tenant via its own `dazzle.host_tenant_id` GUC. The two can
  diverge; `current_tenant` never reads the RLS discriminator.
- **Fails closed.** A request with no host tenant (apex host / non-tenant
  request) denies every `current_tenant` predicate — list/read return no rows,
  create/update are refused. Enforced in both the param-mode filter and the
  RLS policy body.
- **Requires `tenant_host:`.** Apps using the legacy schema-isolation
  middleware don't bind the host tenant context, so `current_tenant` predicates
  there deny — use `current_user.<org_attr>` instead.

### Display gating with `current_tenant.<attr>`

In `visible_when:` / `when:` conditions, `current_tenant.id|slug|kind|name`
resolves at render time from the host tenant — e.g. show a region only on a
trust-kind host:

```dsl
region trust_rollup:
  visible_when: current_tenant.kind == trust
```

Display gating is **cosmetic** — it hides UI, it does not filter rows. Always
back a `current_tenant` display gate with a matching `scope:` rule for the
actual access control. The display gate is bound to the same host-tenant
source as scope, so it hides exactly when the scope predicate would deny.

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

### Pattern E — Relationship through a junction (`via`)

When visibility depends on a *many-to-many* relationship rather than
a column the entity carries directly, scope through a junction entity
with `via`. This compiles to an `EXISTS`/`IN` subquery against the
junction (`ExistsCheck` in the algebra — ADR-0009):

```dsl
scope:
  # A rater sees a row only if a UserRole junction links them to it.
  read: via UserRole(user = current_user, role.code = co_rater)
    as: rater
  # Exclusion: hide rows the caller has explicitly blocked.
  list: not via BlockList(user = current_user, resource = id)
    as: member
```

`via JunctionEntity(junction_col = current_user[.attr], junction_col = id)`
compiles to
`WHERE id IN (SELECT junction_col FROM JunctionEntity WHERE junction_col = $current_user)`;
`not via …` compiles to `NOT EXISTS`. Every binding names its column
explicitly, and each is validated against the FK graph at
`dazzle validate` time.

#### `via` is a **single junction hop** (#1306)

`via` expresses exactly **one** junction. It scopes an entity that has
a *direct* link to the scoping pivot (or to a junction that carries
`current_user`). An entity that reaches the pivot only **through an
intermediate entity** — a two-junction path — **cannot** be `via`-scoped,
because no single junction's binding reaches `current_user` in one hop.

Concrete case (a parent portal scoping `AssessmentEvent` to "my child's
assessments"): `AssessmentEvent` is class-level (school, teaching_group,
…) and has no `student` field. The child link runs
`AssessmentEvent ← Manuscript.student_profile → ParentContact.parent_user`
— two junctions:

```
AssessmentEvent.id IN (
  SELECT assessment_event FROM Manuscript
  WHERE student_profile IN (
    SELECT student FROM ParentContact WHERE parent_user = $current_user))
```

There is no `via` form for this. (Extending the algebra to a chained
two-junction `via` was considered and **declined** in #1306: it would
mean standing up a second multi-hop predicate path with its own
fail-closed and validate-time-reject hardening, for marginal
expressivity over the workaround below. The algebra stays closed — per
ADR-0009, novel rule forms require an explicit, deliberate extension.)

**Supported pattern — denormalize the link.** Add the pivot reference
to the entity as a real FK and scope on that *single* hop, which the
hardened single-junction / FK-path machinery already handles
(determinism and fail-closed are inherited):

```dsl
entity AssessmentEvent "Assessment Event":
  ...
  # Denormalized child link, maintained when a Manuscript is created.
  student_profile: ref StudentProfile optional

scope:
  read: via ParentContact(student = student_profile, parent_user = current_user)
    as: parent
```

**Anti-pattern — do NOT fall back to an over-broad `filter:`.** Replacing
the unexpressible `via` with `filter: school = current_user.school`
silently widens the row set to the **whole tenant** (the parent sees the
entire school's events, not their child's). That is a confidentiality
regression masquerading as a working scope. If you can't express the
intended scope with a single hop, denormalize — don't widen.

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
   `WHERE` clause; if no row comes back, returns 404. This validates
   the **source** row — the row as it exists *before* the update.
4. **Destination re-validation — UPDATE only (#1312, ADR-0028)** —
   after schema validation and before the write, the row's
   would-be-final state (the scope-validated `existing` row with the
   request's changed fields overlaid) is re-checked against the same
   `scope: update:` rule. This closes the gap where an in-scope row
   could be moved *into* a foreign scope by repointing an FK the
   pre-read never re-examined. FK-path / EXISTS destination guards
   resolve via the same payload-time probe as create-scope (#1311);
   denial is a 404. A `scope: update: all` rule or an update that
   doesn't touch any scope-key column is a no-op here.
5. **Operation** — runs the actual UPDATE/DELETE on the validated row.

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

## Route overrides — opting back into framework enforcement (#1126)

Project route overrides (`# dazzle:route-override` files under your
project's `routes/` directory) are arbitrary code: they bypass the
framework's permit/scope machinery by default. v0.71.24 adds two ways
to opt back in.

### Declarative — `# dazzle:implements`

Add a companion header to the route-override declaration:

```python
# dazzle:route-override POST /api/cohort-assessment/{assessment_id}/delete
# dazzle:implements CohortAssessment.delete via assessment_id

async def handler(request: Request, assessment_id: str):
    # Framework has already, before dispatch:
    #   1. authenticated the user (401 if not)
    #   2. resolved the row at `assessment_id` (404 if not found)
    #   3. evaluated `permit: delete` against the role (403 if denied)
    #   4. evaluated `scope: delete:` against the row (404 if denied)
    # Handler is authorised by construction.
    ...
```

Semantics: `implements: <Entity>.<op> via <path_param>` tells the
framework which DSL entity + operation this route logically implements
and which path parameter holds the target row's primary key. The
framework wraps the handler so the same permit + scope pipeline runs
that the framework-generated CRUD route would.

Drift-free: when the DSL rule changes, the gate's behaviour changes
automatically. Adopters get the textbook ownership check with zero
hand-rolled SQL.

### Imperative — `check_entity_op`

For overrides that take the ID in the body, write to multiple entities,
or need authorisation after some payload computation:

```python
from dazzle.back.runtime.policy import check_entity_op

async def handler(request: Request):
    body = await request.json()
    # Permit + scope evaluation; raises HTTPException(403/404) on denial.
    row = await check_entity_op(
        request, "StudentProfile", "update", row_id=body["pupil_id"],
    )
    # `row` is the framework-fetched record (no need to re-query).
    ...
```

Same primitive as the declarative form. For `create`, pass `payload`
instead of `row_id` — the framework walks the `scope: create:`
predicate against the post-default payload.

### Failure modes

- **Annotation absent** → handler runs unguarded (legacy behaviour
  preserved for overrides that intentionally take their own
  authorisation, e.g. webhook endpoints with HMAC verification).
- **Permit denies** → 403 before the handler body.
- **Scope denies / row missing** → 404 before the handler body
  (default-deny shape; mirrors LIST handler).
- **Unauthenticated** → 401 (the override use case assumes auth has
  run upstream).
- **Wrapper can't find Request or named path param** → 500 with
  diagnostic detail. Framework-bug-shaped, not user-error-shaped.

### Supported predicate shapes for `scope: create:` enforcement

Same as the framework's own create-route enforcement: ColumnCheck,
UserAttrCheck, PathCheck (any bounded depth), ExistsCheck /
NotExistsCheck, and BoolComposite over those. Depth-1 shapes evaluate
in-Python against the payload; FK-path (depth > 1) and EXISTS shapes
resolve via the same payload-time SQL probe (#1311, ADR-0028) — the
override path (`check_entity_op`) builds the probe from the entity's
registered service, so it enforces identically to the framework
create route.

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
