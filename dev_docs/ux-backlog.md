# UX Cycle Backlog

Persistent backlog for `/ux-cycle`. Each row is a UX component that should come under ux-architect governance. See `docs/superpowers/specs/2026-04-12-ux-cycle-design.md` for the full design.

**Legend:**
- `status`: PROPOSED / PENDING / IN_PROGRESS / DONE / VERIFIED / BLOCKED / REGRESSION
- `contract`: MISSING / DRAFT / DONE
- `impl`: PENDING / PARTIAL / DONE
- `qa`: PENDING / PASS / FAIL / BLOCKED

## Components

| id     | component          | status    | contract | impl     | qa      | canonical         | applies                                                          | attempts | last_cycle | notes                                                |
|--------|--------------------|-----------|----------|----------|---------|-------------------|------------------------------------------------------------------|----------|------------|------------------------------------------------------|
| UX-001 | dashboard-grid     | DONE      | DONE     | DONE     | PENDING | ops_dashboard     | ops_dashboard,fieldtest_hub,simple_task                          | 1        | 2026-04-11 | shipped v0.54.0                                      |
| UX-002 | data-table         | DONE      | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets,fieldtest_hub,simple_task,ops_dashboard | 1  | 2026-04-11 | shipped v0.54.0                                      |
| UX-003 | card               | DONE      | DONE     | DONE     | PENDING | ops_dashboard     | ops_dashboard,fieldtest_hub                                      | 1        | 2026-04-11 | shipped as part of UX-001                            |
| UX-004 | form               | BLOCKED   | MISSING  | PENDING  | PENDING | simple_task       | simple_task,contact_manager,support_tickets,fieldtest_hub        | 1        | 2026-04-12 | too large — composite of chrome, field, wizard, validation; needs decomposition into sub-components before a cycle can tackle it |
| UX-005 | modal              | PENDING   | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets,fieldtest_hub                    | 1        | 2026-04-12 | contract + refactor complete this cycle; QA deferred (requires running app + modal trigger flow) |
| UX-006 | filter-bar         | PENDING   | MISSING  | PARTIAL  | PENDING | contact_manager   | contact_manager,support_tickets                                  | 0        | —          | already restyled as part of UX-002                   |
| UX-007 | search-input       | PENDING   | MISSING  | PARTIAL  | PENDING | contact_manager   | contact_manager,support_tickets                                  | 0        | —          | already restyled as part of UX-002                   |
| UX-008 | pagination         | PENDING   | MISSING  | PARTIAL  | PENDING | contact_manager   | contact_manager,support_tickets                                  | 0        | —          | already restyled as part of UX-002                   |
| UX-009 | widget:combobox    | PENDING   | MISSING  | DONE     | PENDING | contact_manager   | contact_manager,support_tickets,fieldtest_hub                    | 0        | —          | TomSelect wrapper                                    |
| UX-010 | widget:datepicker  | PENDING   | MISSING  | DONE     | PENDING | support_tickets   | support_tickets                                                  | 0        | —          | Flatpickr wrapper                                    |
| UX-011 | command-palette    | PENDING   | MISSING  | DONE     | PENDING | ops_dashboard     | ops_dashboard,fieldtest_hub                                      | 0        | —          | Cmd+K spotlight — dzCommandPalette                   |
| UX-012 | slide-over         | PENDING   | MISSING  | DONE     | PENDING | contact_manager   | contact_manager,support_tickets                                  | 0        | —          | Detail drawer — dzSlideOver                          |
| UX-013 | toast              | PENDING   | MISSING  | DONE     | PENDING | simple_task       | all                                                              | 0        | —          | Notification — dzToast                               |
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
