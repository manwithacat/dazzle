# Stem: Multi-tenant billing is the adversarial RBAC / scope-algebra proving ground

## Claim

This example exists to stress **scope predicates and multi-tenant isolation** across personas. Billing domain is real enough to attack; the stem is security judgement, not a full ERP product.

## Reconstruct

- Prefer DSL scopes + personas over handler-only checks.
- Adversarial tests (IDOR, cross-tenant leaks) are part of the stem — do not 'simplify' them away.
- Predicate forms (equality, FK path, EXISTS, AND) are intentional coverage.

## Not this

- Treating scopes as UI filters only.
- Collapsing tenants into a single admin persona for convenience.

## Expressions

- `dsl/`, README, `tests/integration/test_acme_billing_rbac.py`
- Framework: `stems/rbac-and-scope.md`
