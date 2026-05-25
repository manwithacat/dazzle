---
id: subtype_polymorphism_default
name: Subtype polymorphism as the default for variant modelling
layer: inference
status: active
summary: >-
  `subtype_of:` (TPT, ADR-0026) is supported but is the escape hatch, not the
  default. When the spec describes "several variants of X" the corpus reflex
  is inheritance / discriminated subtypes; Dazzle's reflex is composition,
  state machines, or nullable variant fields. Only reach for `subtype_of:`
  when all three conditions hold: true IS-A, subtype-specific NOT NULL fields,
  polymorphic queries genuinely needed.
triggers_text:
  - "subtype"
  - "subclass"
  - "is_a"
  - "type hierarchy"
  - "discriminator"
  - "kind column"
  - "single table inheritance"
  - "STI"
  - "table per type"
  - "TPT"
  - "vehicle is an asset"
  - "different kinds of"
  - "variants of"
triggers_code:
  - 'subtype_of\s*:'
  - 'kind\s*:\s*enum'
  - 'type\s*:\s*enum\['
refs:
  adrs:
    - ADR-0026
  kb_patterns:
    - subtype_polymorphism_escape_hatch
  tests:
    - tests/unit/test_propose_patterns_1249.py
---

# Subtype polymorphism as the default for variant modelling

## The corpus prior

OOP tutorials, Rails guides, Django model docs, and most "Effective X" books reach for inheritance / discriminated subtypes / `kind:` columns whenever a spec describes "several variants of X." Vehicles inherit from Assets. Cars and trucks inherit from Vehicles. Manuscripts and assessments are both Submissions with a `kind` column. The corpus is saturated with this shape.

The reflex is so strong that LLMs propose subtype hierarchies for cases where the variants share only superficial fields, where the variant set is closed and small, where the variants will never be queried polymorphically, or where the actual model is a state machine, a nullable optional field, or just two separate entities.

## Wrong shape

```dsl
entity Submission "Submission":
  id: uuid pk
  kind: enum[manuscript, assessment]
  title: str(200) required
  author: ref Person
  # Manuscripts have a manuscript_number; assessments have a grade.
  # Both fields are nullable because not every row carries them.
  manuscript_number: str optional
  grade: int optional
```

Or, with `subtype_of:` (legal in Dazzle but applied reflexively here):

```dsl
entity Submission "Submission":
  id: uuid pk
  kind: enum[manuscript, assessment]
  title: str(200) required
  author: ref Person

entity Manuscript "Manuscript":
  subtype_of: Submission
  manuscript_number: str required

entity Assessment "Assessment":
  subtype_of: Submission
  grade: int required
```

What this gives up: every read needs a subtype dispatch even when the caller only cares about manuscripts. Surface contracts get muddier — the "Submission list" surface either flattens the subtypes (losing precision) or branches per kind (losing ergonomics). RBAC composition gets harder because the role×entity matrix now has to reason about parents vs subtypes. And in the common case (no polymorphic queries) the entire hierarchy is paying complexity costs for zero modelling benefit.

## Right shape

Walk the alternatives first. Reach for `subtype_of:` only when these fail:

1. **Separate entities.** If `Manuscript` and `Assessment` will never be queried as "list all submissions" — and most real systems don't — they're two entities, not subtypes. Scope rules, RBAC, surfaces all work cleanly per-entity.
2. **State machine.** If the variants are *behavioural* (a Ticket is "open" or "closed" or "escalated"), it's a state machine on one entity, not subtypes. State machines compose with scope predicates; subtypes don't.
3. **Nullable variant fields.** If two variants share 90% of their fields and differ in 1–2, nullable optional fields on one entity is simpler and queries flat. Pay attention to the CHECK constraint — "exactly one of manuscript_number, grade is set" — which keeps the table honest.
4. **`subtype_of:` (TPT)** only when all three hold:
   - True IS-A (the subtypes share a meaningful identity *and* lifecycle, not just superficial fields).
   - Subtype-specific NOT NULL fields (you genuinely need columns that mean something for one subtype and nothing for the other).
   - Polymorphic queries genuinely needed (the system has a surface or process that reads across all subtypes regularly).

If you can't articulate why all three apply, the right answer is one of the alternatives.

## Why this matters here

Polymorphism is a real category of complexity: cross-table joins for the parent table, surface variance, RBAC composition across the hierarchy, query planner cost. The framework supports it (ADR-0026, immutable discriminator, TPT only) because there are cases where it's the right model. But adopting it reflexively pays those costs without earning them.

The "clear business requirement" bar is load-bearing: agents should be able to articulate *why* polymorphism is justified (true IS-A + subtype-specific NOT NULL + polymorphic queries needed) before reaching for it, not as a reflex from the corpus prior. The inference KB entry `subtype_polymorphism_escape_hatch` is the framing that should fire at proposal time; this counter-prior is its inference-time anchor.

## Cross-references

- ADR-0026 (subtype polymorphism via TPT) — the formal closure on *how* `subtype_of:` works when used.
- ADR-0027 (no polymorphic_ref) — the related closure on cross-table polymorphic references.
- Inference KB `subtype_polymorphism_escape_hatch` — bootstrap auto-surfacing.
- Example app `asset_registry` is in `fixtures/`, not `examples/` — a deliberate signal that `subtype_of:` is a coverage test, not a recommended pattern.
