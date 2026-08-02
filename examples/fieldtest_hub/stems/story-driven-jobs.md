# Stem: Story-driven job workspaces (fieldtest_hub)

## Claim

fieldtest_hub teaches multi-entity field QA **and** job workspaces: triage queues
and fleet metrics for engineer/manager; personal queues for testers.

## Reconstruct

- Engineer/manager: `engineering_dashboard` = fleet metrics + `device_attention`
  queue (non-active devices — TR-35) + triage/critical queues + open task queue;
  keep kanban/map/tree as secondary demos.
- Tester: `tester_dashboard` = personal metrics + device/issue/task queues.
- ST-037–041 own the manager/engineer job surfaces; ST-042–044 own tester.
- Device hub related issues/sessions and tester hub activity/assignments are
  **pull queues** (ST-045/047), not warehouse tables.

- List triple-open (story_walk dig cycle 1592): `issue_report_list` →
  IssueReport|Device|Tester(reported_by); `test_session_list` →
  TestSession|Device|Tester.
- List multi-open (journey dig): `device_list` → Device|Tester via
  `assigned_tester_id`; `task_list` → Task|assignee|creator via
  `assigned_to_id` + `created_by_id`.

## Not this

- Landing managers only on density demos (map/tree) without pressure metrics.
- Treating issue triage as a plain chronological list.
- Hub related rosters as dense tables when the job is pull-next field work.

## Expressions

- `dsl/app.dsl` workspaces; `dsl/stories.dsl` ST-037–044
- `docs/guides/story-to-composition.md`
