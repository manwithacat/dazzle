---
id: domain_coupled_keywords
name: Domain-coupled DSL keywords and field names
layer: inference
status: active
summary: >-
  When proposing a new DSL keyword (region primitive, scope verb, lifecycle
  construct) or a new field on an entity, default to domain-neutral names on
  both surfaces. Domain values live at the *adapter* layer, not in the
  grammar. Domain-coupled keywords drag the corpus's domain assumptions into
  the framework and fragment the substrate.
triggers_text:
  - "pupil_card"
  - "class_strip"
  - "customer_id"
  - "patient_id"
  - "ticket_id"
  - "pupil"
  - "student"
  - "domain-specific name"
  - "matches the spec terminology"
triggers_code:
  - '\bcustomer_id\s*:'
  - '\bpupil_id\s*:'
  - '\bpatient_id\s*:'
  - '\bticket_id\s*:'
refs:
  adrs:
    - ADR-0004
  tests: []
---

# Domain-coupled DSL keywords and field names

## The corpus prior

LLM training data is full of domain-specific DSLs and ORMs. Every Rails or Django tutorial introducing models uses domain-evocative names: `Customer`, `Order`, `Patient`, `Ticket`, `Pupil`, `Student`. Region primitives in dashboards-as-code tutorials carry domain names: `customer_card`, `patient_summary`, `ticket_strip`. The corpus equates "evocative naming = good code."

When the LLM authors a new Dazzle keyword from a spec that uses `pupil`, the prior wants to name it `pupil_card`. When the spec talks about `class_strip` (in a school-management context), the prior wants to ship `class_strip` as the framework keyword. Both pull domain assumptions into the substrate.

## Wrong shape

```dsl
region pupil_card:
  uses entity Pupil
  field pupil_id "ID"
  field pupil_name "Name"
  field current_class "Class"
```

What this gives up: the primitive now only meaningfully serves school applications. A different domain (healthcare patient summary, ticket triage view, sales account card) cannot reuse this region without either (a) creating a parallel `patient_card` / `ticket_card` / `account_card`, fragmenting the keyword space, or (b) using a name that misrepresents what the data is. The framework's value depends on the DSL staying small enough to hold in context, and every domain-coupled keyword is a step toward fragmentation.

## Right shape

Two-step interrogation, applied before naming any new keyword *or* field:

1. **Strip the domain.** Write one sentence describing the *shape* without any domain terminology. "Horizontal scrollable row of avatared entities with a lens toggle to swap the primary metric" — that's a `cohort_strip`, not a `class_strip`. "Compact card with an identity halo, status flags, and a quick-actions row" — that's an `item_card`, not a `pupil_card`. If the candidate keyword doesn't survive the strip-the-domain test, it's coupled.
2. **Generic-name the fields.** `member_id` for cohort members, `record_id` / `item_id` / `subject_id` for generic references, or literal `id`. Mode names, sub-construct names, and section labels can usually stay generic from the start (`halo`, `flags`, `mini_bars`, `stamps`, `thread_summary`, `quick_actions` are all fine).

Domain values express themselves at the **adapter layer**, where the generic primitive binds to a domain entity:

```dsl
region cohort_strip:
  uses entity Pupil          # adapter: domain entity is Pupil
  member_via: "student_profile"  # adapter: domain accessor
  scope_param: "pupil_id"        # adapter: domain identifier
```

The same `cohort_strip` primitive then serves school cohorts, healthcare patient panels, sales account groups — domain mapping is data, not grammar.

## Why this matters here

Every domain-coupled DSL construct is a step toward fragmentation. The framework's whole value depends on the DSL staying small enough to hold in context: when the keyword count grows linearly with the number of domains Dazzle has been used in, the agent-ergonomics argument collapses. The Anti-Turing Constraint and Convergence Hypothesis in `ROADMAP.md` both rest on this — the DSL is a small, finite, domain-neutral grammar; domains express themselves via adapters and surfaces, not via new keywords.

The pattern has been caught twice in real shipping cycles (#1015–#1018 region-primitive work): both `pupil_card` and `class_strip` shipped initially because the source spec used those names, and both required immediate renames once the user surfaced the framing. The lesson cost two extra release cycles to learn; this counter-prior is the inoculation so the next domain-coupled name proposal gets caught at design time, not ship time.

## Cross-references

- ADR-0004 (DSL is agent-first; precision and formal correctness over ergonomics) — the foundational decision this counter-prior protects.
- ROADMAP.md — "The Anti-Turing Constraint" and "The Convergence Hypothesis" sections frame why DSL size matters.
- #1015–#1018 — the region-primitive ship cycles where the pattern was first caught.
