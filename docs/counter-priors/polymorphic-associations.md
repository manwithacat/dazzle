---
id: polymorphic_associations
name: Polymorphic database associations
layer: grammar
status: active
summary: >-
  Rails-style `belongs_to :commentable, polymorphic: true` and Django-style
  hand-rolled `(subject_type, subject_id)` discriminator pairs are closed by
  construction. No `ref X | Y | Z` union sugar, ever (ADR-0027). The one
  sanctioned escape is the typed `poly_ref name [T1, T2]` construct + the
  `name[Type].path` scope selector (ADR-0042) — use it ONLY when the
  four-question interrogation genuinely fails (≈5% of proposals).
triggers_text:
  - "polymorphic"
  - "commentable"
  - "attachable"
  - "taggable"
  - "subject_type and subject_id"
  - "owner_type"
  - "item_type"
  - "can belong to X or Y"
  - "reference any entity"
  - "single audit log across types"
  - "morphic"
  - "notification target"
triggers_code:
  - 'subject_type\s*:\s*enum'
  - 'item_type\s*:\s*enum'
  - 'owner_type\s*:\s*enum'
  - 'polymorphic_ref\s*:'
refs:
  adrs:
    - ADR-0026
    - ADR-0027
  memories:
    - feedback_polymorphic_association_antipattern
  kb_patterns:
    - no_polymorphic_keys
  tests:
    - tests/unit/test_propose_patterns_1249.py
---

# Polymorphic database associations

## The corpus prior

The training corpus is dominated by Rails (and Rails-flavoured Django/Laravel/etc.) tutorials that demonstrate the polymorphic-association pattern as the canonical answer to "one model that points at many kinds of other models." Comments on posts or articles or photos. Attachments on tickets or projects or invoices. Tags on anything. Audit-log entries pointing at the changed row.

The pattern looks like: a discriminator column (`commentable_type: "Post"`) plus an id column (`commentable_id: 42`), and at runtime the application resolves the pair to a row in the named table. In Rails, the syntax sugar `belongs_to :commentable, polymorphic: true` makes it feel built-in.

The LLM reaches for it reflexively because it appears in roughly every Rails tutorial, half of all "audit log" examples, and most Stack Overflow answers about generic comments/attachments/tags.

## Wrong shape

```dsl
entity Comment "Comment":
  id: uuid pk
  subject_type: enum[manuscript, assessment, school]  # discriminator
  subject_id: uuid                                     # untyped reference
  body: text
```

```ruby
# Rails equivalent — the canonical corpus pattern
class Comment < ApplicationRecord
  belongs_to :commentable, polymorphic: true
end
```

What this gives up:

- **Referential integrity** — `subject_id` is just a UUID; the database cannot enforce that a `subject_type = "manuscript"` row actually has a matching manuscript. Orphan rows are silent.
- **Scope composition** — Dazzle's `scope:` predicates compile to SQL against a known FK graph. A polymorphic ref has no FK, so cross-entity scope rules (e.g. "you can see comments on manuscripts in your school") cannot be statically checked, only laboriously runtime-asserted per subject type.
- **Query joins** — every read needs an N-way dispatch. Eager loading is brittle. Indexing is fragmented (one composite `(subject_type, subject_id)` index serves all targets badly).
- **Schema evolution** — adding a new subject type touches every reader; removing one leaves dead data with no FK to clean it up.

## Right shape

Walk the four-question interrogation (the canonical Dazzle routing for any
proposed polymorphic-shaped relationship):

1. **Do all subjects share the same lifecycle?** If yes → one entity with `subtype_of:` (TPT, ADR-0026), discriminator immutable, polymorphic queries via SQL UNION ALL. Only when the three TPT conditions hold (true IS-A, subtype-specific NOT NULL fields, polymorphic queries genuinely needed).
2. **Is the relationship N:M per pair?** → one junction entity per (parent, child) pair. `ManuscriptComment`, `AssessmentComment`. Boring, scope-composable, FK-enforced.
3. **Is the parent really a stream of typed events?** → an event-log entity with a `kind:` discriminator and per-kind payload entities. Notifications, audit logs, activity feeds collapse into this almost every time.
4. **Are there N≤4 candidate targets and exactly one is non-null per row?** → N nullable refs + a check constraint that exactly one is set. Mutex refs. Verbose but referentially honest.

If none of the four fit, the design is wrong, not the modelling. Re-state the requirement; the polymorphic shape is downstream of a confused requirement ~95% of the time.

## Why this matters here

Dazzle compiles scope rules to a formal predicate algebra (ADR-0009) validated against the FK graph at link time. A polymorphic ref has no FK, so scope predicates that traverse it cannot be statically verified — the whole row-level-security guarantee collapses for those entities. Closing the keyword by construction (ADR-0027) keeps the FK-graph-validation invariant total: every reference Dazzle knows about points at exactly one known table.

The pattern is also a tell. When an LLM proposes a polymorphic ref, the proximate cause is usually a feature framed too vaguely ("a comment system") that wants four-question decomposition. Catching the proposal early surfaces the framing problem at design time, when it's cheap, rather than at scope-composition time, when it's load-bearing.

## Cross-references

- ADR-0026 (subtype polymorphism TPT) — the legitimate IS-A escape hatch.
- ADR-0027 (no `polymorphic_ref:`, now or planned) — the formal closure.
- ADR-0042 (`poly_ref` scoping) — the realized escape hatch: the typed, statically-validated, scope-composable construct for the ≈5% of cases that survive the interrogation. Verify any poly scope with `dazzle db explain-scope <Entity> <verb>`.
- Inference KB entry `no_polymorphic_keys` — bootstrap auto-surfacing via `spec_analyze.propose_patterns` (#1249).
- `tests/unit/test_propose_patterns_1249.py` — pins the four-question routing for the canonical use cases (comments / attachments / tags / audit log / notifications / likes).
