# Example apps: before/after #1605 agent closed loop
Before HEAD: `37051220c`
After label: `after-1605-sequence` @ `37051220c`

| App | Stories (before) | Accepted bound | Narrative-only | Gate | Processes |
|-----|------------------|----------------|----------------|------|-----------|
| acme_billing | 5 | 0 | 0 | pass | 0 |
| contact_manager | 6 | 0 | 1 | pass | 0 |
| design_studio | 0 | 0 | 0 | pass | 0 |
| domain_join_co | 0 | 0 | 0 | pass | 0 |
| fieldtest_hub | 26 | 0 | 26 | pass | 0 |
| hr_records | 0 | 0 | 0 | pass | 0 |
| invoice_ops | 0 | 0 | 0 | pass | 1 |
| llm_ticket_classifier | 0 | 0 | 0 | pass | 0 |
| ops_dashboard | 10 | 0 | 0 | pass | 0 |
| project_tracker | 0 | 0 | 0 | pass | 0 |
| simple_task | 15 | 1 | 6 | pass | 3 |
| support_tickets | 18 | 0 | 11 | pass | 0 |

## What changed
- MCP `agent` tool: context / prove / playbook
- Story DSL: `executed_by` + `narrative_only`; validate hard-fails accepted+unbound
- CLI: `dazzle scaffold`, `dazzle prove story`
- Example accepted stories migrated (narrative_only or process bind)
- Prove ST-017: `{'story_id': 'ST-017', 'executed_by': 'process.task_auto_assignment', 'result': 'pass', 'reason': 'process_exists', 'evidence': ['process:task_auto_assignment']}`
