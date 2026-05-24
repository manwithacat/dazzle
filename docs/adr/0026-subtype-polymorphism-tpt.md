# ADR-0026 — Subtype Polymorphism: TPT, Flat, Immutable

**Status:** Accepted (v0.71.180)
**Issue:** #1217 — Phase 3(e)
**Spec:** `dev_docs/2026-05-24-1217-phase3e-subtype-polymorphism-design.md`

## Decision

The `subtype_of:` construct uses **table-per-type (TPT) storage** with:
1. A shared-PK FK from each child table to the base.
2. An auto-synthesised `kind` enum column on the base (linker-derived; reserved field name).
3. A `BEFORE INSERT/UPDATE` trigger on each child enforcing cross-row consistency.

The hierarchy is **flat** (no multi-level), and `kind` is **immutable** post-create
(no Vehicle → Building mutation; users must DELETE + INSERT, losing the id).

## Rejected alternatives

- **STI (single-table inheritance):** doubling storage strategies doubles the
  cognitive surface; the escape-hatch framing argues for one well-defined choice.
- **TPC (concrete-only / table-per-concrete-class):** polymorphic queries don't
  work (no shared base table to JOIN).
- **Multi-level inheritance:** explicit deferral; the IR field
  (`subtype_of: str | None`) leaves the door open for a future revisit, but v1
  rejects `A subtype_of B subtype_of C` at linker time.

## Framing

**Subtype polymorphism is a complex, potentially brittle data structure.**
Cross-table joins for subtype queries, surface variance via `subtype_panel:`,
RBAC composition across base + child, additional grants per subtype, immutable
discriminator, cascade-DELETE semantics — each of these is correct-by-design
but adds a real surface area to reason about, both at authoring time and during
refactor. **Dazzle supports the construct and tests it rigorously** (see
`fixtures/asset_registry/` and `tests/unit/test_asset_registry_fixture.py` for
the canonical worked example, pinned by three regression tests). It is **not the
first tool in the toolbox to reach for**.

Agent guidance must require a **clear business requirement** to justify
`subtype_of:`. The inference KB (`subtype_of_only_for_true_isa`) and the
validator (`W_LOOKS_POLYMORPHIC` updated message, `W_SUBTYPE_OF_OVERREACH` new
warning) both steer authors toward alternatives first:

1. Separate entities with no shared base — when Vehicle and Building never need
   to be queried together as a single list, model them as independent entities.
2. State machine + variant fields — when the variants represent behaviour over
   time, use enum states + lifecycle, not subtypes.
3. Nullable subtype fields on a single entity — when variants share most fields
   and the differences are 2–3 nullable columns.
4. `has_many` / `via:` — when the variant data is genuinely a separate concept.

Only reach for `subtype_of:` when an agent can articulate *all three* of these
conditions holding: true IS-A (Vehicle IS an Asset, not Vehicle HAS an Asset);
subtype-specific NOT NULL fields needed at the schema level; polymorphic
queries genuinely needed ("show me all assets, mixed kinds"). Absent that
business pressure, model flat.

## Consequences

- Cross-table joins required for subtype-specific queries (acceptable cost when
  the IS-A relationship is genuine).
- Surface variance handled via `subtype_panel:` on card/detail surfaces (not
  list/table — heterogeneous per-row columns in tables are deliberately out of
  scope for v1).
- RBAC composition is intersection — child can be more restrictive, never less.
- `soft_delete:` must be on the base (child redeclaration is rejected with
  `E_SUBTYPE_SOFT_DELETE_ON_CHILD` — a child-only tombstone would be invisible
  to polymorphic-base queries through the JOIN).
- `grant_schema` permissions emitted per entity; grant on child requires grant
  on base.
- `kind` is a reserved field name on any entity that has subtypes.
- No multi-level inheritance, no subtype mutation in v1.

## References

- Issue #1217 — Phase 1 audit comment (Pattern 8)
- Spec: `dev_docs/2026-05-24-1217-phase3e-subtype-polymorphism-design.md`
- Plan: `dev_docs/2026-05-24-1217-phase3e-subtype-polymorphism-plan.md`
- ADR-0024 — no regex in parser (honoured in slice 3e.i parser additions)
- ADR-0017 — schema migrations via Alembic (honoured in slice 3e.iii DDL)
