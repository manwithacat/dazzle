# tenant_hierarchy — worked example: tenant hierarchy + membership

A framework-validation fixture (not a user-facing app) exercising the full
tenant-hierarchy + declarative-membership authoring pattern from **ADR-0036**
(tenant hierarchy data model) and **ADR-0037** (declarative membership relation).
See the capstone "Tenancy authoring pattern" in `CHANGELOG.md`.

## What it declares (`dsl/domain.dsl`)

A three-level tenant tree, each level resolved by host (`tenant_host:`) and
linked by `parent:` (the `ref` FK to the parent kind):

```
Region        (root: RLS partition + hierarchy root; declares `membership:`)
  └─ Trust    (parent: region)
       └─ School   (parent: trust)
```

…plus a tenant-scoped data entity **Report** (`school: ref School`) with a single
`read: school = current_tenant` scope.

## What it demonstrates

- **`tenant_host: parent:`** linking tenant kinds into a hierarchy (depth-3).
- **`membership:` on the root kind only** (Region) — one membership per identity
  at the root; descendant-host reachability is derived (no per-leaf rows).
- **Hierarchy-aware `current_tenant`**: the Report `read` scope auto-expands to a
  self-or-ancestor disjunction —
  `school = current_tenant OR school.trust = current_tenant OR school.trust.region = current_tenant`
  — so it renders **single** at a School host, **aggregate** at a Trust or Region
  host, and denies (fail-closed) otherwise.
- **Read-only aggregate**: the `update` scope keeps the single leaf check, so an
  ancestor (aggregate) host can read across descendants but not write.

## How it's exercised

`tests/unit/test_tenant_hierarchy_fixture.py` builds the appspec, asserts it
validates clean, and asserts the Report scopes compile to the expected
disjunction (read) / single check (update). The cross-tenant *isolation* property
(single/aggregate/no-bleed/fail-closed) is proven against real Postgres in
`tests/integration/test_current_tenant_scope_pg.py`.

This fixture focuses on the host-hierarchy + `current_tenant` + membership layer;
RLS row-tenancy (`tenancy:` / `dazzle.tenant_id`) is exercised by `fixtures/tenant_rls`.
