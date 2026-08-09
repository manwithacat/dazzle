# Stem: Story-driven job workspaces (simple_task)

## Claim

simple_task teaches **job workspaces** (metrics + queue) for admin/manager/member
personas, not only kanban + list CRUD.

## Reconstruct

- Admin: `admin_dashboard` = metrics + urgent/overdue queues.
- Manager: `team_overview` = conversation + metrics + briefs + review + plate
  (no flow_chart bar void / twin comment timeline).
- Member: `my_work` = conversation + metrics + briefs + board + dues (no twin
  comment dump); completed stays list.
- Prefer `display: queue` for open work; keep dual kanban on `task_board`
  (status + assignee) without status bar-chart theater.
- List triple-open (acceptance dig): `task_list` → Task|User(assignee)|User(created_by);
  triple-open `task_comments` → TaskComment|Task|User(author).

## Not this

- Landing members on a global unscoped task list.
- Metrics regions without `display: metrics` / tones for pressure.
- Task list hops **only** to assignee (no Task hub + creator context).

## Expressions

- `dsl/app.dsl` workspaces; `dsl/stories.dsl` ST-014–020
- `docs/guides/story-to-composition.md`
