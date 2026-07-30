# Stem: Story-driven job workspaces (llm_ticket_classifier)

## Claim

AI classification dogfood still lands on **job surfaces**: supervisor metrics +
open queue; agent ticket queue — not list-only CRUD homes. Ticket hubs show
related AI classifications as a **pull queue** (not warehouse table) (ST-002).

## Reconstruct

- Supervisor `support_dashboard` = metrics + open queue + classifications list.
- Agent `ticket_management` = non-closed queue + full list.
- Ticket detail hub: lifecycle strip + related classifications `display: queue`
  (cycle 1504 journey_dogfood).
- LLM intents remain the automation story; workspaces own the human job.

## Not this

- Supervisor home = raw dual lists with no pressure metrics.
- Sorting tickets by a field that lives only on classifications.

## Expressions

- `dsl/app.dsl` workspaces; `docs/guides/story-to-composition.md`
