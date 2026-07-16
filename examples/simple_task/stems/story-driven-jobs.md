# Stem: Story-driven job workspaces (simple_task)

## Claim

simple_task teaches **job workspaces** (metrics + queue) for admin/manager/member
personas, not only kanban + list CRUD.

## Reconstruct

- Admin: `admin_dashboard` = metrics + urgent/overdue queues.
- Manager: `team_overview` = metrics + review/unassigned/WIP queues.
- Member: `my_work` = personal metrics + WIP/todo queues; completed stays list.
- Prefer `display: queue` for open work; keep kanban on `task_board`.

## Not this

- Landing members on a global unscoped task list.
- Metrics regions without `display: metrics` / tones for pressure.

## Expressions

- `dsl/app.dsl` workspaces; `dsl/stories.dsl` ST-014–020
- `docs/guides/story-to-composition.md`
