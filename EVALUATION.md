# Evaluating Dazzle — a skeptical evaluator's guide

<!-- Root GitHub copy. MkDocs-adapted copy lives at docs/evaluation/evaluation.md; update both together. -->

*Last reviewed against v0.82.35 (2026-06-12).*

This guide is for someone deciding whether Dazzle is worth their time. It
assumes you are skeptical, short on time (~30 minutes), and want to see claims
*demonstrated*, not asserted. Every command below is copy-pasteable and the
expected output shape is shown.

It pairs with [`SECURITY_CLAIMS.md`](SECURITY_CLAIMS.md) (the precise
claim-by-claim inventory). Where this guide says "this proves claim C3", that
refers to the claims in that document.

---

## What Dazzle is (one paragraph)

Dazzle is a DSL-first toolkit: you describe an application — entities, roles,
permissions, workflows, state machines — in `.dsl` files, and a runtime
executes that specification directly as a working web app (PostgreSQL + API +
server-rendered UI + auth). There is no code-generation step and no build step.
The same intermediate representation also drives API specs, a static
authorization matrix, a runtime authorization verifier, and a compliance
evidence mapper. The bet: if the specification is the single source of truth,
properties that are normally scattered across hand-written code become
*statically analyzable* and *machine-verifiable*.

---

## The five questions this guide answers

1. Does an app actually run from a spec, with no generated code to maintain?
2. Can I see every authorization decision **without running the app**?
3. Are the declared access rules **actually enforced** at runtime?
4. What does the "compliance" feature really produce?
5. How mature is each part — what should I *not* rely on yet?

---

## Setup (~5 min)

```bash
# From a clone of the repo (uv is the canonical toolchain):
uv sync --extra dev --extra llm --extra mcp
# pip still works:           pip install -e ".[dev,llm,mcp]"
# Or the published package:  pip install dazzle-dsl

cd examples/support_tickets        # a small multi-role app used below
```

`support_tickets` has four roles (`admin`, `customer`, `agent`, `manager`) and
entities including `Ticket`, `Comment`, `User` — enough to make authorization
non-trivial.

---

## Q1 · Does an app run from the spec? (~5 min)

```bash
dazzle validate          # parse + validate the DSL, no server
dazzle serve     # boot the app  →  UI :3000, API docs :8000/docs
```

**Expected:** `dazzle validate` parses every `.dsl` file, resolves the merged
`AppSpec`, and reports errors/warnings (warnings are non-fatal — e.g. widget
hints). `dazzle serve` brings up a working CRUD app with auth. Open
`http://localhost:8000/docs` — the OpenAPI surface is derived from the same
spec.

**What this proves:** the DSL is executed, not scaffolded. There is no
generated source tree to diff or maintain. Change the DSL, restart, done.

---

## Q2 · Every authorization decision, without running the app (~5 min)

```bash
dazzle rbac matrix --format table
```

**Expected output** (abridged, from `support_tickets`):

```
| entity | operation | admin | customer | agent  | manager |
| Ticket | list      | DENY  | PERMIT_SCOPED | PERMIT | PERMIT |
| Ticket | update    | DENY  | DENY          | PERMIT | PERMIT |
| Ticket | delete    | DENY  | DENY          | DENY   | PERMIT |
| User   | list      | PERMIT_UNPROTECTED | ...  (all roles)  |
```

Every (role, entity, operation) cell resolves statically to one of `PERMIT`,
`PERMIT_SCOPED`, `PERMIT_NO_SCOPE`, `PERMIT_FILTERED`, `PERMIT_UNPROTECTED`, or
`DENY`. Use `--format json` for a machine-readable grid.

**Be skeptical here — two things to notice:**
- `PERMIT_UNPROTECTED` (the `User` rows above) means *that entity has no access
  rules and is world-accessible*. Dazzle surfaces this as a warning, not an
  error. A real evaluation should grep the matrix for `PERMIT_UNPROTECTED`.
- `PERMIT_SCOPED` means "permitted, but rows are filtered by a `scope:` rule" —
  the matrix tells you a filter *exists*, Q3 checks it actually *works*.

A measurable property: **static decision coverage** = share of cells that are
not `PERMIT_UNPROTECTED`. On the `shapes_validation` RBAC fixture this is
**100%** (360/360 cells) — and CI enforces it (the *"Validate Shapes RBAC
matrix"* security gate fails the build if any unprotected cell appears).

**What this proves:** claim C1. Authorization is a static artifact you can
diff, review, and gate in CI — not behaviour buried in request handlers.

```bash
dazzle validate          # also statically checks every scope: predicate
```
`scope:` rules compile to a formal predicate algebra and are validated against
the foreign-key graph at validate time — a rule referencing a non-existent FK
path fails here, before the app ever runs (claim C2).

---

## Q3 · Are the rules actually enforced at runtime? (~10 min)

The matrix is a *claim about intent*. The verifier checks the *running app*.

```bash
# Requires a PostgreSQL server. The verifier creates and drops its own
# disposable scratch database — point DATABASE_URL at a server, not an app DB.
export DATABASE_URL=postgres://localhost/postgres
dazzle rbac verify
```

**Expected output** (the exact counts depend on the app — this is the shape,
not measured numbers):

```
RBAC verification: <total> cells | <passed> passed | <violated> violated | <warnings> warnings
Report: .dazzle/rbac-verify-report.json
```

`verify` boots the app in-process, seeds one user per role, issues a real HTTP
request for every matrix cell, and compares the observed HTTP status to the
matrix's expected decision. A `VIOLATION` is a cell where the running app
disagreed with the declared policy (e.g. matrix says `DENY`, app returned 200).
The command exits non-zero if any cell is a violation — so it works as a CI
gate.

Without `DATABASE_URL` set you get an explicit, honest failure rather than a
false pass:

```
RBAC verification failed: dynamic RBAC verification requires a PostgreSQL
server — set DATABASE_URL (the verifier creates and drops its own scratch DB).
```

**What this proves:** claims C3 and C4. Be precise about what "verify" means —
it is an **empirical probe** of observed HTTP behaviour, not a formal proof of
the enforcement code. It catches divergence between declared and actual
behaviour; it does not prove the absence of all bugs. It is also genuinely new
(shipped v0.71.91) — see its maturity rating below.

---

## Q4 · What does "compliance" actually produce? (~5 min)

```bash
dazzle compliance compile --framework soc2
dazzle compliance gaps --framework soc2
```

**Expected output:**

```
Compliance: SOC 2 Type II — Trust Services Criteria
  Controls: 63
  Evidenced: 34
  Partial: 0
  Gaps: 20
  Excluded: 9
  Coverage: 54.0%
  Output: .dazzle/compliance/output/soc2/auditspec.json
```

This walks the DSL, extracts evidence items (from `permit`, `scope`,
`classify`, state-machine `transitions`, `process`, `persona`, and ~7 other
constructs), and matches them against a hand-authored control→construct mapping
for the full ISO 27001:2022 Annex A (93 controls) and SOC 2 TSC (63 controls).

**Read this output carefully — it is deliberately narrow:**
- `Excluded` controls have no DSL mapping at all (organisational, physical, HR
  controls a DSL cannot evidence). ~9 for SOC 2, ~56 for ISO 27001.
- `Partial` is always `0` — the status is reserved in the data model but the
  compiler never assigns it. It is unimplemented, not a real result.
- `evidenced` means *the specification contains constructs that correspond to a
  control objective*. It does **not** mean the control is operationally
  satisfied, appropriate for your risk, or correctly deployed.

**What this proves:** claim C6 — and, equally important, its limits. This is
**control-coverage evidence mapping**, a starting point for an auditor
conversation. It is not a compliance certification and does not make an app
compliant. The reference doc `docs/reference/compliance.md` states this plainly.

---

## Q5 · Per-subsystem maturity

Ratings use the rubric in [`SECURITY_CLAIMS.md`](SECURITY_CLAIMS.md#maturity-rubric)
(Stable / Beta / Alpha). They are evidence-based assessments, open to revision.

| Subsystem | Maturity | One-line basis |
|-----------|----------|----------------|
| DSL parser + IR | **Stable** | Largest test surface in the repo; API-surface drift gates; 14 example apps + CI. |
| RBAC static matrix | **Stable** | Well-tested; CI security gate asserts zero unprotected cells on the RBAC fixture. |
| Scope predicate algebra | **Beta** | Formal algebra, FK-graph-validated; parser-surface edge cases fixed as recently as v0.71.96. |
| Runtime RBAC enforcement | **Beta** | Enforced on every CRUD route + tested; security fixes landed within the last few releases. |
| Dynamic RBAC verifier | **Beta** | Real verifier since v0.71.91 (replaced a stub); functional, tested, needs live PostgreSQL. |
| RBAC audit trail | **Beta** | Production `AuditLogger` → PostgreSQL; recently hardened (fail-closed mode, scope-deny capture). |
| Session CSRF protection | **Beta** | Session-bound token + Origin gate, auth-class-derived disposition (ADR-0033); shipped v0.81.15–18, tested. |
| Enterprise SSO/SCIM (opt-in) | **Beta** | OIDC/SAML/SCIM behind a `[capabilities]` opt-in registry; each piece tested, cluster (#1342) still in active development. |
| Membership-fenced tenancy | **Beta** | Membership-derived `tenant_id` + Postgres RLS, proven vs real PG as non-superuser; RLS Phases A+E shipped, B–D roadmap. |
| Compliance evidence mapping | **Beta** | ~100 tests; does what the docs claim; `partial` status unimplemented. |
| Compliance — operational/infra checks | **Roadmap** | Not built. The pipeline reasons about the DSL spec only. |
| MCP server / AI workflows | **Beta** | 30+ tools, all handlers implemented, ~315 tests; handler tests mock heavily, API still growing. |
| LSP server | **Alpha** | All major LSP features implemented (~1.6k lines), but the completion handler lacks direct tests and CI does not run `dazzle lsp` end-to-end. |
| Pitch artifacts | **Beta** | End-to-end DSL→PPTX pipeline, ~99 tests; the DSL-extraction path is thinly tested and no example ships a `pitchspec.yaml`. |

If you are evaluating Dazzle *for security/authorization*, the load-bearing
rows are the RBAC group — and four of those are **Beta**, mostly because
security-relevant fixes landed recently. That is the honest picture: the
architecture is sound and tested, the enforcement surface is still being
hardened release-to-release. Read the `Security`/`Fixed` sections of
`CHANGELOG.md`.

---

## How Dazzle compares to other frameworks

A true head-to-head benchmark is apples-to-oranges: Dazzle *generates and runs
the whole app from a spec*, whereas Django/Rails are frameworks you write code
in and Cedar/OpenFGA are authorization libraries you embed. So the useful
comparison is a **capability matrix** — *can the tool answer these questions at
all?* — not a performance number.

| Capability | Dazzle | Django | Rails + Pundit | Supabase / Postgres RLS | Cedar / OpenFGA |
|------------|:------:|:------:|:--------------:|:-----------------------:|:---------------:|
| Authorization is declarative | Yes (`permit:`/`scope:`) | Partial (model perms) | No (policy = Ruby code) | Yes (SQL RLS) | Yes (policy language) |
| Static decision matrix, no app run | **Yes** | No | No | No | Partial (policy analysis) |
| Row-level scoping built in | Yes (predicate algebra) | No (add-on / manual) | No (manual scopes) | Yes (RLS) | Yes (relationship-based) |
| Runtime verification vs declared policy | **Yes** (`rbac verify`) | No | No | No | No (validation is static) |
| Compliance control mapping | Yes (`compliance`) | No | No | No | No |
| Generates the running app | **Yes** | No (you build it) | No (you build it) | No (DB layer only) | No (library) |

How to read this honestly:
- **Cedar / OpenFGA** are the real peers on *analyzable authorization* — formal,
  declarative policy. But they are libraries: you still build the data layer,
  the routes, and the UI, and they have no notion of probing your running app.
- **Supabase / Postgres RLS** is the real peer on *declarative row scoping*,
  and it is enforced in the database. But there is no cross-table decision
  matrix and no app-level verifier.
- **Django / Rails** give you a full app framework, but authorization is
  imperative code in views/policies — not statically enumerable, and there is
  nothing to verify the app against.

Dazzle's distinctive position is the *combination*: spec→running app **and** a
static authorization matrix **and** a runtime verifier that probes the live app.
No single tool in the comparison does all three. Whether that combination is
worth adopting an opinionated DSL for is the actual decision — this guide only
aims to let you see the combination is real.

### Measurable properties (on Dazzle's own apps)

Where a number *is* meaningful, these are reproducible:

| Metric | Command | Observed |
|--------|---------|----------|
| Static decision coverage | `dazzle rbac matrix --format json` → share of cells not `PERMIT_UNPROTECTED` | 100% (360/360) on `shapes_validation` |
| Runtime verifier pass rate | `dazzle rbac verify` → `passed / total` | run it yourself (needs PostgreSQL) |
| Compliance coverage | `dazzle compliance compile` → `Coverage` line | 54% SOC 2 on `support_tickets` |
| Test suite size | `pytest tests/ -m "not e2e" --co -q` | ~17,900 unit tests (~1,600 touch RBAC/scope/audit/compliance) |

---

## What to stay skeptical about

- **`PERMIT_UNPROTECTED` is silent-ish.** A rule-less entity is open. It is a
  warning, not a build failure (outside the `shapes_validation` CI gate). Grep
  your own app's matrix.
- **"Verify" is a probe, not a proof.** It compares observed HTTP status to the
  matrix. It catches divergence; it does not prove the enforcement code correct.
- **"Compliance" is evidence mapping.** It does not make you compliant and does
  not look at infrastructure. ~40% of ISO 27001 controls are not even
  assessable from a DSL.
- **Several RBAC subsystems are Beta and young.** The dynamic verifier shipped
  in the 0.71 series; the enforcement path has had security fixes across recent
  releases. Sound architecture, still-hardening surface.
- **The DSL is opinionated.** Adopting Dazzle means adopting its model of
  entities/roles/workflows. That is the real cost the capability matrix above
  does not show.

If something here does not match what the commands print on your machine, the
commands are right and this document is stale — please open an issue.
