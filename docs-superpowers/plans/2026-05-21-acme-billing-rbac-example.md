# `examples/acme_billing` Canonical Adversarial RBAC Example — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `examples/acme_billing` — a multi-tenant billing app whose `scope:` rules exercise every predicate-algebra form — plus an adversarial RBAC pytest suite that gates CI and drift-gated reference outputs.

**Architecture:** A standard Dazzle example app (`dazzle.toml` + `dsl/*.dsl` + `README.md`). RBAC lives in entity `permit:`/`scope:`/`forbid:` blocks. Adversarial verification is imperative pytest in the framework suite; committed reference outputs are guarded by a drift test.

**Tech Stack:** Dazzle DSL, PostgreSQL runtime, `pytest` (`postgres`/`e2e` markers), existing `dazzle validate` / `lint` / `rbac matrix` / `compliance report` CLI.

**Spec:** `docs/superpowers/specs/2026-05-21-acme-billing-rbac-example-design.md`

---

## File Structure

```
examples/acme_billing/
  dazzle.toml                 project manifest
  README.md                   walkthrough (Task 8)
  dsl/
    app.dsl                   module + app declaration (Task 1)
    personas.dsl              5 personas (Task 1)
    entities.dsl              5 entities + RBAC rules (Task 2)
    surfaces.dsl              list/view surfaces + workspace (Task 3)
    stories.dsl               expected-behaviour narrative (Task 4)
    demo.dsl                  demo/seed data (Task 5)
  expected/
    rbac-matrix.json          committed reference, drift-gated (Task 7)
    compliance-report.md      committed reference, drift-gated (Task 7)

tests/integration/test_acme_billing_rbac.py      adversarial suite (Task 6)
tests/unit/test_acme_billing_reference_drift.py   reference drift gate (Task 7)
```

**Reference apps to read before starting** (proven DSL patterns):
- `fixtures/rbac_validation/dsl/` — entity `permit:`/`scope:`/`forbid:`/`audit:` syntax, `personas.dsl`, `stories.dsl`.
- `fixtures/shapes_validation/` — **how `current_user.<attr>` tenant scoping is wired** (the `realm = current_user.realm` pattern). `acme_billing` needs `current_user.org`; shapes_validation is the canonical reference for making a user attribute resolvable in `scope:` rules. **Determine this mechanism before writing Task 2** — it dictates whether `User`/auth needs a `tenancy:` block or a user attribute.
- `examples/support_tickets/dsl/` — surface + workspace DSL for a real example app.
- `examples/ops_dashboard/` — `dazzle.toml` shape.

---

## Task 1: Scaffold — manifest, app, personas

**Files:**
- Create: `examples/acme_billing/dazzle.toml`
- Create: `examples/acme_billing/dsl/app.dsl`
- Create: `examples/acme_billing/dsl/personas.dsl`

- [ ] **Step 1: Read a reference manifest**

Run: `cat examples/ops_dashboard/dazzle.toml fixtures/rbac_validation/dazzle.toml`
Note the required keys (project name, dsl dir, any auth/tenancy config).

- [ ] **Step 2: Write `dazzle.toml`**

Mirror `ops_dashboard/dazzle.toml`. Project name `acme_billing`. Include whatever auth section the reference apps use (the app needs auth for RBAC to engage).

- [ ] **Step 3: Write `dsl/app.dsl`**

```
module acme_billing

app acme_billing "Acme Billing":
  description: "Multi-tenant billing — canonical adversarial RBAC example"
```

> Confirm the exact `app` block fields against `fixtures/rbac_validation/dsl/app.dsl` — match its shape.

- [ ] **Step 4: Write `dsl/personas.dsl`**

Five personas. Mirror `fixtures/rbac_validation/dsl/personas.dsl` structure exactly (`persona <id> "<Label>": description / goals / proficiency`).

```
module acme_billing.personas

persona admin "Administrator":
  description: "Platform administrator — full cross-org access (break-glass)"
  goals: "Manage organizations", "Audit access"
  proficiency: expert

persona org_owner "Organization Owner":
  description: "Owns one organization — full access within that org only"
  goals: "Manage projects", "Review invoices"
  proficiency: expert

persona auditor "Auditor":
  description: "Read-only reviewer scoped to one organization"
  goals: "Review invoices and projects", "Verify compliance"
  proficiency: intermediate

persona project_member "Project Member":
  description: "Works on assigned projects only"
  goals: "View assigned projects", "View project invoices"
  proficiency: intermediate

persona external_contractor "External Contractor":
  description: "Limited outside collaborator — non-sensitive data on assigned projects"
  goals: "View assigned non-sensitive project data"
  proficiency: beginner
```

- [ ] **Step 5: Validate**

Run: `cd examples/acme_billing && python -m dazzle validate; cd -`
Expected: parses without error (warnings about no entities are acceptable at this stage).

- [ ] **Step 6: Commit**

```bash
git add examples/acme_billing/dazzle.toml examples/acme_billing/dsl/app.dsl examples/acme_billing/dsl/personas.dsl
git commit -m "feat(example): scaffold acme_billing — manifest, app, personas (#1174)"
```

---

## Task 2: Entities + RBAC rules — the core

**Files:**
- Create: `examples/acme_billing/dsl/entities.dsl`

- [ ] **Step 1: Confirm the `current_user.org` mechanism**

Read `fixtures/shapes_validation/` end-to-end (its DSL + README + `dazzle.toml`). Determine exactly how a `scope:` rule references a user attribute (`current_user.realm` there). Record:
- whether a `tenancy:` block is required,
- how the auth user acquires the `org` attribute,
- the exact `scope:` line syntax for `field = current_user.<attr>`.

This is the one genuinely uncertain mechanism — do not guess; the rest of the task depends on it.

- [ ] **Step 2: Write `dsl/entities.dsl`**

Five entities. Use `fixtures/rbac_validation/dsl/entities.dsl` for the `permit:`/`scope:`/`forbid:`/`audit:` block syntax, and the Step-1 finding for the `current_user.org` lines. Each `scope:` rule needs a matching `permit:` rule and an `as:` clause.

```
module acme_billing.entities

entity Organization "Organization":
  intent: "Tenant root — exercises direct-equality scope"
  id: uuid pk
  name: str(120) required
  created_at: datetime auto_add
  permit:
    create: role(admin)
    read: role(admin) or role(org_owner) or role(auditor)
    update: role(admin)
    delete: role(admin)
    list: role(admin) or role(org_owner) or role(auditor)
  scope:
    list: all
      as: admin
    read: id = current_user.org
      as: org_owner, auditor
    list: id = current_user.org
      as: org_owner, auditor
  audit: all

entity User "User":
  intent: "Domain user record — belongs to an organization"
  id: uuid pk
  email: email required
  name: str(120) required
  org: ref Organization required
  permit:
    create: role(admin) or role(org_owner)
    read: role(admin) or role(org_owner) or role(auditor)
    update: role(admin) or role(org_owner)
    delete: role(admin)
    list: role(admin) or role(org_owner) or role(auditor)
  scope:
    list: all
      as: admin
    list: org = current_user.org
      as: org_owner, auditor
    read: org = current_user.org
      as: org_owner, auditor
  audit: all

entity Project "Project":
  intent: "Org project — exercises EXISTS-via-junction scope for project_member"
  id: uuid pk
  name: str(120) required
  org: ref Organization required
  created_at: datetime auto_add
  permit:
    create: role(admin) or role(org_owner)
    read: role(admin) or role(org_owner) or role(auditor) or role(project_member)
    update: role(admin) or role(org_owner)
    delete: role(admin) or role(org_owner)
    list: role(admin) or role(org_owner) or role(auditor) or role(project_member)
  scope:
    list: all
      as: admin
    list: org = current_user.org
      as: org_owner, auditor
    read: org = current_user.org
      as: org_owner, auditor
    list: via Membership(user = current_user, project = id)
      as: project_member
    read: via Membership(user = current_user, project = id)
      as: project_member
  audit: all

entity Invoice "Invoice":
  intent: "Billing record — FK-path scope + negation scope for sensitivity"
  id: uuid pk
  number: str(40) required
  amount: int required
  project: ref Project required
  sensitive: bool=false
  created_at: datetime auto_add
  permit:
    create: role(admin) or role(org_owner)
    read: role(admin) or role(org_owner) or role(auditor) or role(project_member) or role(external_contractor)
    update: role(admin) or role(org_owner)
    delete: role(admin)
    list: role(admin) or role(org_owner) or role(auditor) or role(project_member) or role(external_contractor)
  scope:
    list: all
      as: admin
    list: project.org = current_user.org
      as: org_owner, auditor
    read: project.org = current_user.org
      as: org_owner, auditor
    list: not (sensitive = true)
      as: project_member, external_contractor
    read: not (sensitive = true)
      as: project_member, external_contractor
  audit: all

entity Membership "Membership":
  intent: "Junction — assigns users to projects"
  id: uuid pk
  user: ref User required
  project: ref Project required
  permit:
    create: role(admin) or role(org_owner)
    read: role(admin) or role(org_owner)
    update: role(admin) or role(org_owner)
    delete: role(admin) or role(org_owner)
    list: role(admin) or role(org_owner)
  scope:
    list: all
      as: admin
    list: project.org = current_user.org
      as: org_owner
    read: project.org = current_user.org
      as: org_owner
  audit: all
```

> The exact `current_user.org` / `via Membership(...)` / `not (...)` syntax must match what Step 1 confirmed and the CLAUDE.md "Scope rules" section. `dazzle validate` statically validates scope predicates against the FK graph — Step 3 catches any syntax or FK-path error.
>
> Note the `project_member`/`external_contractor` `scope:` on `Invoice` (`not (sensitive = true)`) does **not** also filter by org/membership in v1 — keep the rule set to exactly what the adversarial tests assert. If the parser requires a single `scope:` rule per (op, persona), and a persona needs both a tenant filter AND the sensitivity filter, combine them with `and` per the boolean predicate form: `project.org = current_user.org and not (sensitive = true)`. Confirm against the grammar in Step 1; adjust here.

- [ ] **Step 3: Validate (strict)**

Run: `cd examples/acme_billing && python -m dazzle validate --strict; cd -`
Expected: passes. If a scope predicate fails FK-graph validation, the error names the entity/rule — fix the rule. Every `scope:` must have a matching `permit:` and an `as:` clause, or validation fails.

- [ ] **Step 4: Eyeball the matrix**

Run: `cd examples/acme_billing && python -m dazzle rbac matrix; cd -`
Expected: a table with all five entities × five roles. Sanity-check: `auditor` shows no PERMIT for create/update/delete; `admin` shows PERMIT everywhere; no cell shows `PERMIT_UNPROTECTED`.

- [ ] **Step 5: Commit**

```bash
git add examples/acme_billing/dsl/entities.dsl
git commit -m "feat(example): acme_billing entities + full-predicate-algebra scope rules (#1174)"
```

---

## Task 3: Surfaces

**Files:**
- Create: `examples/acme_billing/dsl/surfaces.dsl`

- [ ] **Step 1: Read a reference surfaces file**

Run: `cat examples/support_tickets/dsl/*.dsl | grep -A20 "^surface\|^workspace"`
Note the `surface … uses entity … mode: list|view` shape and the `workspace` block.

- [ ] **Step 2: Write `dsl/surfaces.dsl`**

One `list` surface and one `view` surface per entity, plus a `workspace` landing page linking them. Keep field projections plain — no charts/regions. Mirror `support_tickets` surface syntax exactly.

```
module acme_billing.surfaces

surface organization_list "Organizations":
  uses entity Organization
  mode: list
  section main:
    field name "Name"

surface organization_detail "Organization":
  uses entity Organization
  mode: view
  section main:
    field name "Name"
    field created_at "Created"

# … repeat list+view for User, Project, Invoice, Membership …

workspace billing "Acme Billing":
  # link the list surfaces — match the workspace syntax in support_tickets
```

> Fill in every entity's list/view surface following the Organization pattern. The `workspace` block syntax must match `support_tickets` — copy it.

- [ ] **Step 3: Validate + lint + coverage**

Run:
```bash
cd examples/acme_billing && python -m dazzle validate && python -m dazzle lint; cd -
python -m dazzle coverage --fail-on-uncovered
```
Expected: validate + lint clean; coverage gate passes (the app uses only already-covered constructs).

- [ ] **Step 4: Commit**

```bash
git add examples/acme_billing/dsl/surfaces.dsl
git commit -m "feat(example): acme_billing surfaces + workspace (#1174)"
```

---

## Task 4: Stories — expected-behaviour narrative

**Files:**
- Create: `examples/acme_billing/dsl/stories.dsl`

- [ ] **Step 1: Write `dsl/stories.dsl`**

One `story` per key RBAC behaviour, mirroring `fixtures/rbac_validation/dsl/stories.dsl` syntax exactly (`story <ID> "<title>": actor / trigger / scope / given / when / then`). Cover: org_owner manages own-org projects; auditor reads but cannot write; project_member sees only assigned projects; external_contractor cannot see sensitive invoices; admin cross-org access.

```
module acme_billing.stories

story ST-001 "Org owner manages projects within their organization":
  actor: org_owner
  trigger: form_submitted
  scope: [Project]
  given:
    - "Org owner is authenticated and belongs to Acme"
  when:
    - "Org owner creates a project"
  then:
    - "Project is created with org = Acme"
    - "Org owner cannot see Globex projects"

# … ST-002 … ST-005 for auditor / project_member / external_contractor / admin
```

- [ ] **Step 2: Validate**

Run: `cd examples/acme_billing && python -m dazzle validate; cd -`
Expected: passes.

- [ ] **Step 3: Commit**

```bash
git add examples/acme_billing/dsl/stories.dsl
git commit -m "feat(example): acme_billing RBAC behaviour stories (#1174)"
```

---

## Task 5: Demo / seed data

**Files:**
- Create: `examples/acme_billing/dsl/demo.dsl` (or the seed mechanism the reference apps use)

- [ ] **Step 1: Determine the seed mechanism**

Read how `fixtures/rbac_validation` and `examples/support_tickets` provide demo data (`demo` DSL construct vs `dazzle demo` generated data). Use whatever those apps use.

- [ ] **Step 2: Write the demo data**

Two organizations — **Acme** and **Globex** — each with: users across all roles, 2–3 projects, several invoices (≥1 `sensitive` per org), memberships assigning `project_member` users to a subset of projects. This is the app's runnable demo data.

> The *adversarial tests* (Task 6) seed their own deterministic rows via the API — they do not depend on this demo data. This `demo.dsl` exists so `dazzle serve` shows a populated, inspectable app.

- [ ] **Step 3: Validate**

Run: `cd examples/acme_billing && python -m dazzle validate; cd -`
Expected: passes.

- [ ] **Step 4: Commit**

```bash
git add examples/acme_billing/dsl/demo.dsl
git commit -m "feat(example): acme_billing demo data — two tenants (#1174)"
```

---

## Task 6: Adversarial RBAC test suite

**Files:**
- Create: `tests/integration/test_acme_billing_rbac.py`

- [ ] **Step 1: Read the e2e test harness**

Read `tests/integration/test_runtime_e2e.py` end-to-end. Identify the exact pattern for: booting an example app against PostgreSQL, getting an HTTP client, and authenticating. Mirror it. Note the markers it uses (`@pytest.mark.e2e`, fixtures for the DB/app).

Also read `src/dazzle/cli/rbac.py:138-186` (`_login`) — the JSON `/auth/login` flow — and the #1171 verifier plan (`docs/superpowers/plans/2026-05-20-rbac-verifier.md`) for the per-role user-seeding approach. The acme_billing tests need the same: seed one user per role into each org, log in per role.

- [ ] **Step 2: Write the test module skeleton + fixtures**

```python
"""Adversarial RBAC tests for examples/acme_billing (#1174).

Each test exercises an attack/failure path against the multi-tenant
billing app — IDOR, cross-tenant leakage, sensitive-data denial, bulk
bypass — and asserts the RBAC guarantee holds.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

# Fixtures: boot examples/acme_billing against PostgreSQL, seed two orgs
# (Acme, Globex) each with users for every role + projects + invoices
# (some sensitive) + memberships. Mirror tests/integration/test_runtime_e2e.py.
# Expose, per the booted app: an httpx client factory `client_as(role, org)`
# that returns a session authenticated as that role in that org, and the
# seeded ids (acme_invoice_id, globex_invoice_id, sensitive_invoice_id,
# acme_project_id, unassigned_project_id, …).
```

> The fixture is the bulk of this task. Build it directly on the `test_runtime_e2e.py` pattern from Step 1 — do not invent a new harness. If `test_runtime_e2e.py` already exposes a reusable app-boot fixture, import it; otherwise add a local fixture in this file.

- [ ] **Step 3: Write the adversarial tests**

```python
async def test_idor_foreign_org_invoice_returns_404(rbac_app) -> None:
    """An Acme org_owner fetching a Globex invoice by id gets 404 —
    indistinguishable from a non-existent row (no existence leak)."""
    client = await rbac_app.client_as("org_owner", org="acme")
    resp = await client.get(f"/api/invoices/{rbac_app.globex_invoice_id}")
    assert resp.status_code == 404


async def test_cross_tenant_list_isolation(rbac_app) -> None:
    """An Acme org_owner's invoice list contains only Acme invoices."""
    client = await rbac_app.client_as("org_owner", org="acme")
    resp = await client.get("/api/invoices")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()["items"]}
    assert rbac_app.globex_invoice_id not in ids
    assert rbac_app.acme_invoice_id in ids


async def test_sensitive_invoice_denied_to_contractor(rbac_app) -> None:
    """external_contractor cannot read a sensitive invoice (negation scope)."""
    client = await rbac_app.client_as("external_contractor", org="acme")
    resp = await client.get(f"/api/invoices/{rbac_app.sensitive_invoice_id}")
    assert resp.status_code == 404


async def test_bulk_action_denied_for_unpermitted_role(rbac_app) -> None:
    """Bulk action on invoices as a non-permitted role is denied — the
    #1170 bulk-bypass regression, pinned in a realistic app."""
    client = await rbac_app.client_as("external_contractor", org="acme")
    resp = await client.post(
        "/api/invoices/bulk",
        json={"action": "<a declared bulk action>", "ids": [rbac_app.acme_invoice_id]},
    )
    assert resp.status_code in (403, 404)


async def test_auditor_is_read_only(rbac_app) -> None:
    """auditor has no create/update/delete permit — writes are denied."""
    client = await rbac_app.client_as("auditor", org="acme")
    create = await client.post("/api/projects", json={"name": "x", "org": rbac_app.acme_org_id})
    assert create.status_code == 403


async def test_project_member_sees_only_assigned_projects(rbac_app) -> None:
    """project_member's project list is filtered to Membership rows."""
    client = await rbac_app.client_as("project_member", org="acme")
    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()["items"]}
    assert rbac_app.assigned_project_id in ids
    assert rbac_app.unassigned_project_id not in ids


async def test_admin_has_cross_org_access(rbac_app) -> None:
    """Positive control — admin sees both orgs' invoices."""
    client = await rbac_app.client_as("admin", org="acme")
    resp = await client.get("/api/invoices")
    ids = {row["id"] for row in resp.json()["items"]}
    assert {rbac_app.acme_invoice_id, rbac_app.globex_invoice_id} <= ids


async def test_denied_access_emits_audit_record(rbac_app) -> None:
    """A denied access produces a row in _dazzle_audit_log."""
    client = await rbac_app.client_as("external_contractor", org="acme")
    await client.get(f"/api/invoices/{rbac_app.globex_invoice_id}")
    rows = await rbac_app.query_audit_log(entity="Invoice", decision="deny")
    assert rows, "expected an audit record for the denied Invoice read"
```

> If `examples/acme_billing` declares no `bulk_actions:` on a list surface, either add one (an Invoice status transition) in `surfaces.dsl` so test 4 is real, or drop test 4 and note bulk-bypass stays covered by `test_bulk_routes.py`. Adding one is preferred — it makes the bulk path part of the canonical example.

- [ ] **Step 4: Run the suite**

Run: `python -m pytest tests/integration/test_acme_billing_rbac.py -v -m "e2e and postgres"`
Expected: all pass. A failure is either a real RBAC bug (investigate — a genuine finding) or a test/fixture bug (fix the test).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_acme_billing_rbac.py examples/acme_billing/dsl/surfaces.dsl
git commit -m "test(example): adversarial RBAC suite for acme_billing (#1174)"
```

---

## Task 7: Committed reference outputs + drift gate

**Files:**
- Create: `examples/acme_billing/expected/rbac-matrix.json`
- Create: `examples/acme_billing/expected/compliance-report.md`
- Create: `tests/unit/test_acme_billing_reference_drift.py`

- [ ] **Step 1: Generate the reference outputs**

Run:
```bash
cd examples/acme_billing
mkdir -p expected
python -m dazzle rbac matrix --format json > expected/rbac-matrix.json
python -m dazzle compliance report > expected/compliance-report.md
cd -
```

> Confirm the exact `dazzle compliance report` invocation/flags by running `python -m dazzle compliance --help`. If the report needs a framework argument (e.g. `--framework soc2`), pin it and use the same flag in the drift test.

- [ ] **Step 2: Read the drift-test pattern**

Read `tests/unit/test_api_surface_drift.py` — it regenerates a baseline and diffs against the committed copy. Mirror its structure.

- [ ] **Step 3: Write `tests/unit/test_acme_billing_reference_drift.py`**

```python
"""Drift gate for examples/acme_billing committed reference outputs (#1174).

Regenerates the RBAC matrix and compliance report and diffs them against
the committed copies. A framework change that alters either output fails
here — update the committed reference (and CHANGELOG) deliberately.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

_APP = Path("examples/acme_billing")


def test_rbac_matrix_matches_committed_reference() -> None:
    committed = json.loads((_APP / "expected" / "rbac-matrix.json").read_text())
    result = subprocess.run(
        ["python", "-m", "dazzle", "rbac", "matrix", "--format", "json"],
        cwd=_APP, capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout) == committed, (
        "acme_billing RBAC matrix drifted from expected/rbac-matrix.json — "
        "regenerate it and note the change in CHANGELOG."
    )


def test_compliance_report_matches_committed_reference() -> None:
    committed = (_APP / "expected" / "compliance-report.md").read_text()
    result = subprocess.run(
        ["python", "-m", "dazzle", "compliance", "report"],  # match Step-1 flags
        cwd=_APP, capture_output=True, text=True, check=True,
    )
    assert result.stdout == committed, (
        "acme_billing compliance report drifted from expected/compliance-report.md — "
        "regenerate it and note the change in CHANGELOG."
    )
```

> If the compliance report embeds a timestamp or other nondeterministic content, normalise it in both the committed file and the test (strip the volatile line) — a drift test must compare only stable content.

- [ ] **Step 4: Run the drift test**

Run: `python -m pytest tests/unit/test_acme_billing_reference_drift.py -v`
Expected: PASS (committed copies were just generated).

- [ ] **Step 5: Commit**

```bash
git add examples/acme_billing/expected/ tests/unit/test_acme_billing_reference_drift.py
git commit -m "test(example): drift-gated reference outputs for acme_billing (#1174)"
```

---

## Task 8: README walkthrough

**Files:**
- Create: `examples/acme_billing/README.md`

- [ ] **Step 1: Write the README**

Structure: (1) one-paragraph purpose — the canonical adversarial RBAC example; (2) the domain model + role table; (3) the **inspection walkthrough** — copy-pasteable commands each with expected output:

```bash
# 1. Validate the app
dazzle validate examples/acme_billing

# 2. See the RBAC model
cd examples/acme_billing && dazzle rbac matrix

# 3. See compliance evidence coverage
dazzle compliance report

# 4. Run the adversarial RBAC suite
pytest tests/integration/test_acme_billing_rbac.py -v -m "e2e and postgres"

# 5. Run the app
dazzle serve
```

(4) a short "what each scope rule demonstrates" table mapping each entity's `scope:` to the predicate form it exercises. Keep it inspectable and concrete — show real expected output snippets, not prose.

- [ ] **Step 2: Verify README commands**

Run each command block from the README and confirm the output matches what the README claims. Fix any mismatch.

- [ ] **Step 3: Commit**

```bash
git add examples/acme_billing/README.md
git commit -m "docs(example): acme_billing README walkthrough (#1174)"
```

---

## Final steps

- [ ] **Full validation sweep.** Run `python -m pytest tests/ -m "not e2e" -q -n auto` (drift test + discovery tests — `acme_billing` is now picked up by `test_examples_rbac_lint_clean`, `test_cli_sweep`, etc.; fix any real failure, re-run flakes in isolation). Run the e2e suite: `python -m pytest tests/integration/test_acme_billing_rbac.py -m "e2e and postgres" -v`.
- [ ] **Bump + CHANGELOG.** Run `/bump patch`. CHANGELOG entry:

```markdown
### Added

- **`examples/acme_billing` — canonical adversarial RBAC example** (#1174).
  A multi-tenant billing app whose `scope:` rules exercise every
  predicate-algebra form (direct equality, FK-path, EXISTS-via-junction,
  negation), with an adversarial pytest suite (IDOR, cross-tenant
  isolation, sensitive-invoice denial, bulk-bypass, auditor read-only)
  that gates CI, drift-gated committed reference outputs, and a README
  walkthrough. The home the #1173 adversarial tests anticipated and a
  realistic target for the #1171 dynamic verifier.
```

- [ ] **Ship.** Commit, push, monitor CI (`gh run list --branch main`). The new app is exercised by the `e2e-smoke` (validate/lint all examples) and unit (drift + discovery) jobs — watch those.
- [ ] **Close #1174.** Comment summarising the app + commits; `gh issue close 1174`.
- [ ] **Update #1173 / #1171.** Note in #1173 that its app-level adversarial cases now have a home; note in the #1171 plan that `acme_billing` is available as a verifier target.

---

## Notes for the implementer

- **The two uncertain mechanisms** — both have explicit "read first" steps: `current_user.org` scope resolution (Task 2 Step 1, reference `fixtures/shapes_validation`) and the e2e app-boot harness (Task 6 Step 1, reference `tests/integration/test_runtime_e2e.py`). Read those before writing; do not guess.
- **`dazzle validate` is the DSL test loop.** Scope predicates are statically validated against the FK graph at validate time, so a wrong FK-path or junction binding fails fast at each task's validate step — that is the TDD signal for the DSL tasks.
- **Discovery tests will pick up the new app automatically** — `test_examples_rbac_lint_clean`, `test_cli_sweep`, `test_ir_field_reader_parity` and similar iterate `examples/`. The final full-suite run catches any discovery-test breakage.
- **Postgres required** for Tasks 6 and the e2e run. The unit/drift test (Task 7) and the DSL tasks (1–5) do not need it.
- **If a real RBAC bug surfaces** while writing Task 6 (a test fails because enforcement is genuinely wrong), that is a finding — file it as its own issue and either fix it in scope or note it; do not weaken the test to make it pass.
