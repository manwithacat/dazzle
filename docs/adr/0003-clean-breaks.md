# ADR-0003: Clean Breaks Over Backward Compatibility

**Status:** Accepted
**Date:** 2026-03-20

## Context

Dazzle is pre-1.0 software with a single primary user who is fully engaged with the development process. As the DSL, IR, and runtime APIs evolve, questions arise about how to handle interface changes:

- Should old function signatures be preserved with deprecation warnings?
- Should compatibility aliases re-export renamed symbols?
- Should new modules wrap old modules for gradual migration?

Standard open-source practice favours deprecation cycles to protect downstream users. However, that practice assumes:

1. Many users on varying release schedules
2. Maintainers without visibility into downstream usage
3. Time and attention cost of coordinating migrations

None of these apply here. The primary user reviews every significant change before it ships.

## Decision

**Backward compatibility is not a requirement before v1.0.**

The following rules apply:

- **Delete old functions** rather than keeping them alongside new ones
- **Rename freely** — symbols, modules, CLI flags, DSL keywords
- **Never create wrapper functions**, re-exports, or compatibility aliases
- **Update all callers** in the same commit as the breaking change
- **Communicate breaking changes** via `CHANGELOG.md` (`### Changed` / `### Removed`) and GitHub issue comments — that is sufficient notice

The test suite is the safety net. If all tests pass after a rename, the rename is complete.

## Consequences

### Positive

- Codebase stays clean — no `_deprecated`, `_v1`, or `_compat` symbols accumulating
- Refactors are atomic — the codebase is never in a half-migrated state
- Contributors read one canonical path, not two
- Evolution speed is unconstrained by compatibility obligations

### Negative

- Branches that diverge from main for more than a day may require manual reconciliation
- External tooling (IDE plugins, scripts) that call Dazzle APIs directly will break silently on upgrade — acceptable given the current user base

### Neutral

- CHANGELOG becomes the authoritative record of interface changes
- This policy is explicitly documented in `CLAUDE.md` so contributors don't introduce compatibility shims

## Alternatives Considered

### 1. Deprecation Warnings

Mark old symbols with `@deprecated` and remove them after one release cycle.

**Rejected:** Adds dead code to every release. The single primary user doesn't need a release cycle of warning — a CHANGELOG entry plus a GitHub comment is enough.

### 2. Gradual Migration

Keep old and new APIs in parallel, migrate callers over multiple commits.

**Rejected:** Leaves the codebase in an inconsistent state between commits. Increases cognitive load — contributors must learn which API is current.

### 3. Compatibility Layers

Add thin wrappers that forward old call sites to new implementations.

**Rejected:** Wrappers accumulate. They become permanent because removing them is itself a breaking change. They hide the true shape of the API.

## Implementation

This policy is enforced by convention, not tooling. Code review checks that no new `_compat`, `_v1`, or `_deprecated` symbols are introduced, and that breaking commits include a corresponding `CHANGELOG.md` entry.
