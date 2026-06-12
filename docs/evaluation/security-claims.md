# Dazzle — Security & Compliance Claims Inventory

<!-- MkDocs copy adapted from ../../SECURITY_CLAIMS.md; update both files together. -->

*Last reviewed against v0.82.35 (2026-06-12).*

This document inventories every security-relevant claim Dazzle makes, with its
implementation status, where it is enforced, where it is tested, and its known
gaps. It exists so a skeptical evaluator can separate **implemented
guarantees** from **useful scaffolding** from **roadmap** without reading the
source.

**Honesty principle.** A claim is only listed as `Implemented` if there is code
that enforces it *and* an automated test that exercises it. Where a capability
is partial, the partiality is stated. If something here drifts from the code,
the code wins — file an issue.

> This is a companion to [`evaluation.md`](evaluation.md) (the hands-on
> walkthrough) and the reference docs under [`../reference/index.md`](../reference/index.md).
> The maturity ratings below are evidence-based assessments, not marketing
> grades; they are open to maintainer revision.

---

## Maturity rubric

| Rating | Criteria |
|--------|----------|
| **Stable** | Public API/behaviour is settled. Comprehensive automated tests. Exercised by example apps **and** gated in CI. No known correctness gaps. A breaking change would go through deprecation. |
| **Beta** | Works end-to-end and is tested, but the API may still shift, or there are *known, documented* edge-case gaps (listed below). Safe to build on with awareness of those gaps. |
| **Alpha** | Functional but incomplete: thin test coverage, known significant gaps, or design still in flux. Expect change. |

A rating reflects the *evidence available today*, not ambition. "Beta" here
often means "correct and tested, but young or recently hardened" — several RBAC
subsystems are Beta purely because security-relevant fixes landed within the
last few releases (see the gap columns).

---

## Subsystem maturity (security-relevant)

| Subsystem | Maturity | Basis |
|-----------|----------|-------|
| DSL parser + IR | **Stable** | Largest test surface in the repo; API-surface drift gates; every construct exercised by 14 example apps and CI. |
| RBAC static matrix | **Stable** | `generate_access_matrix` is well-tested; CI has a dedicated security gate asserting the `shapes_validation` matrix has zero unprotected cells. |
| Scope predicate algebra | **Beta** | Formal 6-type predicate algebra, statically validated against the FK graph at `dazzle validate` time. Core is solid; parser-surface edge cases were still being fixed as recently as v0.71.96 (#1180). |
| Runtime RBAC enforcement | **Beta** | Enforced on every generated CRUD route and tested — but the enforcement surface has had security fixes land recently (bulk endpoints, FK errors, scope-deny auditing). |
| Dynamic RBAC verifier | **Beta** | A real verifier (boots the app, probes every role) shipped in v0.71.91 (#1171), replacing an earlier stub. Functional and tested, but only weeks old and requires a live PostgreSQL server. |
| RBAC audit trail | **Beta** | The production `AuditLogger` writes every CRUD decision to PostgreSQL. Recently hardened (fail-closed mode #1172; scope-denied writes captured since #1179). |
| Compliance evidence mapping | **Beta** | Maps DSL constructs to ISO 27001 / SOC 2 controls and flags coverage gaps. Does exactly what the (reframed) docs claim; the `partial` status is reserved but unimplemented. |
| Session CSRF protection | **Beta** | Session-bound token + Origin gate with auth-class-derived disposition (ADR-0033). Shipped v0.81.15–18; young but tested. |
| Enterprise SSO/SCIM (opt-in) | **Beta** | OIDC/SAML/SCIM behind a `[capabilities]` opt-in registry; a greenfield app exposes none. Each piece is tested, but the cluster (#1342) is still in active development. |
| Membership-fenced tenancy | **Beta** | Global Identity + Org + fenced Membership; PostgreSQL RLS keyed on a membership-derived `tenant_id`, proven against real PG as a non-superuser. Phases A+E shipped; generated RLS (B–D) is roadmap. |

---

## Claims inventory

Status legend: **Implemented** (code + tests exist) · **Partial** (works within
stated limits) · **Roadmap** (not yet built).

### RBAC — access control

#### C1 · Every (role, entity, operation) triple has a statically-determined access decision
- **Status:** Implemented · **Maturity:** Stable
- **What it means:** Without running the app, Dazzle resolves each cell of the
  role × entity × operation grid to one of `PERMIT`, `PERMIT_SCOPED`,
  `PERMIT_NO_SCOPE`, `PERMIT_FILTERED`, `PERMIT_UNPROTECTED`, or `DENY`, using
  Cedar semantics (forbid > permit > default-deny).
- **Enforced where:** `src/dazzle/rbac/matrix.py` (`generate_access_matrix`).
  Surfaced by `dazzle rbac matrix`.
- **Tested where:** `tests/unit/test_rbac_matrix.py`; CI step *"Validate Shapes
  RBAC matrix (security gate)"* in `.github/workflows/ci.yml` asserts the
  `shapes_validation` fixture produces zero unprotected cells.
- **Known gaps:** An entity with **no** access rules resolves to
  `PERMIT_UNPROTECTED` (open access) — this is backward-compatible behaviour,
  emitted as a warning, **not** an error. A matrix with unprotected cells is a
  finding to act on, not a failure Dazzle blocks on.

#### C2 · Access rules compile to a formal predicate algebra, validated against the schema
- **Status:** Implemented · **Maturity:** Beta
- **What it means:** `scope:` rules are not opaque strings — they compile to a
  6-form predicate algebra (direct equality, FK-path, EXISTS/NOT-EXISTS
  junction, negation, boolean AND/OR) and are statically checked against the
  foreign-key graph at `dazzle validate` time. A scope rule that references a
  non-existent FK path fails validation.
- **Enforced where:** `src/dazzle/core/dsl_parser_impl/conditions.py` and the
  predicate compiler; validated during `dazzle validate`.
- **Tested where:** `tests/unit/test_predicate_algebra.py`,
  `test_validate_scope_predicates.py`, `test_scope_via.py`.
- **Known gaps:** The predicate *parser* surface is still maturing — composing
  `not (...)` as an operand of `and`/`or` was only fixed in v0.71.96 (#1180).
  The algebra itself is sound; new syntactic forms occasionally surface gaps.

#### C3 · Row-level scope filters are enforced at runtime on every CRUD route
- **Status:** Implemented · **Maturity:** Beta
- **What it means:** For `list`/`read`/`update`/`delete`/`create`, the
  generated route applies the role's `scope:` predicate as a SQL filter (or a
  pre-read for single-id ops). A row outside the caller's scope yields 404 on a
  single-id op — row existence stays opaque.
- **Enforced where:** `src/dazzle/back/runtime/audit_wrap.py`
  (`_build_cedar_handler`) and `scope_filters.py` (`_scoped_pre_read`),
  assembled by `route_generator.py` — the #1361 god-file split extracted
  these handler/filter clusters out of `route_generator.py`.
- **Tested where:** `tests/unit/test_row_level_access.py`,
  `test_scoped_pre_read.py`, `tests/integration/test_acme_billing_rbac.py`.
- **Known gaps:** This surface has had security fixes land recently — bulk-action
  endpoints bypassed permit/scope until #1170; scope-denied UPDATE/DELETE left
  no audit record until #1179 (v0.71.94). Treat the enforcement path as
  correct-but-young; review the CHANGELOG `Security`/`Fixed` entries.

#### C4 · The running app can be probed as every role and compared to the static matrix
- **Status:** Implemented · **Maturity:** Beta
- **What it means:** `dazzle rbac verify` boots the app in-process against a
  disposable PostgreSQL database, seeds one user per role, issues a real HTTP
  request for every (role, entity, operation) cell, and reports
  `PASS`/`VIOLATION`/`WARNING` by comparing the observed HTTP status against the
  static matrix's expected decision.
- **Enforced where:** `src/dazzle/rbac/verifier.py` (`verify`),
  `verification_harness.py`.
- **Tested where:** `tests/unit/test_rbac_verifier.py`,
  `test_rbac_verifier_probe.py`, `tests/integration/test_rbac_verifier_e2e.py`.
- **Known gaps:** Requires a live PostgreSQL server (`DATABASE_URL`). Shipped in
  v0.71.91 (#1171) replacing an earlier stub — it is genuinely new. "Verify"
  means *observed HTTP behaviour matches the declared matrix*; it is an
  empirical probe, **not** a formal proof of the enforcement code.

#### C5 · Every CRUD access decision is written to a durable audit trail
- **Status:** Implemented · **Maturity:** Beta
- **What it means:** The runtime `AuditLogger` records each access decision
  (allow and deny, with matched policy, user, evaluation time) to the
  `_dazzle_audit_log` PostgreSQL table for entities under `audit:`/`audit_trail`.
- **Enforced where:** `src/dazzle/back/runtime/audit_log.py`; route hooks in
  `route_generator.py`.
- **Tested where:** `tests/unit/test_audit_log.py`, `test_rbac_audit.py`,
  `test_rbac_audit_integration.py`.
- **Known gaps:** Recently hardened — a fail-closed production mode was added in
  #1172, and scope-denied UPDATE/DELETE were not captured until #1179. The
  `dazzle.rbac.audit` *sink* (`NullAuditSink` by default) is a separate
  verification-layer seam, **not** the production trail — don't confuse the two.

### Authentication & tenancy

#### C7 · Session mutations are gated by auth-class-derived CSRF protection
- **Status:** Implemented · **Maturity:** Beta
- **What it means:** State-changing requests are protected by a session-bound
  CSRF token plus an Origin/Referer gate, with the disposition (enforce, exempt,
  report) derived from each route's auth class rather than hand-wired per route.
  The resulting policy is auditable.
- **Enforced where:** `src/dazzle/back/runtime/csrf.py`; design recorded in
  ADR-0033 (CSRF as an auth-class disposition).
- **Tested where:** `tests/unit/test_csrf_disposition_phase3.py`,
  `test_csrf_origin_gate_phase2.py`, `test_csrf_exempt_paths.py`,
  `test_csrf_middleware_defers_to_route_cookie.py`.
- **Known gaps:** Shipped across v0.81.15–18; ADR-0033 §Deferred lists hardening
  deliberately not built (hx-headers transport switch, a DSL escape hatch). The
  disposition surface is young — treat it as correct-but-recent.

#### C8 · Enterprise SSO/SCIM is available only behind an explicit opt-in capability
- **Status:** Implemented · **Maturity:** Beta
- **What it means:** OIDC/SAML login and SCIM user/group provisioning are gated
  behind a `[capabilities]` opt-in registry — a greenfield app exposes none of
  these routes. SAML supports IdP-metadata import, SP-signed AuthnRequests,
  encrypted assertions, and Single-Logout; SCIM supports the /Users, /Groups,
  /ResourceTypes, and /Schemas endpoints.
- **Enforced where:** `src/dazzle/back/runtime/auth/saml_provider.py`,
  `saml_routes.py`, `scim_provisioning.py`, `scim_routes.py`; opt-in gate in
  `auth/capability_guard.py`.
- **Tested where:** `tests/integration/test_saml_routes.py`,
  `test_scim_routes.py`; `tests/unit/test_saml_provider.py`,
  `test_saml_metadata.py`, `test_saml_logout.py`.
- **Known gaps:** The enterprise-auth cluster (#1342) is **still in active
  development** — SP-initiated SLO and a boot guard (#1344) remain. Rated Beta:
  each piece is code + tested, but the surface is young and the issue is open.

#### C9 · Tenant rows are fenced by membership-derived row-level security
- **Status:** Partial · **Maturity:** Beta
- **What it means:** Identity is modelled as a global Identity + Org + fenced
  Membership, with the active membership binding the request's `tenant_id`.
  PostgreSQL row-level security keyed on that discriminator fences tenant rows;
  fencing has been proven against a real database as a non-superuser.
- **Enforced where:** `src/dazzle/back/runtime/auth/` (membership +
  `current.py`); RLS binding derived from the active membership. The QA-auth
  containment invariant is recorded in ADR-0035.
- **Tested where:** `tests/integration/test_membership_rls_activation_pg.py`,
  `test_auth_orgprovision_pg.py`; `tests/unit/test_bind_rls_from_membership.py`,
  `test_auth_membership_model.py`.
- **Known gaps:** RLS Phases A (discriminator substrate) and E (tenant
  lifecycle) have shipped; generating RLS from the scope algebra (Phases B–D) is
  roadmap. `Partial`: the substrate and activation path are real and tested, but
  full per-entity RLS generation is not yet wired across the example fleet.

### Compliance

#### C6 · DSL constructs are mapped to ISO 27001 / SOC 2 controls with per-control status
- **Status:** Partial (by design) · **Maturity:** Beta
- **What it means:** `dazzle compliance compile` parses the DSL, extracts
  evidence items (from `permit`, `scope`, `classify`, `transitions`, `process`,
  `persona`, `grant_schema`, and ~6 other constructs), and matches them against
  a hand-authored control→construct mapping table. Each control is reported
  `evidenced`, `gap`, or `excluded`, written as an `AuditSpec` JSON artifact.
- **Enforced where:** `src/dazzle/compliance/` (taxonomy YAML +
  `compiler.py` + `evidence.py`).
- **Tested where:** `tests/unit/test_compliance_*.py` (~100 tests across 9
  files).
- **Known gaps / non-claims:**
  - The frameworks are the **full** control lists (ISO 27001:2022 Annex A — 93
    controls; SOC 2 TSC — 63 controls), but only the controls with a DSL
    evidence mapping are assessable: ~37 of 93 for ISO, ~54 of 63 for SOC 2.
    The rest are always `excluded` (organisational, physical, HR controls a DSL
    cannot evidence).
  - The `partial` status is defined in the model but **never assigned** by the
    compiler — it is reserved/unimplemented.
  - **This does not make an app compliant.** `evidenced` means the
    specification *contains constructs that correspond to* a control objective.
    It does not verify the control is operationally satisfied, appropriate for
    your risk profile, or correctly deployed. As `docs/reference/compliance.md`
    puts it: *"The AuditSpec is evidence that your design intent is documented
    in machine-readable form. It is a starting point for an auditor
    conversation, not a substitute for one."*

---

## Explicit non-claims

Things Dazzle is sometimes assumed to do, and does **not**:

- **It does not make an application compliant.** It maps design intent to
  control objectives and flags coverage gaps. Operational compliance — that the
  controls are appropriate, deployed, and followed — is a human/auditor
  judgment.
- **The verifier does not formally prove the enforcement code correct.** It
  empirically probes the running app's HTTP behaviour against the declared
  matrix. It catches divergence; it is not a proof.
- **No infrastructure, cloud-configuration, or deployment-posture assessment.**
  The compliance pipeline reasons about the DSL specification only.
- **`PERMIT_UNPROTECTED` entities are open.** An entity with no access rules is
  world-accessible by design (backward compatibility). The matrix flags it as a
  warning; it is the operator's job to act on it.
- **Audit completeness depends on configuration.** Only entities under an
  `audit:`/`audit_trail` declaration are written to the durable trail.

---

## How to verify these claims yourself

See [`evaluation.md`](evaluation.md) for a ~30-minute hands-on walkthrough with
copy-pasteable commands and expected output. The short version:

```bash
dazzle rbac matrix --format table     # C1 — the static decision grid
dazzle validate                       # C2 — scope predicates checked vs FK graph
dazzle rbac verify                    # C3/C4 — probe the running app (needs PostgreSQL)
dazzle compliance compile --framework soc2   # C6 — control evidence mapping
```
