# Invoice Ops

> **Complexity**: Advanced | **Entities**: 6 | **Personas**: 5 | **DSL Lines**: ~600

`invoice_ops` is the **keystone example app** in the Dazzle examples collection — built specifically to prove the framework under realistic multi-tenant, multi-role, workflow-driven pressure. It models a supplier-invoice approval and payment-operations platform for a SaaS product that serves multiple isolated customer tenants. The app exercises `shared_schema` tenancy with `partition_key: tenant_id`, a 6-state role-guarded Invoice state machine, maker-checker `approval` gates, HLESS event publishing with a `InvoiceStatusView` projection, and a `payment_provider` integration service. The build was conducted as an evaluator-briefing improvement round: every friction point encountered was logged, reproduced, and filed as a framework issue.

---

## Running it

```bash
cd examples/invoice_ops
dazzle serve --local   # without Docker
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

The adversarial isolation suite at `tests/integration/test_invoice_ops_tenant_isolation.py` probes **11 cross-tenant vectors** including:

- Cross-tenant list leak (read Tenant B's invoices as a Tenant A user)
- Cross-tenant read by UUID (IDOR)
- Cross-tenant update
- Cross-tenant delete
- Cross-tenant supplier registration
- Creating an invoice that references another tenant's supplier (FK injection)
- Cross-tenant payment attempt
- `tenant_admin` cross-tenant scope bypass (the `admin_personas` footgun — see friction log)

Result: **9 passed, 2 skipped** (skipped tests require a second tenant row in the seed data for the specific test variant).

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

9 tests (2 skipped without a second seeded tenant):

| Test | What it probes |
|------|---------------|
| `test_cross_tenant_invoice_list_isolation` | Tenant B user cannot list Tenant A invoices |
| `test_cross_tenant_invoice_read_by_id` | IDOR: Tenant B user cannot read a Tenant A invoice by UUID |
| `test_cross_tenant_invoice_update` | Tenant B user cannot update a Tenant A invoice |
| `test_cross_tenant_invoice_delete` | Tenant B user cannot delete a Tenant A invoice |
| `test_cross_tenant_supplier_list_isolation` | Supplier list is scoped per tenant |
| `test_create_invoice_with_foreign_supplier_rejected` | Cross-tenant FK injection on create is rejected |
| `test_cross_tenant_payment_attempt_isolation` | Payment attempt reads are scoped per tenant |
| `test_tenant_admin_cannot_read_other_tenant` | `tenant_admin` is NOT a cross-tenant bypass (fixed) |
| `test_tenant_admin_cannot_delete_other_tenant_invoice` | `tenant_admin` delete is scoped to own tenant |

### RBAC / transition suite (`test_invoice_ops_rbac.py`)

3 tests (1 skipped without full seed data):

| Test | What it probes |
|------|---------------|
| `test_transition_role_guard_enforced` | Role-guarded transitions are enforced at runtime |
| `test_finance_can_trigger_payment` | `finance` role can move approved → paid |
| `test_requester_cannot_approve` | `requester` role is denied the approved transition |

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

---

*Part of the DAZZLE examples collection. See `examples/` for the full set.*
