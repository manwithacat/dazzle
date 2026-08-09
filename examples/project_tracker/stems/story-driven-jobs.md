# Stem: Story-driven job workspaces (project_tracker)

## Claim

Dashboard/board/my-tasks are job homes: metrics + queues before warehouse lists.

## Reconstruct

- admin/manager default: `dashboard` = portfolio metrics + composition +
  conversation + open task queue + grid + kanban (no priority bar-chart void).
- member default: `my_tasks` = personal load + conversation + assigned queue +
  board (no chart / twin comment timeline).
- `project_board` = delivery kanban + unassigned queue + milestones (metrics
  encode status counts — no project status chart theater).
- `milestone_plan` = manager schedule desk (milestones + active projects).
- Project hub related **tasks** and **milestones** are **pull queues**
  (milestones: name+status+end) — not status_cards warehouse chrome.
- List triple-open (acceptance dig cycle 1595): `comment_list` →
  Comment|Task|User(author); `attachment_list` → Attachment|Task|User(uploaded_by).
- List dual-open (journey dig): `milestone_list` → Milestone|Project.
- Task list triple open `Task via id | Project via parent_project | User via
  assigned_to` (cycle 1586 story_walk) — task hub, parent project, assignee
  teammate (ST-002/005).
- Project list dual open `Project via id | User via owner` (cycle 1575
  story_walk) — project hub first; secondary owner teammate hub (ST-001/004).

## Not this

- Persona lands on a bare entity list when the job is triage or delivery.
- Story `given:` workspace names that disagree with `default_workspace`.
- Hub milestone roster as status_cards when the job is pull-next delivery.
- Task list hops **only** to parent Project (orphan project-only open).

## Expressions

- `dsl/` workspaces + personas; `docs/guides/story-to-composition.md`
- Product maturity: `scripts/example_product_maturity.py`
