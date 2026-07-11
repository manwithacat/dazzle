# Stem: Multi-tenant invoice approval/payment ops — keystone multi-role workflow pressure

## Claim

Keystone example: **shared_schema tenancy**, invoice state machine, maker-checker approvals, HLESS events, payment service. Built to surface framework friction under realistic ops load.

## Reconstruct

- Prefer process/state machine + approvals in DSL over free-form status strings.
- Tenant partition and role guards are non-negotiable.
- Log framework friction as issues; do not paper over with app-only hacks that hide product gaps.

## Not this

- Single-tenant simplification that drops the stem.
- Bypassing maker-checker in 'demo mode' as permanent design.

## Expressions

- `dsl/`, README, SPECIFICATION
- Framework: `stems/dsl-first.md`, `stems/rbac-and-scope.md`, `stems/hypermedia-ssr.md`
