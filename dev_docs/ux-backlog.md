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
| UX-001 | dashboard-grid     | READY_FOR_QA | DONE     | DONE     | FAIL    | ops_dashboard     | ops_dashboard,fieldtest_hub,simple_task                          | 2        | 2026-04-13 | Cycle 113 — first real Phase B run (b6aa1d63+). ops_dashboard bootstrapped this cycle. Run IDs: admin=7bfe75c8, ops_engineer=7ce13cc6. 46 findings total (23 per persona), degraded=False. Walker noted a 403 inconsistency — admin sometimes sees the dashboard, sometimes gets Forbidden at command_center. See examples/ops_dashboard/dev_docs/fitness-backlog.md for the full finding list. |
| UX-002 | data-table         | READY_FOR_QA | DONE     | DONE     | FAIL    | contact_manager   | contact_manager,support_tickets,fieldtest_hub,simple_task,ops_dashboard | 2  | 2026-04-13 | Cycle 114 — first real Phase B. contact_manager bootstrapped this cycle (.env added, dev personas admin + user auto-provisioned). Run IDs: admin=86b55a36, user=b8cfba35. 20 findings total (10 per persona), degraded=False. No 403 inconsistencies — Contact Manager UI renders correctly for both personas. Findings in examples/contact_manager/dev_docs/fitness-backlog.md. |
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
| UX-026 | widget:money       | READY_FOR_QA | DONE     | DONE     | PENDING | support_tickets   | support_tickets,fieldtest_hub                                    | 1        | 2026-04-12 | dzMoney (pinned + unpinned); Cycle 23 — flex group replaces DaisyUI `join`, adjacent borders collapse via border-r-0 |
| UX-027 | widget:file        | READY_FOR_QA | DONE     | DONE     | PENDING | support_tickets   | support_tickets,fieldtest_hub                                    | 1        | 2026-04-12 | dzFileUpload dropzone; Cycle 24 — template refactor + `<progress>` pseudo-element override |
| UX-028 | widget:search_select | READY_FOR_QA | DONE    | DONE     | PENDING | contact_manager   | contact_manager,support_tickets                                  | 1        | 2026-04-12 | Dynamic search-select; Cycle 25 — **form_field.html now 100% DaisyUI-free** |
| UX-029 | detail-view        | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | all                                                              | 1        | 2026-04-12 | Generic detail surface; Cycle 26 — pure Tailwind, 6 Jinja blocks preserved, 29 DaisyUI hits → 0 |
| UX-030 | review-queue       | READY_FOR_QA | DONE     | DONE     | PENDING | support_tickets   | support_tickets                                                  | 1        | 2026-04-12 | Approval queue; Cycle 27 — action-style semantic mapping (primary/error/default), data-dz-progress CSS reuse |
| UX-031 | app-shell          | READY_FOR_QA | DONE     | DONE     | PENDING | ops_dashboard     | all                                                              | 1        | 2026-04-12 | Layout chrome; Cycle 28 — dropped DaisyUI drawer, Alpine-driven responsive drawer, converted logout to HTMX POST |
| UX-032 | related-displays   | READY_FOR_QA | DONE     | DONE     | PENDING | contact_manager   | contact_manager,support_tickets                                  | 1        | 2026-04-12 | 3 fragments refactored; Cycle 29 — tabs via ARIA pattern, status cards, file list; all share detail-view's card tokens |
| UX-033 | base-layout        | READY_FOR_QA | DONE     | DONE     | PENDING | ops_dashboard     | all                                                              | 1        | 2026-04-12 | base.html; Cycle 30 — body bg-base-200 + toast toast-end + alert alert-* all token-driven |
| UX-034 | report-e2e-journey | DONE        | DONE     | DONE     | PASS    | —                 | internal                                                         | 1        | 2026-04-12 | Cycle 31 — **out-of-scope for token governance**; standalone diagnostic report with own palette; 5/5 gates pass |
| UX-035 | region-wrapper     | READY_FOR_QA | DONE     | PARTIAL  | PENDING | ops_dashboard     | all workspace regions                                            | 14       | 2026-04-13 | + detail.html. **14/16 adopters.** 2 remaining (funnel_chart, tab_data). Detail DL uses uppercase muted labels; `badge_class` filter still returns DaisyUI classes — follow-up. |
| UX-036 | auth-page          | READY_FOR_QA | DONE     | DONE     | PENDING | —                 | login,signup,forgot_password,reset_password,2fa_*                | 7        | 2026-04-13 | **All 7 adopters complete (Cycle 42).** 2fa_settings.html is the last — JS dynamically generates rows with named button-class constants (BTN_PRIMARY/BTN_DESTRUCTIVE/BTN_OUTLINE) so future tweaks touch one place. Full grep-sweep on `src/dazzle_ui/templates/site/auth/` confirms zero DaisyUI tokens remain. **impl: DONE** — awaiting Phase B QA when running-app cycle becomes available |

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
| PROP-026 | widget:money | dzMoney currency input (form_field money branch) | PROMOTED→UX-026 | 17 | Promoted in Cycle 23 |
| PROP-027 | widget:file | dzFileUpload dropzone (form_field file branch) | PROMOTED→UX-027 | 17 | Promoted in Cycle 24 |
| PROP-028 | widget:search_select | Dynamic search-select fragment (`fragments/search_select.html`) | PROMOTED→UX-028 | 17 | Promoted in Cycle 25 |
| PROP-029 | review-queue | Approval/review queue component (`components/review_queue.html`) | PROMOTED→UX-030 | 17 | Promoted in Cycle 27 |
| PROP-030 | detail-view | Generic detail surface (`components/detail_view.html`) | PROMOTED→UX-029 | 17 | Promoted in Cycle 26 |
| PROP-031 | app-shell | Layout chrome — navbar/drawer (`layouts/app_shell.html`) | PROMOTED→UX-031 | 17 | Promoted in Cycle 28 |
| PROP-032 | workspace-regions | 4 workspace region types (grid/list/kanban/tabbed_list) | PROPOSED | 17 | ~69 total hits across 4 files; likely decomposes into 4 sub-rows. |
| PROP-033 | auth-pages | 7 auth pages (login/signup/2fa_\*/forgot/reset) | PROMOTED→UX-036 | 17 | Promoted in Cycle 33 |
| PROP-034 | base-layout | Top-level HTML base (`base.html`) | PROMOTED→UX-033 | 17 | Promoted in Cycle 30 |
| PROP-035 | related-displays | Related-entity display fragments (table/status-cards/file-list) | PROMOTED→UX-032 | 17 | Promoted in Cycle 29 |
| PROP-036 | reports-e2e-journey | E2E journey report (`reports/e2e_journey.html`) | PROMOTED→UX-034 | 17 | Promoted in Cycle 31 |
