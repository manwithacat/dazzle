# Stem: Story-driven job workspaces (support_tickets)

## Claim

support_tickets teaches **job workspaces** (queue, metrics, SLA strip), not only
multi-entity CRUD. Stories ST-019–030 own the composition; CRUD stories
ST-013–018 own surfaces.

## Reconstruct

- Agent default: `ticket_queue` = metrics + `display: queue` + kanban.
- Manager default: `manager_ops` = team metrics + status_list SLA strip +
  critical/unassigned queues + funnel (not an empty personal list).
- Customer default: `my_tickets` = my metrics + open queue + history list.
- Prefer queue/metrics over bare list for open-work stories.
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
