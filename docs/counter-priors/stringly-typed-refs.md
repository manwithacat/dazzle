---
id: stringly_typed_refs
name: Stringly-typed cross-entity references
layer: grammar
status: active
summary: >-
  `customer_email: str` or `user_name: str` used as a reference to another
  entity. The corpus reflex copies a display value instead of declaring a
  typed `ref`; the runtime then can't auto-include, FK-enforce, or traverse
  scope predicates through the relationship. Always use `ref Entity`.
triggers_text:
  - "customer_email as field"
  - "user_name as field"
  - "string reference"
  - "denormalized"
  - "copy of name"
  - "store the email"
  - "denormalised name"
triggers_code:
  - '\b(customer|user|patient|tenant)_email\s*:\s*str'
  - '\b(customer|user|patient|tenant)_name\s*:\s*str'
  - '\bowner_email\s*:\s*str'
refs:
  adrs: []
  kb_patterns:
    - no_stringly_refs
  tests: []
---

# Stringly-typed cross-entity references

## The corpus prior

Denormalisation tutorials and "performance optimisation" Stack Overflow answers routinely show copying a display value (`customer_email`, `user_name`, `school_name`) into a child entity as a "performance" or "search convenience" measure. The corpus is full of examples where what looks like denormalisation is actually a missing relationship: the child holds a string copy of a value that lives on a parent row.

LLMs reach for this when a spec says "show the customer's email next to the order" — the reflex is to put `customer_email` on the Order, instead of declaring `customer: ref Customer` and letting the email come through the relation.

## Wrong shape

```dsl
entity Order "Order":
  id: uuid pk
  customer_email: str(200) required       # string copy
  assigned_user_name: str(100)            # string copy
  shipping_postcode: str(20)              # string copy

entity StudentProfile "Student":
  school_name: str(200)                   # string copy
  ...
```

What this gives up:

- **No FK** — the database cannot enforce that `customer_email` matches a real Customer row. Typos, stale copies, and orphan rows are silent.
- **Stale data** — when the Customer changes their email, every Order row referencing the old value is now wrong. The application is responsible for cascading the update; nothing else will.
- **No traversal in scope rules** — `scope: customer.school = current_user.school` can't compile, because there's no `customer` relationship to traverse. Scope rules collapse to flat field equality, losing the predicate algebra (ADR-0009).
- **No auto-include** — surfaces that want "show the customer's name" have to remember which string field is the cached copy and which is the real source. Inconsistencies accrete.

## Right shape

```dsl
entity Order "Order":
  id: uuid pk
  customer: ref Customer required
  assigned_to: ref User
  shipping_address: ref Address

entity StudentProfile "Student":
  school: ref School required
  # school.name is auto-included in API responses and resolved in
  # rendered surfaces via the ref.
```

The ref carries the relationship; display values are resolved at read time. The Repository auto-includes referenced rows, the predicate algebra can traverse the FK, and the FK constraint catches orphans at write time.

When you *legitimately* need a denormalised string (rare): it's a calculated field with an explicit refresh mechanism (an event handler, a scheduled job), not an ad-hoc copy. Reach for it only when the read pattern genuinely cannot tolerate the join cost — which is essentially never at Dazzle's scale.

## Why this matters here

Dazzle's scope predicate algebra is the load-bearing reason `ref` is required for cross-entity relationships. Scope rules compile against the FK graph; the graph is built from `ref` declarations. A string copy doesn't show up in the graph, so any rule that wants to traverse it can't be compiled, and the substrate's row-level-security guarantee silently collapses for that surface.

The corpus shape is a relic of pre-ORM-mature thinking. Modern relational databases handle the join cost trivially for the read patterns that Dazzle applications generate; the "performance" justification doesn't apply at this scale and never did at most scales it was invoked.

## Cross-references

- ADR-0009 (predicate algebra) — depends on the FK graph being complete.
- Inference KB `no_stringly_refs` — bootstrap auto-surfacing.
- `docs/reference/grammar.md` — `ref` syntax.
