# Stem: Verified email domain self-service join under per-tenant policy

## Claim

Kayfabe app for **verified-domain join** (#1424): prove domain ownership, match work email, policy-gated self-join and admin approval.

## Reconstruct

- Model policy and verification in DSL/process, not only UI copy.
- Tenant isolation and verified email are load-bearing.

## Not this

- Skipping verification steps as 'demo shortcuts' in the stem.

## Expressions

- `dsl/`, README, SPECIFICATION
- Framework: `stems/rbac-and-scope.md`, `stems/dsl-first.md`
