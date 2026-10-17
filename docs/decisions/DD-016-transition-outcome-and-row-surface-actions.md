# DD-016: `transition` outcome on surface actions + per-row surface actions in list mode

```yaml
id: DD-016
status: PARKED
issues: [1787, 1310, 1148, 1592]
adrs: []
decided: 2026-10-17
decided_at_sha: d5148e6de
parent: null
```

## One-line intent

Surface actions do not get a `transition <name>` outcome kind, and `mode: list`
surfaces do not render surface actions per row, until cyfuture needs transition
buttons it cannot get from the state machine.

## Plan (what we already concluded)

The #1787 ask (cyfuture, Plan 2 Phase 14) wrote `on click -> transition received`.
That is not current grammar: `parse_outcome` accepts only `"url" external`,
`surface X`, `experience X [step S]` and `integration X action Y`, and
`OutcomeKind` has no transition kind. State-machine buttons on detail pages and
list rows are derived from the entity's `transitions:` block (a PUT of the
status field), not from surface actions. Surface actions are not rendered in
`mode: list` rows.

When forced, the shape is:

1. **`OutcomeKind.TRANSITION`** — `on click -> transition <to_state>` names a
   target state of the surface entity's state machine. Linker: the entity must
   have a state machine and `<to_state>` must be a declared state with at least
   one transition into it. The rendered button is the same PUT the derived
   transition chip issues; the action only adds a label and placement.
2. **One permission source.** The transition's own guards (`role(...)`,
   `requires`, expression guards) stay the permission. An action `visible:` on a
   transition outcome can only narrow what is offered; the PUT re-runs the SM
   guards, never the action predicate. A declared transition action suppresses
   the derived chip for the same target on that surface, so the button is not
   offered twice.
3. **Per-row surface actions in list mode.** The list-row renderer
   (`render/fragment/renderer/_data_row.py`) gains an actions slot fed with each
   surface action whose `visible:` holds for that row, evaluated upstream in
   `http/` (as #1787 C does for transitions via `refused_row_transitions`) so
   `render/` stays pure. One predicate evaluation per row per action, no
   per-row queries: predicates that read `current_user.<path>` resolve the User
   row once per request.
4. **POST path.** Transition outcomes need nothing new (the PUT is the POST).
   Integration outcomes on list rows reuse `enforce_integration_action`.

Counter-priors: do not give surface actions their own transition endpoint; do
not evaluate the action predicate on the PUT (two permission sources drift —
MDF-02); do not render list-row actions from the client.

## Reopen when (consumer force)

1. **Named consumer** — cyfuture needs transition buttons with custom
   labels/placement or per-row surface actions in list mode.
2. **Evidence of dual-lock / host workaround** — a cyfuture host patch or
   template that relabels or relocates SM chips, or renders row actions itself.
3. **Acceptance that unblocks** — an `InformationRequest` list where staff mark
   a row received from the row, with the label "Mark everything received", and
   the button absent for clients and for rows not in `sent` / `partially_received`.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan below; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- **#1787 B** — `visible:` on surface actions (`ConditionExpr` grammar), validated
  by `dazzle validate` (fields, personas, integration bindings), evaluated per
  record on detail pages; INTEGRATION outcomes refused on POST with 403 naming
  the predicate (`http/runtime/action_visibility.py`). External / surface /
  experience outcomes are hide-only; the host route is the authz boundary.
- **#1787 C** — transition chips on detail pages and list rows are offered only
  when the SM's `role(...)` and expression guards pass for the viewer
  (`TransitionValidator.validate_transition(..., for_render=True)`). The PUT is
  unchanged and remains the permission.
- Field / section `visible:` are validated and evaluated against the record.

## Explicitly out of scope until force

- Workspace queue regions applying per-row SM guards (they drop guarded targets
  already, #1663, and stay principal-wide).
- `transition` outcomes on create/edit forms.
- Bulk actions driven by surface actions.

## Trail

| Date | Event |
|------|--------|
| 2026-10-17 | Parked (this DD) alongside #1787 B + C |
