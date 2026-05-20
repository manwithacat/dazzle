# `examples/acme_billing` — Canonical Adversarial RBAC Example — Design (#1174)

**Date:** 2026-05-21
**Issue:** #1174 — "canonical adversarial RBAC walkthrough example app"
**Status:** Approved — ready for implementation planning

## Problem

An evaluator cannot, today, run one command and see Dazzle's RBAC model,
its generated routes, runtime enforcement, and adversarial pass/fail
tests in one place. `fixtures/shapes_validation` and
`fixtures/rbac_validation` are abstract policy-engine probes — their
READMEs explicitly forbid UI/workflows. They are also **role-gate-heavy
and row-scope-light**: `rbac_validation` uses `permit:`/`forbid:` role
rules and `scope: list: all` almost exclusively. It exercises Cedar
permit/forbid thoroughly but barely touches *row-level* scope — which is
exactly where IDOR and cross-tenant bugs live (cf. #1170).

## Goal

A "boring", inspectable, multi-tenant example app — `examples/acme_billing`
— that:
- exercises **every form** of the scope predicate algebra,
- ships realistic seed data spanning multiple tenants,
- carries an **adversarial test suite** that actively tries to break the
  RBAC guarantees, gating CI,
- and has a README that walks an evaluator through inspecting the model
  and running the tests with copy-pasteable commands.

It is the home the #1173 adversarial tests "ideally" belong in, and a
realistic target app for the #1171 dynamic verifier.

## Decisions (from brainstorming)

1. **Deliverable** — hand-author the DSL, adversarial pytest suite,
   seed data, and README; **also commit reference outputs** (static RBAC
   matrix, compliance report) guarded by a drift test so they cannot go
   stale silently.
2. **Test expression** — `story` DSL blocks in the app for the
   expected-behaviour narrative; the adversarial verification is
   imperative **pytest in the framework suite** (`tests/integration/`),
   so it gates CI. Adversarial cases need HTTP-level control (status
   codes, IDOR id-probing, bulk payloads) the DSL `test` construct
   cannot express.

## Domain model

Five entities, multi-tenant. `Organization` is the tenant root.

| Entity | Key fields | Notes |
|---|---|---|
| `Organization` | `id`, `name` | Tenant root |
| `User` | `id`, `email`, `name`, `org: ref Organization` | Domain user record (distinct from the framework auth user) |
| `Project` | `id`, `name`, `org: ref Organization` | Belongs to an org |
| `Invoice` | `id`, `number`, `amount`, `project: ref Project`, `sensitive: bool=false` | Org reachable via `project.org` |
| `Membership` | `id`, `user: ref User`, `project: ref Project` | Junction — which users are assigned to which projects |

**Roles / personas:** `admin`, `org_owner`, `auditor`, `project_member`,
`external_contractor`.

## Scope rules — full predicate-algebra coverage

The point of the app is that its `scope:` rules exercise **every form**
of the predicate algebra (CLAUDE.md "Scope rules"):

| Form | Entity | Rule (illustrative) |
|---|---|---|
| Direct equality | `Organization` | `scope: read: id = current_user.org  as: org_owner, auditor` |
| FK-path (depth-2) | `Invoice` | `scope: list: project.org = current_user.org  as: org_owner, auditor` |
| EXISTS via junction | `Project` | `scope: list: via Membership(user = current_user, project = id)  as: project_member` |
| Negation | `Invoice` | `scope: read: not (sensitive = true)  as: project_member, external_contractor` |
| Unrestricted | all | `scope: <op>: all  as: admin` |

**`auditor` is read-only** — `permit:` grants only `read`/`list`; no
`create`/`update`/`delete` permit rule exists for it (default-deny).

**"Forbid sensitive invoices" is a `scope:` rule, not `forbid:`.** ADR-0010
forbids field conditions in `permit:`/`forbid:`. The requirement "external
contractors and project members cannot see sensitive invoices" is
therefore expressed as `scope: read: not (sensitive = true) as: …` — they
see only non-sensitive rows. This is correct *and* exercises the negation
predicate form.

Each `scope:` rule has a matching `permit:` rule and an `as:` clause, per
the grammar.

## Surfaces

`acme_billing` is a real `examples/` app (not an abstract `fixtures/`
probe), so it has surfaces: a list + view surface per entity and a
workspace landing page. Kept modest — the surfaces exist to make the app
inspectable and runnable, not to showcase UI. Field projections are
plain; no charts/regions.

## Seed data

Two organizations — **Acme** and **Globex** — each with:
- users across every role (`admin` is global; `org_owner`, `auditor`,
  `project_member`, `external_contractor` per org),
- 2–3 projects,
- several invoices, **some flagged `sensitive`**,
- memberships assigning `project_member` users to a subset of projects.

The cross-tenant data on *both* sides is what lets the adversarial tests
prove isolation (an Acme user must not see Globex rows, and vice versa).

## Adversarial test suite

`tests/integration/test_acme_billing_rbac.py` — `postgres` + `e2e`
marked, runs in CI. Each test exercises an *attack/failure* path:

1. **IDOR** — an Acme `org_owner` fetches a Globex invoice by id → `404`.
2. **Cross-tenant list isolation** — an Acme `org_owner` lists invoices →
   only Acme invoices returned.
3. **Sensitive-invoice denial** — `external_contractor` / `project_member`
   reading a `sensitive` invoice → denied (filtered / `404`).
4. **Bulk-endpoint bypass** — a bulk action on invoices as a
   non-permitted role → denied (the #1170 regression, pinned here).
5. **Auditor is read-only** — `auditor` attempts create/update/delete →
   `403`.
6. **Project scoping** — a `project_member` lists projects → only
   projects they have a `Membership` for, not all org projects.
7. **Admin baseline** — `admin` has full cross-org access (positive
   control, so the suite isn't all-negative).
8. **Audit emission** — a denied access produces an audit record
   (asserts runtime audit, rather than committing a stale audit dump).

The app also carries `story` DSL blocks (`dsl/stories.dsl`) narrating the
expected behaviour per persona — readable documentation, mirroring
`rbac_validation/dsl/stories.dsl`.

## Committed reference outputs + drift gate

`examples/acme_billing/expected/` holds committed reference artifacts:
- `rbac-matrix.json` — output of `dazzle rbac matrix --format json`.
- `compliance-report.md` — output of `dazzle compliance report`.

`tests/unit/test_acme_billing_reference_drift.py` regenerates each via the
CLI and diffs against the committed copy — the same self-maintaining
pattern as `tests/unit/test_api_surface_drift.py`. A framework change
that alters the matrix or compliance output fails this test, forcing the
committed reference (and a CHANGELOG note) to be updated deliberately.

**Audit output is deliberately NOT a committed file.** Audit records are
runtime artifacts (`_dazzle_audit_log`); a committed dump would rot
immediately. Test 8 above asserts audit emission instead.

## File layout

```
examples/acme_billing/
  dazzle.toml
  README.md                  walkthrough + expected command output
  dsl/
    app.dsl                  module + app declaration
    entities.dsl             5 entities, permit/scope/forbid/audit
    personas.dsl             5 personas
    stories.dsl              expected-behaviour narrative
    surfaces.dsl             list/view surfaces + workspace
  seed/                      seed data (demo_data DSL or seed fixtures)
  expected/
    rbac-matrix.json         committed reference (drift-gated)
    compliance-report.md     committed reference (drift-gated)

tests/integration/test_acme_billing_rbac.py     adversarial suite (postgres+e2e)
tests/unit/test_acme_billing_reference_drift.py  reference drift gate
```

The app follows the structure of existing `examples/` apps
(`dazzle.toml` + `dsl/*.dsl` + `README.md`).

## Error / edge handling

- The app must pass `dazzle validate` and `dazzle lint` cleanly — it is
  picked up by the CI `e2e-smoke` job's "validate all examples" loop, so
  a broken DSL fails CI immediately.
- It must satisfy the framework artefact-coverage gate
  (`dazzle coverage --fail-on-uncovered`) — every construct it uses
  already has coverage; it introduces no new DisplayMode/construct.
- Adversarial tests must seed their own auth users/sessions per role
  (mirroring `cli/rbac.py:_login` + the seeding approach from the #1171
  verifier plan) — they cannot assume ambient demo users.

## Testing

- **DSL validity** — `dazzle validate examples/acme_billing` (CI e2e-smoke).
- **Adversarial behaviour** — `tests/integration/test_acme_billing_rbac.py`
  (CI `e2e-runtime` / postgres).
- **Reference drift** — `tests/unit/test_acme_billing_reference_drift.py`
  (CI unit).

## Out of scope

- Per-row IDOR for *every* entity pair — the suite covers the
  Invoice/Organization cross-tenant axis thoroughly; exhaustive
  entity-pair permutations are unnecessary.
- Rich UI / charts / workspace regions — surfaces are deliberately plain.
- Replacing `fixtures/rbac_validation` — that stays as the abstract
  policy-engine probe; `acme_billing` complements it as the realistic,
  row-level-scope, user-facing example.
- A `trial.toml` / qualitative trial scenario — can be added later via
  the `qa-trial` skill if desired.

## Relationship to other issues

- **#1173** — the adversarial RBAC tests this app carries are the home
  the #1173 issue anticipated; #1173's deferred app-level cases
  (custom-route priv-esc, etc.) can land here.
- **#1171** — `acme_billing` is a realistic target app for the dynamic
  RBAC verifier, alongside `fixtures/rbac_validation`.
- **#1170** — adversarial test 4 (bulk-endpoint bypass) pins that fix
  against regression in a realistic multi-tenant app.
