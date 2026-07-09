# Acme Billing

> **Complexity**: Advanced | **Entities**: 5 | **Personas**: 5 | **DSL Lines**: ~450

`acme_billing` is the canonical adversarial RBAC example in the Dazzle examples collection. It models a multi-tenant billing platform and exercises every predicate form in Dazzle's scope algebra — direct equality, FK-column equality, FK-path depth-2, EXISTS via junction, and boolean-AND compound predicates — across five personas with deliberately distinct trust levels. The adversarial test suite in `tests/integration/test_acme_billing_rbac.py` does not just check happy paths; it actively attempts IDOR attacks, cross-tenant list leaks, bulk-action bypasses, and sensitive-field exfiltration. If you want to validate that a new scope predicate type or a runtime RBAC change hasn't introduced a regression, this is the app to boot.

---

## Domain model

### Entities

| Entity | Description | Key fields |
|--------|-------------|------------|
| `Organization` | Tenant root. Every user and project belongs to exactly one org. | `id`, `name`, `created_at` |
| `User` | Domain user within an org. The `org` FK is the anchor for `current_user.org` resolution at runtime. | `id`, `email`, `name`, `org` (ref Organization) |
| `Project` | A project owned by an org. `project_member` access is controlled by junction membership, not the org FK directly. | `id`, `name`, `org` (ref Organization) |
| `Invoice` | Billing record attached to a project. Has a `sensitive: bool` flag that gates access for lower-trust roles. Amount stored as integer cents (no separate money type). | `id`, `number`, `amount`, `project` (ref Project), `sensitive` |
| `Membership` | Junction table that assigns users to projects. Drives the `via` EXISTS check for `project_member`. | `id`, `user` (ref User), `project` (ref Project) |

### Roles

| Role | Trust boundary | Notes |
|------|---------------|-------|
| `admin` | Cross-org, unrestricted | Break-glass access. All scope rules are `all`. |
| `org_owner` | Own org only | Read/update within their own organization. Create/delete is restricted: Invoice and Membership create are admin-only (a `scope: create` FK-path limitation, #1124); Organization create/update/delete are admin-only by design; User delete and Invoice delete are also admin-only. org_owner can create/update/delete User and Project rows within their org. |
| `auditor` | Own org, read-only | Can list/read Organizations, Users, Projects, Invoices. No write access. Cannot see Membership records. |
| `project_member` | Assigned projects only | Accesses Projects and Invoices via junction `via Membership`; invoices additionally filtered to `sensitive != true`. |
| `external_contractor` | Non-sensitive invoices on assigned org's projects only | Same invoice filter as `project_member` but no direct Project read access. |

---

## Inspection walkthrough

### Validate the DSL

```bash
cd examples/acme_billing
dazzle validate
```

Expected output (warnings are informational):

```
Validation warnings:

WARNING: [Info] 5 entities have audit: enabled. CRUD operations and access decisions will be logged to the audit trail.
WARNING: [Info] 5 audited entity/entities have include_field_changes enabled. Field-level diffs will be captured for update and delete operations.
WARNING: Entity 'Organization': no fitness.repr_fields declared — fitness evaluation will skip this entity. ...
...

Relevant capabilities (11):
  field 'org' (ref) on surface 'user_create' — widget=combobox in component_showcase/app.dsl:94
  ...
```

The five `fitness.repr_fields` warnings are expected — this example deliberately omits them to stay focused on the RBAC demonstration.

---

### Inspect the RBAC matrix

```bash
cd examples/acme_billing
dazzle rbac matrix
```

Expected output (domain entities only — framework entities such as `SystemHealth`, `SystemMetric`, `DeployHistory` are also present but shown below):

```
| entity       | operation | admin         | org_owner      | auditor        | project_member | external_contractor |
| ---          | ---       | ---           | ---            | ---            | ---            | ---                 |
| Organization | list      | PERMIT        | PERMIT_SCOPED  | PERMIT_SCOPED  | DENY           | DENY                |
| Organization | read      | PERMIT        | PERMIT_SCOPED  | PERMIT_SCOPED  | DENY           | DENY                |
| Organization | create    | PERMIT        | DENY           | DENY           | DENY           | DENY                |
| Organization | update    | PERMIT        | DENY           | DENY           | DENY           | DENY                |
| Organization | delete    | PERMIT        | DENY           | DENY           | DENY           | DENY                |
| User         | list      | PERMIT        | PERMIT_SCOPED  | PERMIT_SCOPED  | DENY           | DENY                |
| User         | read      | PERMIT        | PERMIT_SCOPED  | PERMIT_SCOPED  | DENY           | DENY                |
| User         | create    | PERMIT        | PERMIT_SCOPED  | DENY           | DENY           | DENY                |
| User         | update    | PERMIT        | PERMIT_SCOPED  | DENY           | DENY           | DENY                |
| User         | delete    | PERMIT        | DENY           | DENY           | DENY           | DENY                |
| Project      | list      | PERMIT        | PERMIT_SCOPED  | PERMIT_SCOPED  | PERMIT_SCOPED  | DENY                |
| Project      | read      | PERMIT        | PERMIT_SCOPED  | PERMIT_SCOPED  | PERMIT_SCOPED  | DENY                |
| Project      | create    | PERMIT        | PERMIT_SCOPED  | DENY           | DENY           | DENY                |
| Project      | update    | PERMIT        | PERMIT_SCOPED  | DENY           | DENY           | DENY                |
| Project      | delete    | PERMIT        | PERMIT_SCOPED  | DENY           | DENY           | DENY                |
| Invoice      | list      | PERMIT        | PERMIT_SCOPED  | PERMIT_SCOPED  | PERMIT_SCOPED  | PERMIT_SCOPED       |
| Invoice      | read      | PERMIT        | PERMIT_SCOPED  | PERMIT_SCOPED  | PERMIT_SCOPED  | PERMIT_SCOPED       |
| Invoice      | create    | PERMIT        | DENY           | DENY           | DENY           | DENY                |
| Invoice      | update    | PERMIT        | PERMIT_SCOPED  | DENY           | DENY           | DENY                |
| Invoice      | delete    | PERMIT        | DENY           | DENY           | DENY           | DENY                |
| Membership   | list      | PERMIT        | PERMIT_SCOPED  | DENY           | DENY           | DENY                |
| Membership   | read      | PERMIT        | PERMIT_SCOPED  | DENY           | DENY           | DENY                |
| Membership   | create    | PERMIT        | DENY           | DENY           | DENY           | DENY                |
| Membership   | update    | PERMIT        | PERMIT_SCOPED  | DENY           | DENY           | DENY                |
| Membership   | delete    | PERMIT        | PERMIT_SCOPED  | DENY           | DENY           | DENY                |
```

`PERMIT_SCOPED` means the role has access but with a row-filter predicate applied at query time. The exact predicate for each cell is documented in `dsl/entities.dsl`. The reference matrix is committed at `expected/rbac-matrix.json` and gated by `tests/unit/test_acme_billing_reference_drift.py`.

---

### Compile the ISO 27001 compliance evidence

```bash
cd examples/acme_billing
dazzle compliance compile
```

Expected output:

```
Compliance: ISO/IEC 27001:2022
  Controls: 93
  Evidenced: 16
  Partial: 0
  Gaps: 21
  Excluded: 56
  Coverage: 17.2%

  Output: .dazzle/compliance/output/iso27001/auditspec.json
```

The compiled auditspec captures all DSL-derivable access-control evidence (permit rules, scope rules, audit declarations). The reference output is committed at `expected/compliance-auditspec.json` and gated by the drift test. Other subcommands: `dazzle compliance evidence` (raw DSL evidence), `dazzle compliance gaps` (partial + missing controls).

---

### Run the adversarial RBAC suite

The test suite requires a PostgreSQL database. It boots the app in-process against a disposable schema.

```bash
export TEST_DATABASE_URL="postgresql+asyncpg://user:pass@localhost/test_db"
pytest tests/integration/test_acme_billing_rbac.py -v -m "e2e and postgres"
```

The 8 tests cover:

| Test | What it probes |
|------|---------------|
| `test_idor_foreign_org_invoice_returns_404` | IDOR: an org_owner requesting a different org's invoice by UUID must receive 404, not 200 |
| `test_cross_tenant_list_isolation` | List endpoint for a scoped role must return only the caller's own-org records, never another tenant's |
| `test_sensitive_invoice_denied_to_contractor` | `external_contractor` must receive 403/404 on an invoice where `sensitive = true` |
| `test_bulk_action_denied_for_unpermitted_role` | A bulk-action call on an entity the role has no write permit for must be rejected |
| `test_auditor_is_read_only` | `auditor` write attempts (create/update/delete) must all return 403 |
| `test_project_member_sees_only_assigned_projects` | `project_member` list returns only projects where a Membership row exists for `current_user` |
| `test_admin_has_cross_org_access` | Positive control: `admin` can read records from any tenant |
| `test_denied_access_emits_audit_record` | A rejected request must still produce an audit trail entry |

Without `TEST_DATABASE_URL` set the suite is skipped (`pytest.mark.postgres` guard).

---

### Run the app

```bash
cd examples/acme_billing
dazzle serve         # with Docker
dazzle serve # without Docker
```

- UI: http://localhost:3000
- API docs: http://localhost:8000/docs

---

## What each scope rule demonstrates

The table below maps each entity's `scope:` rules to the predicate algebra form they exercise. Read `dsl/entities.dsl` for the authoritative source.

| Entity | Role(s) | Scope rule | Predicate form |
|--------|---------|------------|----------------|
| Organization | `admin` | `all` | Unrestricted — no WHERE clause added |
| Organization | `org_owner`, `auditor` | `id = current_user.org` | **Direct equality** — `current_user.org` is the caller's org UUID, matched against the PK of the row |
| User | `admin` | `all` | Unrestricted |
| User | `org_owner`, `auditor` | `org = current_user.org` | **FK-column equality** — filters on a direct FK column rather than the PK of the entity itself |
| Project | `admin` | `all` | Unrestricted |
| Project | `org_owner`, `auditor` | `org = current_user.org` | FK-column equality |
| Project | `project_member` | `via Membership(user = current_user, project = id)` | **EXISTS via junction** — compiles to an `EXISTS (SELECT 1 FROM membership WHERE user = :uid AND project = project.id)` subquery |
| Invoice | `admin` | `all` | Unrestricted |
| Invoice | `org_owner`, `auditor` | `project.org = current_user.org` | **FK-path depth-2** — two-hop join: Invoice → Project → Organization, compared to `current_user.org` |
| Invoice | `project_member`, `external_contractor` | `project.org = current_user.org and sensitive != true` | **Boolean AND with not-equals** — the FK-path predicate combined with a column inequality. Note: `!=` is used here rather than `not (sensitive = true)` because the parser does not support standalone `not(...)` inside a compound predicate (#1181) |
| Membership | `admin` | `all` | Unrestricted |
| Membership | `org_owner` | `project.org = current_user.org` | FK-path depth-2 |

The `not (...)` standalone-negation form (e.g. `not (status = archived)`) is supported as a top-level scope rule but not yet inside a compound boolean predicate — tracked as #1181.

---

## Project structure

```
acme_billing/
├── dazzle.toml                        # Project configuration
├── README.md                          # This file
├── dsl/
│   ├── app.dsl                        # Module root
│   ├── entities.dsl                   # 5 entities with full scope rules
│   ├── personas.dsl                   # 5 persona definitions
│   ├── surfaces.dsl                   # CRUD surfaces for each entity
│   ├── stories.dsl                    # User stories
│   └── seeds/
│       └── demo_data/                 # 2-tenant JSONL seed fixtures
├── expected/
│   ├── rbac-matrix.json               # Committed RBAC matrix baseline
│   └── compliance-auditspec.json      # Committed compliance audit baseline
└── tests/
    └── integration/
        └── test_acme_billing_rbac.py  # 8 adversarial RBAC tests
```

---

*Part of the DAZZLE examples collection. See `examples/` for the full set.*
