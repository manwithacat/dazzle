# Stem: Story-driven job workspaces (project_tracker)

## Claim

Dashboard/board/my-tasks are job homes: metrics + queues before warehouse lists.

## Reconstruct

- admin/manager default: `dashboard` = portfolio metrics + open task queue + grid + kanban.
- member default: `my_tasks` = personal load + assigned queue + board.
- `project_board` = delivery kanban + unassigned queue + milestones.
- `milestone_plan` = manager schedule desk (milestones + active projects).

## Not this

- Persona lands on a bare entity list when the job is triage or delivery.
- Story `given:` workspace names that disagree with `default_workspace`.

## Expressions

- `dsl/` workspaces + personas; `docs/guides/story-to-composition.md`
- Product maturity: `scripts/example_product_maturity.py`
