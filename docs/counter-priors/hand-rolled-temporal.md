---
id: hand_rolled_temporal
name: Hand-rolled effective-dated history
layer: grammar
status: active
summary: >-
  `start_date` + nullable `end_date` + per-surface `scope: end_date = null`
  + a custom as-of route handler is the corpus shape for effective-dated
  entities (employment, salary, lease, price, GDPR consent). Dazzle ships a
  `temporal:` keyword (#1223, v0.71.161) that wires auto-filtering, current-row
  uniqueness, `?as_of=` URL param, and `latest_one` traversal. Use the keyword.
triggers_text:
  - "effective date"
  - "history of"
  - "as of"
  - "as-of date"
  - "snapshot at date"
  - "time machine"
  - "career history"
  - "salary history"
  - "price history"
  - "lease term"
  - "employment history"
  - "manager change"
  - "slowly changing"
  - "SCD"
  - "interval table"
  - "current row"
  - "currently active"
triggers_code:
  - 'start_date\s*:\s*date.*\n.*end_date\s*:\s*date\s*(optional|nullable)?'
  - 'effective_from\s*:\s*date'
  - 'valid_from\s*:\s*date.*\n.*valid_to\s*:\s*date'
refs:
  adrs: []
  kb_patterns:
    - prefer_temporal_keyword
  tests: []
---

# Hand-rolled effective-dated history

## The corpus prior

Slowly-changing-dimension tutorials, ETL guides, and HR-database textbooks all teach the same shape: a row per time interval, with `start_date` (required) and `end_date` (nullable; NULL means "currently active"). Every read filters `end_date IS NULL` to get the current row. Every "as of" query writes a custom predicate. Every "at most one current row per person" invariant is enforced ad-hoc in the application or via a partial unique index the author has to remember.

The corpus pattern is correct in the database — partial unique indexes really are how you do this — but charging it to the author at every surface site repeats the discipline-required problem from soft-delete: forget once, and an inactive row leaks into a current-row view.

## Wrong shape

```dsl
entity Employment "Employment":
  id: uuid pk
  person: ref Person required
  role: ref Role required
  start_date: date required
  end_date: date optional          # NULL = active

surface current_roles "Current Roles":
  uses entity Employment
  mode: list
  scope: end_date = null           # remember every time

surface employment_history "History":
  uses entity Employment
  mode: list
  # Custom route handler to accept ?as_of=YYYY-MM-DD and rewrite the
  # predicate to (start_date <= as_of AND (end_date IS NULL OR end_date > as_of))
```

Plus: the "at most one current row per person" invariant is your problem. The "current_employment" relationship on Person is your problem (probably a custom query). The auto-include into Person responses is your problem.

## Right shape

```dsl
entity Employment "Employment":
  id: uuid pk
  person: ref Person required
  role: ref Role required
  start_date: date required
  end_date: date

  temporal:
    start_field: start_date
    end_field: end_date
    key_field: person

entity Person "Person":
  id: uuid pk
  legal_name: str(200) required
  current_employment: latest_one Employment via person
  # GET /api/person/<id> includes the resolved current Employment row.
```

What the keyword wires:

- Read paths auto-filter `end_date IS NULL` (or `>= today`) for the current row, per surface, without manual scope rules.
- `?as_of=YYYY-MM-DD` URL parameter on every list surface re-projects to that date automatically.
- DB-level partial unique index enforces "at most one active row per `key_field`" at the schema layer.
- `latest_one EntityName via fk_field` on a parent gives a typed current-row relationship that resolves at read time.

When to *not* reach for `temporal:`: if the lifecycle is a multi-state workflow (draft → submitted → approved → archived), that's a state machine, not interval data. `temporal:` is for entities whose rows represent open or closed time intervals — an Employment row is true from start to end, and the *current* row is determined by date, not by event.

## Why this matters here

Effective-dated history is everywhere in real systems — HR, finance, GDPR consent, regulatory rate tables, lease management, exchange rates. The corpus pattern treats each application as a fresh discovery, charging the author with re-implementing the predicates, the URL param, the uniqueness invariant, and the current-row resolver. The substrate consolidates all four into one keyword, so all four become declared properties rather than discipline-enforced procedures.

This is the third instance of the same shape pattern (alongside `soft_delete:` and `subtype_of:`): a category of entity has a well-known invariant set; the framework hosts the invariants as a keyword; the author declares intent rather than implementing the invariants by hand. Each keyword closes a corpus pattern that the LLM would otherwise re-emit per surface.

## Cross-references

- `temporal:` keyword reference — `docs/reference/grammar.md`.
- Inference KB `prefer_temporal_keyword` — bootstrap auto-surfacing.
- Released in v0.71.161 (#1223).
