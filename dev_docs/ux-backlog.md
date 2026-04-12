# UX Cycle Backlog

Persistent backlog for `/ux-cycle`. Each row is a UX component that should come under ux-architect governance. See `docs/superpowers/specs/2026-04-12-ux-cycle-design.md` for the full design.

**Legend:**
- `status`: PROPOSED / PENDING / IN_PROGRESS / DONE / VERIFIED / BLOCKED / BLOCKED_ON / NEEDS_HARNESS / READY_FOR_QA / REGRESSION
- `contract`: MISSING / DRAFT / DONE
- `impl`: PENDING / PARTIAL / DONE
- `qa`: PENDING / PASS / FAIL / BLOCKED

**Status semantics (v1.1):**
- `BLOCKED` — unrecoverable without human input (ambiguous design, missing decision)
- `BLOCKED_ON: UX-NNN` — depends on another row; dependency re-prioritised
- `NEEDS_HARNESS` — event-triggered component; needs a test harness before QA can run (agent can write this)
- `READY_FOR_QA` — contract + impl done; awaiting a running app for Phase B verification

## Components

| id     | component          | status    | contract | impl     | qa      | canonical         | applies                                                          | attempts | last_cycle | notes                                                |
|--------|--------------------|-----------|----------|----------|---------|-------------------|------------------------------------------------------------------|----------|------------|------------------------------------------------------|
| UX-001 | dashboard-grid     | READY_FOR_QA | DONE     | DONE     | PENDING | ops_dashboard     | ops_dashboard,fieldtest_hub,simple_task                          | 1        | 2026-04-11 | shipped v0.54.0; awaiting running-app cycle          |
| UX-002 | data-table         | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets,fieldtest_hub,simple_task,ops_dashboard | 1  | 2026-04-11 | shipped v0.54.0; awaiting running-app cycle          |
| UX-003 | card               | READY_FOR_QA | DONE     | DONE     | PENDING | ops_dashboard     | ops_dashboard,fieldtest_hub                                      | 1        | 2026-04-11 | shipped as part of UX-001; awaiting running-app cycle |
| UX-004 | form               | READY_FOR_QA | DONE     | DONE     | PENDING | simple_task       | simple_task,contact_manager,support_tickets,fieldtest_hub        | 1        | 2026-04-12 | aggregate row — cleared by completion of UX-016/017/018/019 in Cycles 6–9; awaiting running-app QA |
| UX-016 | form-chrome        | READY_FOR_QA | DONE     | DONE     | PENDING | simple_task       | all                                                              | 1        | 2026-04-12 | contract + refactor done (Cycle 6); form.html + form_errors.html pure Tailwind; awaiting running-app cycle |
| UX-017 | form-field         | READY_FOR_QA | DONE     | DONE     | PENDING | support_tickets   | all                                                              | 1        | 2026-04-12 | contract + refactor done (Cycle 7); core branches pure Tailwind; widget branches left to UX-009..015 |
| UX-018 | form-wizard        | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,fieldtest_hub                                    | 1        | 2026-04-12 | contract + stepper refactor done (Cycle 8); dzWizard state machine unchanged |
| UX-019 | form-validation    | READY_FOR_QA | DONE     | DONE     | PENDING | support_tickets   | all                                                              | 1        | 2026-04-12 | orchestration contract (Cycle 9); layered model: HTML5 → stage-advance → server 422; no new code, code already implements it |
| UX-005 | modal              | NEEDS_HARNESS | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets,fieldtest_hub                    | 1        | 2026-04-12 | contract + refactor done; QA needs a test harness (event-triggered, no stable URL) |
| UX-006 | filter-bar         | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets                                  | 1        | 2026-04-12 | retroactive contract; refactor done as part of UX-002; awaiting running-app cycle |
| UX-007 | search-input       | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets                                  | 1        | 2026-04-12 | retroactive contract; refactor done as part of UX-002; awaiting running-app cycle |
| UX-008 | pagination         | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets                                  | 1        | 2026-04-12 | retroactive contract; refactor done as part of UX-002; awaiting running-app cycle |
| UX-009 | widget:combobox    | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets,fieldtest_hub                    | 1        | 2026-04-12 | TomSelect wrapper; Cycle 10 — branch pure Tailwind + TS token override in design-system.css |
| UX-010 | widget:datepicker  | READY_FOR_QA | DONE     | DONE     | PENDING | support_tickets   | support_tickets                                                  | 1        | 2026-04-12 | Flatpickr wrapper (picker + range variants); Cycle 11 — token override in design-system.css |
| UX-011 | command-palette    | READY_FOR_QA | DONE     | DONE     | PENDING | ops_dashboard     | ops_dashboard,fieldtest_hub                                      | 1        | 2026-04-12 | Cmd+K spotlight — dzCommandPalette; Cycle 12 — template pure Tailwind; also fixed aria-activedescendant wiring |
| UX-012 | slide-over         | PENDING   | MISSING  | DONE     | PENDING | contact_manager   | contact_manager,support_tickets                                  | 0        | —          | Detail drawer — dzSlideOver                          |
| UX-013 | toast              | NEEDS_HARNESS | DONE     | DONE     | PENDING | simple_task       | all                                                              | 1        | 2026-04-12 | contract + fragment refactor done; QA needs a test harness (OOB-emitted, no URL) |
| UX-014 | confirm-dialog     | PENDING   | MISSING  | DONE     | PENDING | contact_manager   | all                                                              | 0        | —          | dzConfirm                                            |
| UX-015 | popover            | PENDING   | MISSING  | DONE     | PENDING | ops_dashboard     | ops_dashboard,fieldtest_hub                                      | 0        | —          | dzPopover (anchored to Floating UI)                  |

## Exploration Findings

| id     | kind                | description                                                | status    | source_cycle | notes |
|--------|---------------------|------------------------------------------------------------|-----------|--------------|-------|
| _(none yet — populated by EXPLORE mode)_ | | | | | |

## Proposed Components

| id      | component_name | description                                              | status    | source_cycle | notes |
|---------|----------------|----------------------------------------------------------|-----------|--------------|-------|
| _(none yet — populated by EXPLORE strategy A)_ | | | | | |
