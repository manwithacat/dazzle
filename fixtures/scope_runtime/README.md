# scope_runtime — scope-enforcement runtime fixture

A **framework-validation fixture** (not a user-facing example): a minimal,
auth-enabled app whose only purpose is to exercise the scope-enforcement
runtime against a **real Postgres**, via `tests/integration/test_scope_runtime_pg.py`
(marked `postgres`; runs in CI's `postgres-tests` job, skipped locally without
`TEST_DATABASE_URL`).

## What it probes

- **#1311 — FK-path (depth-2) `scope: create:`** (ADR-0028 trajectory 1). The
  `Enrolment.scope.create` rule `teaching_group.department = current_user.department`
  compiles to a payload-time SQL probe; the test proves it runs correctly
  against real SQL (str→uuid coercion, the `EXISTS (… "id" = %s …)` shape,
  tenant search_path) — not just against a unit-test fake.
- **#1312 — `scope: update:` DESTINATION revalidation** (trajectory 2).
  Repointing an in-scope enrolment's `teaching_group` into a foreign
  department must 404 (the would-be-final row fails scope).
- **#1313 (slice 1b, pending)** — a guarded `atomic` reassign flow will be
  added here once per-step in-transaction scope enforcement lands.

## Domain

`Department` ← `User.department` (drives `current_user.department`, resolved by
email-match like invoice_ops' `current_user.tenant_id`); `TeachingGroup`
belongs to a `Department`; `Enrolment` references a `TeachingGroup` — so a
teacher's authority over an enrolment is the **multi-hop** FK path
`Enrolment → TeachingGroup → Department` compared to the teacher's department.

Personas: `teacher` (department-scoped) and `admin` (unscoped).
