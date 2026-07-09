# Invoice Ops

> **Complexity**: Advanced | **Entities**: 6 | **Personas**: 6 | **DSL Lines**: ~600

`invoice_ops` is the **keystone example app** in the Dazzle examples collection — built specifically to prove the framework under realistic multi-tenant, multi-role, workflow-driven pressure. It models a supplier-invoice approval and payment-operations platform for a SaaS product that serves multiple isolated customer tenants. The app exercises `shared_schema` tenancy with `partition_key: tenant_id`, a 6-state role-guarded Invoice state machine, maker-checker `approval` gates, HLESS event publishing with a `InvoiceStatusView` projection, and a `payment_provider` integration service. The build was conducted as an evaluator-briefing improvement round: every friction point encountered was logged, reproduced, and filed as a framework issue.

---

## Running it

```bash
cd examples/invoice_ops
dazzle serve   # without Docker
```

- UI: http://localhost:3000
- API docs: http://localhost:8000/docs

Requires a PostgreSQL database. Set `DATABASE_URL=postgresql://localhost/invoice_ops` (or any valid connection string) before running.

---

## The invoice lifecycle

### State machine

Invoices move through six states:

```
draft → submitted → approved → paid
                ↘ rejected
                              ↘ disputed → approved
                                         ↘ rejected
```

Every transition is role-guarded:

| Transition | Required role | Notes |
|------------|--------------|-------|
| `draft → submitted` | `requester` | Submitter records themselves as `submitted_by` |
| `submitted → approved` | `approver` | Core maker-checker gate |
| `submitted → rejected` | `approver` | Requires `rejection_reason` |
| `approved → paid` | `finance` | Triggers payment; creates a `PaymentAttempt` |
| `approved → disputed` | `finance` | Requires `dispute_reason` |
| `paid → disputed` | `finance` | Post-payment dispute, requires `dispute_reason` |
| `disputed → approved` | `finance` | Reinstates for payment |
| `disputed → rejected` | `approver` | Final rejection from dispute |

### Maker-checker model

The app declares two approval gates that enforce quorum on the submit-to-approved path:

- **`StandardApproval`** — quorum 1, applies to invoices below the per-tenant `approval_threshold`
- **`HighValueApproval`** — quorum 2, applies to invoices at or above `approval_threshold`

The threshold itself is a per-tenant configuration key (`per_tenant_config: approval_threshold: int`), so each tenant can set their own value. Both gates validate cleanly and `dazzle validate` accepts the declarations; see the friction log for the current enforcement status.

### Role summary

| Role | Trust boundary | Key capabilities |
|------|---------------|-----------------|
| `requester` | Own tenant | Create invoices, submit for approval |
| `approver` | Own tenant | Approve or reject submitted invoices |
| `finance` | Own tenant | Pay, dispute, manage suppliers and payment attempts |
| `finance_admin` | Own tenant | Finance Administrator — cross-cutting finance oversight, an override role above `finance`; same access `finance` has on Invoice and PaymentAttempt |
| `auditor` | Own tenant, read-only | Read invoices, line items, payment attempts, users |
| `tenant_admin` | Own tenant | Manage users, suppliers, tenant configuration |

---

## Tenant isolation

The app uses `shared_schema` tenancy with `partition_key: tenant_id`:

```dsl
tenancy:
  mode: shared_schema
  partition_key: tenant_id
  per_tenant_config:
    approval_threshold: int
    base_currency: str
```

Every tenant-scoped entity (`User`, `Supplier`, `Invoice`, `LineItem`, `PaymentAttempt`) carries a `tenant_id: ref Tenant required` FK and a matching `scope: tenant_id = current_user.tenant_id` rule on every operation. These scope rules are load-bearing — the runtime enforces them as SQL `WHERE` predicates on every query.

### Membership model (auth Plan 1d)

`Tenant` is declared `archetype: tenant`, so it is the framework **tenant root**. On the auth identity model, each `Tenant` row is mirrored 1:1 into the framework `organizations` table at the **same id**, and every user gets a `membership` in their tenant — so `membership.tenant_id == Tenant.id == dazzle.tenant_id` and a logged-in member is fenced to their tenant by Postgres **RLS** at the database (defence-in-depth *under* the app-layer `scope:` filters above; RLS is only observable when the app runs as a non-superuser DB role). `current_user.tenant_id` resolves membership-first.

This is a **multi-tenant** app, so it does **not** use `auto_provision_single_org` (that flag funnels every login into one default org — for single-org apps only). To bring an existing invoice_ops deployment onto the membership model, backfill it:

```bash
dazzle auth migrate --dry-run   # preview: orgs mirrored + memberships per user
dazzle auth migrate             # mirror each Tenant → organizations (shared id) + a membership per user
```

`auth migrate` resolves each auth user's tenant via the domain `User` entity (matched by email → its `tenant_id`); it is idempotent and reports any user with no resolvable tenant rather than guessing. Tenant-scoped creates no longer take `tenant_id` as input — the DB fills it from the bound session (`current_setting('dazzle.tenant_id')`), so a create on an unbound session fails closed.

The adversarial isolation suite at `tests/integration/test_invoice_ops_tenant_isolation.py` probes **11 cross-tenant vectors** including:

- Cross-tenant list leak (read Tenant B's invoices as a Tenant A user)
- Cross-tenant read by UUID (IDOR)
- Cross-tenant update
- Cross-tenant delete
- Cross-tenant supplier registration
- Creating an invoice that references another tenant's supplier (FK injection)
- Cross-tenant payment attempt
- `tenant_admin` cross-tenant scope bypass (the `admin_personas` footgun — see friction log)

Result: **10 passed, 2 skipped** (skipped tests require a second tenant row in the seed data for the specific test variant). On the membership model the cross-tenant Tenant-root read denies via 403 (the root permit/scope eval) rather than 404 — the isolation suite asserts denial + no config leak, not the exact status code.

---

## Tests

Both integration suites require a PostgreSQL database. Boot the app once first to run migrations, then run:

```bash
DATABASE_URL=postgresql://localhost/postgres \
  pytest tests/integration/test_invoice_ops_tenant_isolation.py \
         tests/integration/test_invoice_ops_rbac.py \
  -m e2e -v
```

### Tenant isolation suite (`test_invoice_ops_tenant_isolation.py`)

11 tests (9 run, 2 skipped):

| Test | What it probes | Notes |
|------|---------------|-------|
| `test_list_excludes_other_tenant` | Northwind invoice list contains no contoso rows (checks both id and invoice_number) | Runs |
| `test_read_other_tenant_invoice_is_404` | IDOR: northwind requester fetching a contoso invoice by UUID gets 404 | Runs |
| `test_update_other_tenant_invoice_is_404` | Northwind approver cannot update a contoso invoice (404 or 405) | Runs |
| `test_delete_other_tenant_supplier_is_404` | Northwind `tenant_admin` cannot delete a contoso supplier by UUID | Runs |
| `test_create_invoice_with_foreign_supplier_rejected` | Invoice create referencing a contoso supplier is rejected (cross-tenant FK injection) | Runs |
| `test_read_other_tenant_lineitem_is_404` | IDOR: northwind requester fetching a contoso line item by UUID gets 404 | Runs |
| `test_admin_positive_control` | Sanity check: northwind requester CAN read a northwind invoice (guards against over-filtering false-greens) | Runs |
| `test_search_excludes_other_tenant` | Northwind invoice list with search params (`q=`, `search=`) contains no contoso data | Runs |
| `test_audit_export_excludes_other_tenant` | Northwind auditor's `/_dazzle/audit/logs` view contains no contoso entity ids | **Skipped** — `/_dazzle/audit/logs` not accessible to auditor role; endpoint gated |
| `test_event_log_excludes_other_tenant` | `/_dazzle/events/topics/invoice_events` contains no contoso tenant_id | **Skipped** — events subsystem not wired under in-process transport (no lifespan, no REDIS_URL); endpoint returns 500 |
| `test_other_tenant_config_denied` | Northwind `tenant_admin` cannot read or delete the contoso `Tenant` row (per-tenant config container) | Runs |

### RBAC / transition suite (`test_invoice_ops_rbac.py`)

4 tests (3 run, 1 skipped):

| Test | What it probes | Notes |
|------|---------------|-------|
| `test_requester_cannot_approve` | A requester attempting `submitted → approved` is denied (403/404/422) — approver-only transition | Runs |
| `test_approver_cannot_pay` | An approver attempting `approved → paid` is denied (403/404/422) — finance-only transition | Runs |
| `test_approver_can_approve` | Positive control: approver driving `submitted → approved` succeeds (200/204/302) | Runs |
| `test_projection_agrees_with_status_column` | `InvoiceStatusView` projection status agrees with raw `Invoice.status` column | **Skipped** — no queryable projection route; events subsystem not functional under in-process ASGITransport |

---

## Project structure

```
invoice_ops/
├── dazzle.toml                        # Project configuration
├── README.md                          # This file
├── dsl/
│   ├── app.dsl                        # Module root + tenancy block
│   ├── entities.dsl                   # 6 entities with scope rules and transitions
│   ├── personas.dsl                   # 5 persona definitions
│   ├── surfaces.dsl                   # List / view / create / edit surfaces
│   ├── workflow.dsl                   # Approval gates, settle_invoice process
│   ├── events.dsl                     # HLESS event model + InvoiceStatusView projection
│   ├── services.dsl                   # payment_provider integration service
│   └── seeds/
│       └── demo_data/                 # 2-tenant JSONL seed fixtures
└── tests/
    └── integration/
        ├── invoice_ops_harness.py     # Test harness (in-process app boot + auth helpers)
        ├── test_invoice_ops_tenant_isolation.py   # Adversarial cross-tenant suite
        └── test_invoice_ops_rbac.py               # Transition RBAC suite
```

---

## Friction log

The table below records framework friction encountered during the invoice_ops keystone build. Items marked with an issue number were filed as GitHub issues. Items marked "resolved" were fixed in this build round. Items marked "known" are pre-existing and tracked separately.

| # | Area | Finding | Status |
|---|------|---------|--------|
| 1 | `approval` gates | Variable quorum by amount (`StandardApproval` quorum 1, `HighValueApproval` quorum 2 with `threshold:`) validates cleanly — but `dazzle validate` warns `[Preview] approval gates are not yet enforced at runtime`. Quorum is **declared**, not enforced. | Known — preview |
| 2 | `approval threshold:` | `threshold: amount <= approval_threshold` (a `per_tenant_config` key) is accepted by `dazzle validate`. Same preview-only caveat as #1. | Known — preview |
| 3 | Separation of duty | Role-level transition guards (`role(approver)`) **are** enforced at runtime. Actor-identity SoD (the user who submitted cannot also approve) is **not** expressible or enforced in DSL. | Limitation |
| 4 | `partition_key` enforcement | `partition_key: tenant_id` with `ref Tenant` FK fields is accepted. Runtime tenant isolation is enforced. Explicit per-entity `scope:` rules are load-bearing (not auto-derived from `partition_key`). | Resolved |
| 5 | Audit export | No dedicated audit-export route; `audit_export` surface collided with `GET /invoices` at boot and was dropped as a duplicate. The internal `/_dazzle/audit/logs` endpoint exists but is admin-gated. | Limitation |
| 6 | Cross-tenant FK rejection | Creating an invoice that references another tenant's supplier is correctly rejected. | Resolved |
| 7 | `admin_personas` footgun | `tenancy: admin_personas:` grants a **cross-tenant scope bypass**. Listing the within-tenant `tenant_admin` role there silently made it a cross-tenant superuser; the adversarial suite caught 2 real cross-tenant leaks. `dazzle validate` did not warn. Fixed in invoice_ops by removing `tenant_admin` from `admin_personas`. | Fixed in app → [#1184](https://github.com/manwithacat/dazzle/issues/1184) (framework guard) |
| 8 | `postgres://` URL scheme | Runtime did not normalize the `postgres://` scheme alias; `DATABASE_URL=postgres://...` 500'd. `EVALUATION.md` instructs evaluators to use exactly that form. Fixed in commit `bcfce910`. | Resolved → [#1185](https://github.com/manwithacat/dazzle/issues/1185) (consolidation) |
| 9 | Scheme-normalization duplication | The `postgres://` → `postgresql://` rewrite is duplicated across ~17 files. | [#1185](https://github.com/manwithacat/dazzle/issues/1185) |
| 10 | E2E generator skips role-guarded transitions | `src/dazzle/testing/testspec_generator.py` line 587 skips all transitions with `role()` guards. Invoice_ops received zero auto-derived lifecycle E2E flows. | [#1186](https://github.com/manwithacat/dazzle/issues/1186) |
| 11 | `dazzle e2e run-viewport` broken | Fails with `ModuleNotFoundError: No module named 'dazzle.core.loader'` — `viewport_testing.py` imports a renamed module. | [#1187](https://github.com/manwithacat/dazzle/issues/1187) |
| 12 | Transition-guard denials return HTTP 422 | Denied role-guarded transitions return 422 Unprocessable Entity instead of 403 Forbidden. Denial is correct; status code is softer than expected. | Minor |
| 13 | `Tenant.create` open to `tenant_admin` | The `Tenant` entity's `permit: create: role(tenant_admin)` with `scope: create: all` allows a `tenant_admin` to create new `Tenant` rows without restriction. In a production multi-tenant SaaS, tenant provisioning would be a platform-admin action outside any tenant's trust boundary. `invoice_ops` keeps this simple: tenants are demo seed data and there is no platform-admin persona in the DSL. This is a deliberate simplification, not a bug. | Known limitation |
| 14 | Event model only partially wired to publishers | `events.dsl` declares 6 events (`InvoiceSubmitted`, `InvoiceApproved`, `InvoiceRejected`, `InvoiceDisputed`, `InvoicePaid`, `PaymentAttemptFailed`), but the `Invoice` entity only has `publish` directives for `InvoiceSubmitted` and `InvoicePaid`. The entity-level `publish … when status changed` trigger fires on coarse state changes and cannot emit a distinct event per target state; fine-grained per-transition events (`InvoiceApproved`, `InvoiceRejected`, `InvoiceDisputed`) are declared in the model but have no publisher wired to them. The events stack is preview-only regardless, so this is a known limitation rather than an actionable gap. | Known limitation — preview |

The rows below were added during the **SP2 migration exercise** (branch `feat/migration-story-sp2`), which evolved the invoice_ops schema through 6 requirement changes (Changes 0–6).

| # | Area | Finding | Status |
|---|------|---------|--------|
| SP2-1 | `dazzle db baseline` | `dazzle db baseline` crashed on a fresh example app with `AttributeError: 'NoneType' object has no attribute 'config'` — `env.py` module-level code accessed `context.config` before the context was bound. Fixed by extracting a `metadata_loader.py` module and deferring DSL loading into the Alembic `run_migrations_*` functions. | Fixed this round → [#1190](https://github.com/manwithacat/dazzle/issues/1190) |
| SP2-2 | `.gitignore` + migrations | `.dazzle/` is gitignored, so a project must manually un-ignore its `migrations/` subtree (`.gitignore` exception `!.dazzle/migrations/versions/`) to version-control migration history. The scaffold should emit this exception by default. | [#1190](https://github.com/manwithacat/dazzle/issues/1190) |
| SP2-3 | `dazzle db revision` autogenerate | `dazzle db revision --autogenerate` emits spurious ops on every run: (1) a `drop_table('_dazzle_params')` for the framework table not in app metadata, and (2) unnamed `id` unique-constraint re-emissions for every entity. Must be hand-stripped before committing each migration. | [#1188](https://github.com/manwithacat/dazzle/issues/1188) |
| SP2-4 | First-time DB setup | First-time setup is a non-obvious two-step: `dazzle db upgrade` (framework baseline only, no project tables) then `dazzle db baseline` (captures current schema) then `dazzle db upgrade` (applies the baseline migration). Unintuitive sequence — the CLI output does not guide users through it. | Known — UX gap |
| SP2-5 | Field-rename autogenerate | `dazzle db revision --autogenerate` emits a data-destroying `drop_column` + `add_column` pair for a renamed field (`bank_reference` → `bank_account_ref`). Must be hand-edited to `op.alter_column(...)` to preserve data. No DSL-level `rename:` hint exists to guide autogenerate. | Known limitation |
| SP2-6 | DSL `enum` → unconstrained TEXT | A DSL `enum` field (e.g. `Invoice.status`) maps to an unconstrained `TEXT` column in PostgreSQL. Enum validity is not DB-enforced — any string can be inserted at the SQL level. A PostgreSQL `CHECK` constraint or native `ENUM` type would enforce validity. | Known limitation |
| SP2-7 | `event_model` — no schema versioning | `event_model` has no event-schema-versioning mechanism (no version field, no compatibility declaration, no upcaster). Adding a required field to a declared event is a silent breaking change for consumers. The `hless` construct is a better fit for schema-evolving event streams. | [#1189](https://github.com/manwithacat/dazzle/issues/1189) |

---

*Part of the DAZZLE examples collection. See `examples/` for the full set.*
