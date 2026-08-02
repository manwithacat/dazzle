# Stem: Story-driven job workspaces (hr_records)

## Claim

HR homes open with headcount/compensation metrics before dense directories.

## Reconstruct

- staff_directory: headcount metrics then staff lists; assignment status mix
  (active / on_leave / terminated) sits beside department mix for ST-001/ST-005.
- compensation_review: compensation metrics then salary list.
- employment_list + person hub related employment show status alongside dates.
- Temporal/history surfaces stay list/timeline for the teaching gap.

- List open hops: `employment_list` → Employment|Person|Role (ST-005 triple);
  `managerlink_list` → ManagerLink|Person(report)|Person(manager) (ST-002 triple);
  `salary_list` → Salary|Person; `role_list` → Role|Department (ST-001/003);
  `department_list` → Department|parent_department (org tree context).

## Not this

- Persona lands on a bare entity list when the job is triage, review, or oversight.
- Story `given:` workspace names that disagree with `default_workspace`.

## Expressions

- `dsl/` workspaces + personas; `docs/guides/story-to-composition.md`
