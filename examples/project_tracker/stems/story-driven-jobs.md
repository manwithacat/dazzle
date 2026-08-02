# Stem: Story-driven job workspaces (project_tracker)

## Claim

Dashboard/board/my-tasks are job homes: metrics + queues before warehouse lists.

## Reconstruct

- admin/manager default: `dashboard` = portfolio metrics + open task queue + grid + kanban.
- member default: `my_tasks` = personal load + assigned queue + board.
- `project_board` = delivery kanban + unassigned queue + milestones.
- `milestone_plan` = manager schedule desk (milestones + active projects).
- Project hub related **tasks** and **milestones** are **pull queues**
  (milestones: name+status+end) — not status_cards warehouse chrome.
- List dual-open (journey dig): `task_list` → Task|Project; `comment_list` →
  Comment|Task; `milestone_list` → Milestone|Project; `attachment_list` →
  Attachment|Task.
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
