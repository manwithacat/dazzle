# Stem: Story-driven job workspaces (support_tickets)

## Claim

support_tickets teaches **job workspaces** (queue, metrics, SLA strip), not only
multi-entity CRUD. Stories ST-019–030 own the composition; CRUD stories
ST-013–018 own surfaces.

## Reconstruct

- Agent default: `ticket_queue` = metrics + `display: queue` + kanban.
- Agent secondary: `agent_dashboard` personal WIP = **kanban** (`my_assigned`
  group_by status, non-closed) + resolved **queue** (`pending_resolution`) —
  stage movement after claim, not a single-status list (HMC-065).
- Manager default: `manager_ops` = team metrics + status_list SLA strip +
  critical/unassigned queues (limit 12) + funnel + short recent_trail
  timeline (not an empty personal list; no second open-board kanban —
  lifecycle board stays on agent_dashboard).
- Customer default: `my_tickets` = my metrics + open queue + resolved **timeline**
  (`resolved_recent`) + history trail.
- Comment streams on `ticket_queue` / `agent_dashboard` use **timeline**
  (dated events), not inventory list — same work-surface utility as simple_task.
- Comment list dual open `Comment via id | Ticket via ticket` (cycle 1543
  journey_dogfood) — inspect the note or hop to the parent ticket hub.
- Ticket list dual open `Ticket via id | User via assigned_to` (cycle 1572
  agent_acceptance) — ticket hub first; secondary assignee hub for load /
  reassignment context (ST-019/028).
- Prefer queue/metrics/kanban/timeline over bare list for open-work and event streams.
- Keep story `given:` workspace names aligned with persona defaults.

## Not this

- Landing every persona on the same entity list “for demo density.”
- Manager home = personal assigned list when seed assigns to agents (TR-52).
- Replacing teaching kanban with nothing — keep it as secondary lifecycle board.

## Expressions

- `dsl/app.dsl` workspaces `ticket_queue`, `manager_ops`, `my_tickets`
- `dsl/stories.dsl` ST-019–030
- Framework: `docs/guides/story-to-composition.md`
- HM: blueprints `ops-queue`, `triage-drawer`, `manager-sla-strip`
