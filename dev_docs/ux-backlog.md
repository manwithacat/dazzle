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
| UX-005 | modal              | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets,fieldtest_hub                    | 1        | 2026-04-12 | contract + refactor (Cycle 1); unblocked by UX-020 harness (Cycle 16); awaiting running-app QA |
| UX-006 | filter-bar         | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets                                  | 1        | 2026-04-12 | retroactive contract; refactor done as part of UX-002; awaiting running-app cycle |
| UX-007 | search-input       | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets                                  | 1        | 2026-04-12 | retroactive contract; refactor done as part of UX-002; awaiting running-app cycle |
| UX-008 | pagination         | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets                                  | 1        | 2026-04-12 | retroactive contract; refactor done as part of UX-002; awaiting running-app cycle |
| UX-009 | widget:combobox    | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets,fieldtest_hub                    | 1        | 2026-04-12 | TomSelect wrapper; Cycle 10 — branch pure Tailwind + TS token override in design-system.css |
| UX-010 | widget:datepicker  | READY_FOR_QA | DONE     | DONE     | PENDING | support_tickets   | support_tickets                                                  | 1        | 2026-04-12 | Flatpickr wrapper (picker + range variants); Cycle 11 — token override in design-system.css |
| UX-011 | command-palette    | READY_FOR_QA | DONE     | DONE     | PENDING | ops_dashboard     | ops_dashboard,fieldtest_hub                                      | 1        | 2026-04-12 | Cmd+K spotlight — dzCommandPalette; Cycle 12 — template pure Tailwind; also fixed aria-activedescendant wiring |
| UX-012 | slide-over         | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets                                  | 1        | 2026-04-12 | dzSlideOver detail drawer; Cycle 13 — both templates pure Tailwind; .escape→.esc alias for semgrep compatibility |
| UX-013 | toast              | READY_FOR_QA | DONE     | DONE     | PENDING | simple_task       | all                                                              | 1        | 2026-04-12 | contract + fragment refactor (Cycle 2); unblocked by UX-020 harness (Cycle 16); awaiting running-app QA |
| UX-014 | confirm-dialog     | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | all                                                              | 1        | 2026-04-12 | dzConfirm; Cycle 14 — native <dialog> + destructive button; unblocked by UX-020 harness (Cycle 16) |
| UX-015 | popover            | READY_FOR_QA | DONE     | DONE     | PENDING | ops_dashboard     | ops_dashboard,fieldtest_hub                                      | 1        | 2026-04-12 | dzPopover; Cycle 15 — pure Tailwind, x-anchor preserved; unblocked by UX-020 harness (Cycle 16) |
| UX-020 | widget-harness-set | DONE      | DONE     | DONE     | PASS    | —                 | UX-005,UX-013,UX-014,UX-015                                      | 1        | 2026-04-12 | Cycle 16 — static/test-event-widgets.html; unblocks 4 NEEDS_HARNESS rows; 5/5 gates pass |
| UX-021 | widget:multiselect | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets,fieldtest_hub                    | 1        | 2026-04-12 | TomSelect multi-select; Cycle 18 — template-only refactor, zero CSS (UX-009 override covers `.ts-wrapper.multi`) |
| UX-022 | widget:tags        | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | all                                                              | 1        | 2026-04-12 | TomSelect tags (create:true); Cycle 19 — template-only, zero CSS |
| UX-023 | widget:slider      | READY_FOR_QA | DONE     | DONE     | PENDING | fieldtest_hub     | fieldtest_hub                                                    | 1        | 2026-04-12 | Native range input + dzRangeTooltip; Cycle 20 — pure Tailwind + scoped CSS override for ::slider-thumb/track |
| UX-024 | widget:colorpicker | READY_FOR_QA | DONE     | DONE     | PENDING | fieldtest_hub     | fieldtest_hub                                                    | 1        | 2026-04-12 | Pickr wrapper; Cycle 21 — template refactor + prospective .pcr-app override in design-system.css |
| UX-025 | widget:richtext    | READY_FOR_QA | DONE     | DONE     | PENDING | fieldtest_hub     | fieldtest_hub,support_tickets                                    | 1        | 2026-04-12 | Quill wrapper; Cycle 22 — template refactor + ~150-line .ql-snow override; also removed `\| safe` from editor div (bridge handles restore) |

## Exploration Findings

| id     | kind                | description                                                | status    | source_cycle | notes |
|--------|---------------------|------------------------------------------------------------|-----------|--------------|-------|
| EX-001 | coverage-gap        | 82 template files still contain DaisyUI class tokens. The original backlog (UX-001..019) only covered ~20 "core" component files. Remaining 62 files span widget branches, workspace regions, site/auth pages, layout chrome, fragments, and reports. | OPEN | 17 | Top findings recorded as PROP-021..036. Full list ranked by hit count in ux-log.md cycle 17 entry. |

## Proposed Components

| id      | component_name | description                                              | status    | source_cycle | notes |
|---------|----------------|----------------------------------------------------------|-----------|--------------|-------|
| PROP-021 | widget:multiselect | TomSelect multi-select wrapper (form_field multi_select branch) | PROMOTED→UX-021 | 17 | Promoted in Cycle 18 |
| PROP-022 | widget:tags | TomSelect tags wrapper with create-on-the-fly (form_field tags branch) | PROMOTED→UX-022 | 17 | Promoted in Cycle 19 |
| PROP-023 | widget:colorpicker | Pickr colour picker wrapper (form_field color branch) | PROMOTED→UX-024 | 17 | Promoted in Cycle 21 |
| PROP-024 | widget:richtext | Quill editor wrapper (form_field rich_text branch) | PROMOTED→UX-025 | 17 | Promoted in Cycle 22 |
| PROP-025 | widget:slider | Native range input + dzRangeTooltip Alpine (form_field slider branch) | PROMOTED→UX-023 | 17 | Promoted in Cycle 20 |
| PROP-026 | widget:money | dzMoney currency input (form_field money branch) | PROPOSED | 17 | Uses DaisyUI `join` + `btn-ghost` for prefix; pinned/unpinned variants. Alpine + Tailwind refactor. |
| PROP-027 | widget:file | dzFileUpload dropzone (form_field file branch) | PROPOSED | 17 | Dropzone with drag-drop + preview; uses `btn-ghost` and `bg-base-200`. Alpine + Tailwind refactor. |
| PROP-028 | widget:search_select | Dynamic search-select fragment (`fragments/search_select.html`) | PROPOSED | 17 | May share contract with UX-009 combobox family; verify scope. |
| PROP-029 | review-queue | Approval/review queue component (`components/review_queue.html`) | PROPOSED | 17 | 36 DaisyUI hits; btn+card heavy. |
| PROP-030 | detail-view | Generic detail surface (`components/detail_view.html`) | PROPOSED | 17 | 29 hits; btn-outline, btn-sm pattern. Used by non-table detail surfaces. |
| PROP-031 | app-shell | Layout chrome — navbar/drawer (`layouts/app_shell.html`) | PROPOSED | 17 | 32 hits; navbar+drawer. Affects every page. |
| PROP-032 | workspace-regions | 4 workspace region types (grid/list/kanban/tabbed_list) | PROPOSED | 17 | ~69 total hits across 4 files; likely decomposes into 4 sub-rows. |
| PROP-033 | auth-pages | 7 auth pages (login/signup/2fa_\*/forgot/reset) | PROPOSED | 17 | ~149 total hits; likely 2–3 shared auth-chrome contracts. |
| PROP-034 | base-layout | Top-level HTML base (`base.html`) | PROPOSED | 17 | 17 hits; link styles + global loading indicators. |
| PROP-035 | related-displays | Related-entity display fragments (table/status-cards/file-list) | PROPOSED | 17 | 33+ hits across 3 variants; shared layout contract likely. |
| PROP-036 | reports-e2e-journey | E2E journey report (`reports/e2e_journey.html`) | PROPOSED | 17 | 18 hits; badge/card/steps. Standalone report surface. |
