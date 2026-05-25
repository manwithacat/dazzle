---
id: duplicated_parent_fields
name: Duplicated parent fields on child entities
layer: inference
status: active
summary: >-
  Copying a parent's field onto a child alongside the `ref` to the parent —
  `school_name: str` on `StudentProfile` next to `school: ref School`. The
  corpus reflex is denormalisation-for-convenience; the runtime auto-includes
  ref data in API responses and the UI resolves display names through the
  relation, so the copy is redundant *and* lossy when the parent changes.
triggers_text:
  - "duplicated field"
  - "copy parent field"
  - "denormalized name"
  - "school_name on student"
  - "cache the name"
  - "store the name for display"
triggers_code:
  - '\w+\s*:\s*ref\s+\w+.*\n.*\w+_name\s*:\s*str'
  - '\w+\s*:\s*ref\s+\w+.*\n.*\w+_title\s*:\s*str'
refs:
  adrs: []
  kb_patterns:
    - no_duplicated_fields
  tests: []
---

# Duplicated parent fields on child entities

## The corpus prior

Denormalisation-for-display tutorials show the pattern of copying parent fields onto children so that "we don't have to JOIN every time we want to show the school name." The corpus is full of this — Stack Overflow answers, "performance" guides, and ORM "anti-N+1" advice routinely recommend caching display values on child rows.

The shape is closely related to stringly-typed-refs but distinct: this one has *both* the ref AND the copy. The intent is "use the ref for the relationship and the copy for display."

## Wrong shape

```dsl
entity StudentProfile "Student":
  id: uuid pk
  school: ref School required
  school_name: str(200)        # duplicates School.name
  ...
```

What this gives up: when the School changes its name, the `school_name` on every StudentProfile referencing it is now stale. The framework has no way to know that `school_name` is supposed to track `School.name` — it's just a string. Either the application has to cascade the rename (manual coordination across every soft-link the author has emitted), or the data slowly diverges.

Worse, the duplicate creates a question for every reader: which field is canonical? The display layer might use one and the analytics layer the other; over time the inconsistency surfaces as bug reports where "the school name on the profile doesn't match the school record."

## Right shape

```dsl
entity StudentProfile "Student":
  id: uuid pk
  school: ref School required
  # school.name is auto-included in API responses and resolved through
  # the relation in rendered surfaces. No string copy.
```

The Repository auto-includes referenced rows for list/detail/aggregate paths. The UI resolves display names through the ref. If the read pattern genuinely cannot tolerate the join (essentially never at Dazzle's scale), the legitimate shape is a computed field with an explicit refresh mechanism — not an ad-hoc string copy that nobody is tracking.

## Why this matters here

The "performance" justification for denormalisation is almost always a relic. Postgres handles the join cost trivially for the read patterns Dazzle applications generate; the read penalty for going through a ref is invisible compared to the cost of any one network hop. Meanwhile the staleness cost compounds: every time the parent changes, the cached copy is wrong somewhere.

The deeper substrate point: Dazzle's surfaces are generated from the IR, and the IR captures the ref. Surfaces *already* resolve display values through refs — the author's job is to declare the ref, not to pre-compute the display string. When an LLM proposes a duplicated field, the prior is that the author has to do the resolution themselves; the substrate already does it.

## Cross-references

- Inference KB `no_duplicated_fields` — bootstrap auto-surfacing.
- `docs/reference/grammar.md` — ref behaviour and auto-include semantics.
- See also: `stringly-typed-refs.md` for the related-but-distinct shape (string instead of ref entirely).
