# Stem: Multi-entity field beta hub with persona-scoped job desks

## Claim

Advanced **multi-entity domain** for hardware field testing: personas, access
rules, and **role-shaped workspaces** — not a single CRUD dashboard.

## Reconstruct

- engineer → `engineering_dashboard` (+ `issue_triage`, `firmware_pipeline`)
- manager → `manager_ops` (fleet KPIs first; also triage/firmware access)
- tester → `tester_dashboard` (+ `field_kit` for road devices/sessions)
- Prefer explicit persona scoping and access rules in DSL.
- Keep entity graph coherent; new features attach to existing domain stems.

## Not this

- Flattening all personas to one admin for convenience.
- Every product persona defaults to the same mega-workspace.
- Landing on bare entity lists when the job is triage, fleet health, or field kit.

## Expressions

- `dsl/`, README, SPEC
- Framework: `stems/dsl-first.md`, `stems/rbac-and-scope.md`
- Product maturity: `scripts/example_product_maturity.py`
