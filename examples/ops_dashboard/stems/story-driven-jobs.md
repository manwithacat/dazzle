# Stem: Story-driven job workspaces (ops_dashboard)

## Claim

Reference dogfood: command centre is already metrics/queue/status_list/task_inbox shaped.

## Reconstruct

- Keep ack_queue, health_summary, ops_readiness, ops_inbox as the story map.
- Prefer extending jobs over adding bare lists.
- Alert list dual open-via: **Alert hub** (id) + **System hub** (system FK) —
  triage notes without losing parent context hops.

## Not this

- Persona lands on a bare entity list when the job is triage, review, or oversight.
- Story `given:` workspace names that disagree with `default_workspace`.
- Alert rows that only warehouse-open the parent and never the alert hub.

## Expressions

- `dsl/` workspaces + personas; `docs/guides/story-to-composition.md`
