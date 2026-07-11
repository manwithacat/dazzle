# Stem: RBAC and scope

## Claim

**Permit** (what action is allowed) and **scope** (which rows are visible) are
separate concerns. Predicate algebra and persona binding are first-class in the
IR, not ad-hoc checks in handlers.

## Reconstruct

- Don’t collapse “auth” into a single boolean.
- Scope type-checks against the FK graph at validate time where possible.
- Runtime re-validates; client ids are never the sole authority.

## Not this

- UI-only filtering as security.
- Mixing permit matrix with row scope in one opaque policy bag.

## Expressions

- ADR-0007, ADR-0009, ADR-0010
- `src/dazzle/rbac/`, scope compilation in core
