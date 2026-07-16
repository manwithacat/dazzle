# Stem: Story-driven job workspaces (fieldtest_hub)

## Claim

fieldtest_hub teaches multi-entity field QA **and** job workspaces: triage queues
and fleet metrics for engineer/manager; personal queues for testers.

## Reconstruct

- Engineer/manager: `engineering_dashboard` = fleet metrics + triage/critical
  queues + open task queue; keep kanban/map/tree as secondary demos.
- Tester: `tester_dashboard` = personal metrics + device/issue/task queues.
- ST-037–041 own the manager/engineer job surfaces; ST-042–044 own tester.

## Not this

- Landing managers only on density demos (map/tree) without pressure metrics.
- Treating issue triage as a plain chronological list.

## Expressions

- `dsl/app.dsl` workspaces; `dsl/stories.dsl` ST-037–044
- `docs/guides/story-to-composition.md`
