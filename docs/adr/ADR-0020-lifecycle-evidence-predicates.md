# ADR-0020: Lifecycle Evidence Predicates

**Status:** Proposed
**Date:** 2026-04-13
**Context:** `docs/superpowers/specs/2026-04-13-agent-led-fitness-methodology-design.md`
**Deciders:** Dazzle team
**Blocks:** Fitness methodology v1 (progress_evaluator.py)

## Context

The Agent-Led Fitness Methodology (v2 spec, 2026-04-13) introduces a `progress_evaluator` subsystem that distinguishes **motion** (things happened) from **work** (progress through a meaningful lifecycle). The motivation is the "silent discard" failure class: an agent clicks buttons, the UI shows success, rows change in the DB, but the entity's lifecycle state never advances toward any terminal condition. Motion without work.

To implement motion-vs-work detection, the progress evaluator needs to answer three questions per entity:

1. **What states can this entity be in?** — known from existing enum declarations
2. **What is the valid transition order?** — partially known from existing `process` construct, but not canonicalized
3. **What data must be present to call a transition "valid progress"?** — NOT currently expressible in the DSL

Without question 3, the evaluator cannot distinguish a real transition (status change accompanied by the required supporting data) from a spurious one (status change with empty payload). A support agent clicking "Resolve" without a resolution note is *motion*; the same click WITH a resolution note is *work*.

The existing `process` DSL construct (see `src/dazzle/core/dsl_parser_impl/process.py`) supports named states and transitions but has no concept of **evidence predicates** — the data shape that must be present for a transition to count. Fitness needs this concept as a prerequisite.

## Decision

Extend the `process` DSL construct with two new optional fields:

1. **`evidence_predicate`** per transition — a boolean expression over the entity's fields that MUST evaluate to `true` for the transition to count as valid progress
2. **`progress_order`** on the state enum — an ordering relation on states so "forward" and "backward" are well-defined

### Syntax

```dsl
entity Ticket "Support Ticket":
  id: uuid pk
  status: enum[new, assigned, in_progress, resolved, closed] required
  assignee_id: ref User
  resolution_notes: text

process ticket_lifecycle:
  entity: Ticket
  status_field: status

  states:
    - new         (order: 0)
    - assigned    (order: 1)
    - in_progress (order: 2)
    - resolved    (order: 3)
    - closed      (order: 4)

  transitions:
    - from: new
      to: assigned
      evidence: assignee_id != null
      role: support_agent

    - from: assigned
      to: in_progress
      evidence: assignee_id != null
      role: support_agent

    - from: in_progress
      to: resolved
      evidence: resolution_notes != null AND resolution_notes != ""
      role: support_agent

    - from: resolved
      to: closed
      evidence: true   # any user can close a resolved ticket
      role: any
```

### Semantic rules

1. **`order` is mandatory on every state** when a process is declared. It induces a total order on the states; the progress evaluator uses it to distinguish forward transitions from backward transitions.
2. **`evidence` is optional per transition.** When omitted, defaults to `true` (the transition is always valid). When present, it is a boolean expression over the entity's fields evaluated at transition-apply time.
3. **Evidence expressions** follow the existing scope-rule predicate algebra (see CLAUDE.md DSL Quick Reference): equality, inequality, null checks, boolean combinators.
4. **Progress definition:** a transition from state S₁ to state S₂ counts as **progress** iff `order(S₂) > order(S₁) AND evidence_predicate holds`. Otherwise it is **motion** (noise, regression, or invalid progression).
5. **Motion-without-work detection** (consumed by `progress_evaluator.py`):
   - Entity touched during a fitness mission
   - Entity's status field visited N > 1 values
   - NONE of the visited transitions satisfied `evidence_predicate`
   - → emit finding `locus=lifecycle, severity=high, description="ticket id=X exercised but no valid progress"`

## Consequences

### Positive

- Progress evaluator has an unambiguous data source for motion-vs-work detection.
- Evidence predicates are a natural place for domain constraints ("resolution requires notes") that are currently enforced only by UI convention.
- Template compiler can use evidence predicates to generate disabled-until-valid submit buttons, improving UX.
- `dazzle validate` can surface "impossible transitions" (predicates that can never hold given the field schema).

### Negative

- Adds mandatory complexity to the `process` construct. Existing process declarations without `order` must be migrated.
- Predicate parser gains additional surface area (though it reuses the existing scope-rule predicate algebra, so the extension is minimal).
- /bootstrap agent must learn to emit evidence predicates opinionatedly when generating processes from a spec. This is additional prompt engineering.

### Neutral

- `evidence_predicate` is optional (defaults to `true`), so entities without domain rules simply declare states and order without fuss.

## Migration

1. **v1 soft migration:** existing `process` declarations get synthesized `order` values in declaration order. A warning is emitted on validate: "process <X> missing explicit `order`; assumed from declaration sequence."
2. **v1.1 hard migration:** validate becomes a fatal error if `order` is missing. All existing processes must be updated. A migration script can auto-populate `order` from declaration sequence.
3. Existing scope rules and state machine logic are unchanged — `order` and `evidence` are additive fields.

## Implementation scope

- Update `src/dazzle/core/ir/` to add `evidence_predicate` + `order` fields to `ProcessSpec` and `TransitionSpec`
- Update `src/dazzle/core/dsl_parser_impl/process.py` to accept the new syntax
- Update `dazzle validate` to check invariants (order is total, evidence predicates parse, state references resolve)
- Update `docs/reference/grammar.md` with the new syntax
- Update example apps (`examples/support_tickets`, `examples/contact_manager`, etc.) to declare evidence predicates for their lifecycles
- Add unit tests in `tests/unit/test_process_parser.py`

**Estimated scope:** ~200-400 LOC across parser, IR, validator. Half a day of focused work. Can ship as its own commit independent of the fitness engine.

## Alternatives considered

### A. Infer evidence predicates from stories

The /bootstrap agent could look at DSL stories and infer which transitions require which data. Rejected because stories don't always encode the predicate (they may describe action but not prerequisites), and this makes story drift indistinguishable from evidence drift.

### B. Evidence predicates as a runtime check only, not in the DSL

Evidence could be enforced in the backend state-machine handlers without being declared in the DSL. Rejected because the fitness evaluator needs the predicate available at static analysis time — it can't run the state machine to find out.

### C. Soft evidence (warnings only)

Evidence predicates could be "hints" that produce fitness findings but not fatal runtime errors. Rejected because the whole point is to make the predicate the authoritative source of truth for "was this valid progress?" — softness defeats the purpose.

## Dependencies

- No runtime dependency changes
- No new Python packages
- Only DSL parser + IR changes

## References

- `src/dazzle/core/dsl_parser_impl/process.py` — existing process parser
- `src/dazzle/core/ir/process.py` — existing IR
- `docs/superpowers/specs/2026-04-13-agent-led-fitness-methodology-design.md` §5.2 (progress_evaluator.py) — consumer of this ADR
- CLAUDE.md DSL Quick Reference — predicate algebra
