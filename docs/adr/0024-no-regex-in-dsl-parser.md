# ADR-0024: No Regex Parsing in the DSL — Regex is a Grammar Smell

**Status:** Accepted
**Date:** 2026-05-19

## Context

The DSL parser is line-and-token oriented. Most constructs (`entity`,
`surface`, `workspace`, `scope:`, `process`, `event_model`, `view`,
`integration` …) are parsed by reading tokens off a buffer and dispatching
on keywords — a recursive-descent style that produces typed IR directly.

A handful of places, however, accept a free-form **string field** that is
parsed at runtime via regex. The longest-lived example is `_AGGREGATE_RE`
in `back/runtime/workspace_aggregation.py:40`:

```python
_AGGREGATE_RE = re.compile(r"\s*(count|sum|avg|min|max)\s*\(\s*(\w+)\s*(?:where\s+(.+?))?\s*\)")
```

It powers `count(Entity)`, `avg(field)`, `sum(field where pred)` across
five IR sites (`WorkspaceRegion.aggregates`, `OverlaySeriesSpec`,
`PipelineStageSpec.value`/`.progress`, `ActionCardSpec.count_aggregate`,
`LensAggregatePrimary.aggregate`). Other examples have appeared and been
fixed: `_parse_simple_where` (since superseded by the predicate parser),
ad-hoc bucket-label regex, current-bucket sentinel substitution.

In every case the regex started as a small expedient. In every case it
accreted disambiguation hacks ("`count(X)` → entity; `avg(X)` → column"),
silently rejected new shapes ("`avg(Entity.column)` is unrepresentable"),
and blocked downstream tooling (linter, doc-gen, IDE completion) because
the contents of the string were invisible to the IR.

Issue #1144 Gap 1 phase 2 surfaced the cost concretely: a cross-entity
aggregate (`avg(MarkingResult.score)`) cannot be expressed because the
regex has no slot for it. Extending the regex is a one-line change. But
extending the regex *again* — and adding the matching disambiguation
branch — entrenches the smell.

## Decision

**The DSL parser does not use regex to parse DSL constructs or
expressions.** When a piece of DSL needs to be parsed, parse it
structurally — produce typed IR — using the same token-driven dispatcher
the rest of the language uses.

Specifically:

1. **No regex for grammar.** Regex is reserved for character-class
   recognition (whitespace, identifier shape, numeric literal shape) and
   for non-DSL inputs (log line scraping, file globs, etc.). Recognising
   a DSL keyword or shape via regex is grammar work in disguise.
2. **No string fields whose contents are later parsed at runtime.** If a
   construct accepts user-authored DSL (an aggregate call, a predicate, a
   path expression), the parser MUST produce typed IR for it at parse
   time, validated against the IR schema. Stashing the source string for
   "later" defers parsing into the runtime — where errors surface as
   500s instead of `dazzle validate` failures and where tooling cannot
   inspect the construct.
3. **A regex in the parser is a signal to extend the grammar.** When the
   temptation arises, the right next step is to add an IR type and a
   dispatcher method, not a `re.compile`. The regex is the symptom; the
   missing grammar is the cause.

This applies to new constructs and, on a rolling basis, to existing ones:
when a regex-parsed construct grows a new shape or a disambiguation hack
is needed, that change MUST be implemented by retiring the regex in
favour of typed IR — not by extending the regex.

## Consequences

### Positive

- **Errors surface earlier.** Parse-time errors at `dazzle validate`
  instead of runtime regex misses.
- **Tooling sees the structure.** Linter, IDE completion, doc-gen,
  composition audits all read typed IR. They can't read inside a string.
- **No disambiguation hacks.** When a shape's meaning depends on the
  parser context (entity vs column, literal vs aggregate), the IR
  encodes the distinction in named fields rather than a func-switch.
- **Extension has a home.** New shapes get an IR field. The grammar
  grows in one place, not across `re.compile` calls in multiple modules.
- **Compiles to alternative targets.** Typed IR can be compiled to SQL,
  to MCP tool schemas, to OpenAPI examples, etc. Strings can't.

### Negative

- **Migration cost.** Five sites carry regex-parsed strings today
  (`_AGGREGATE_RE` consumers). Each migration is a clean-break diff per
  ADR-0003 — IR change + parser change + runtime change + tests + example
  apps in one commit. See `dev_docs/2026-05-19-aggregate-ref-ir-brainstorm.md`
  for the aggregate-specific sequencing.
- **Parser surface grows.** Recursive-descent parsing of small
  sub-grammars is more code than a regex. The tradeoff is paid back in
  validation, tooling, and the lack of disambiguation hacks.
- **A judgement call remains.** Character-class regex (e.g. "is this an
  identifier?") is still allowed; "is this a `count(X)` call?" is not.
  The line is: matches a *lexical shape* (OK) vs matches a *grammar
  shape* (not OK).

### Neutral

- The DSL surface syntax does not change. Users continue to write
  terse, familiar forms (`count(Task where status=open)`). What changes
  is how the parser handles them — structurally, not via regex.

## Alternatives Considered

### 1. Extend the regex on demand

Each time a new shape is needed, add a capture group and a downstream
branch. This is what was almost done for #1144 Gap 1 phase 2 (extend
`_AGGREGATE_RE` to `(\w+)(?:\.(\w+))?`).

**Rejected:** The regex was already encoding two distinct grammars via
`func`-disambiguation. Each extension worsens the smell and pushes the
fix-cost forward. The disambiguation hack is the kind of subtle bug
producer ADR-0009 was written to eliminate for predicates.

### 2. Allow regex for "small, contained" sub-grammars

Permit regex for parsing tiny string fields with clear shape (e.g.
`"yyyy-mm-dd"` date literals, the `count(X)` shape).

**Rejected:** No regex starts large. The `_AGGREGATE_RE` example began
as "just `count(X)`" and grew into a five-consumer load-bearing
disambiguation hub over four releases. The rule has to be sharp or it
won't bind.

### 3. Defer parsing to runtime universally

Keep DSL fields as strings, parse on each request when needed.

**Rejected:** Defers errors from `dazzle validate` (where they're
caught pre-deployment) to runtime (where they're 500s). Contradicts
ADR-0006's frozen-IR guarantee and ADR-0009's link-time validation
posture.

## Implementation

- This ADR is normative for new constructs from 2026-05-19.
- Existing regex-parsed constructs are migrated as they evolve.
  Current backlog of regex-encoded grammar slots:
  - `_AGGREGATE_RE` consumers (5 IR sites). Migration drafted in
    `dev_docs/2026-05-19-aggregate-ref-ir-brainstorm.md`.
  - `parse_aggregate_where` (`back/runtime/aggregate_where_parser.py`)
    — already a structured parser, but lives in `back/` and duplicates
    the main predicate parser. Folding it in is the second slice of
    the aggregate migration.
- Linter check: `tests/unit/test_no_regex_in_parser.py` greps
  `src/dazzle/core/dsl_parser_impl/` for `re.compile` and `re.match` and
  fails on hits outside an explicit allowlist (lexical-shape regex). This
  is the enforcement gate.

## Related

- [ADR-0003](0003-clean-breaks.md) — Migrations are clean breaks, no
  compatibility shims. Migrations under this ADR follow the same rule.
- [ADR-0006](0006-frozen-ir.md) — Typed IR is the source of truth.
  Stashed strings violate that posture.
- [ADR-0009](0009-predicate-algebra.md) — Same shape of argument for
  scope predicates: formal IR with link-time validation, not ad-hoc
  pattern matching.
- [ADR-0023](0023-template-emission-patterns.md) — Similar shape of
  argument for HTML output: pick the right mechanism per intent, don't
  paper-over with a string concat.
