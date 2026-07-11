# Stem: Clean breaks

## Claim

No backward-compatibility shims for the comfort of partial upgrades. When the
contract changes, **update all callers in the same change**. Agents can do this;
dead dual paths are a human-era habit.

## Reconstruct

- Prefer delete + fix over deprecated aliases that live forever.
- Version bumps and CHANGELOG record the break; code does not keep both worlds.

## Not this

- Endless `compat_` modules “just for one release.”
- Dual IR shapes with silent coercion.

## Expressions

- ADR-0003
- Bump/ship workflows that refuse half-migrated trees
