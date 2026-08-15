# Stem: Story-driven job workspaces (support_tickets)

## Claim

support_tickets teaches **job workspaces** (queue, metrics, SLA strip), not only
multi-entity CRUD. Stories ST-019–030 own the composition; CRUD stories
ST-013–018 own surfaces.

## Reconstruct

- Agent default: `ticket_queue` = metrics + `display: queue` + kanban.
- Agent secondary: `agent_dashboard` personal WIP = **kanban** (`my_assigned`
  group_by status, non-closed) + conversation notes queue + resolved **queue**
  (`pending_resolution`) + **one** comment timeline — stage movement after
  claim, not a single-status list (HMC-065); no funnel/progress chart theater
  or triple activity dumps (empty_region honesty cycle 1812).
- Manager default: `manager_ops` = team metrics + status_list SLA strip +
  critical/unassigned queues (limit 4) + SLA waiver composition (limit 4) +
  live conversation (limit 4) — no status funnel or secondary ticket trail
  (empty_region honesty cycle 1850; funnel_chart coverage on agent_console;
  cycle 2086 agent_only_selector keeps the inspector picker staff-only).
  Not an empty personal list; no second open-board kanban — lifecycle board
  stays on agent_dashboard.
- Customer default: `my_tickets` = my metrics + open/WIP queues + **one**
  case-history timeline + how-it-works (no bar-chart theater or twin dumps).
- Comment streams on `ticket_queue` / `agent_dashboard` use **timeline**
  (dated events), not inventory list — same work-surface utility as simple_task.
- Comment list dual open `Comment via id | Ticket via ticket` (cycle 1543
  journey_dogfood) — inspect the note or hop to the parent ticket hub.
- Ticket list triple open `Ticket via id | User via assigned_to | User via created_by`
  (cycle 1591 journey_dogfood) — ticket hub first; assignee hub for load /
  reassignment; creator hub for customer context (ST-019/028).
- Agent Console inspector `context_selector` lists frontline staff only
  (`support_tier = l1 and department != External`; cycle 2086
  `agent_only_selector`) — Zendesk/Front pickers do not default to a
  customer requester void.
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
