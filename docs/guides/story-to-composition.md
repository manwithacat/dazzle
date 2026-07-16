# Story → composition playbook

How to lift a Dazzle example (or product app) from **entity CRUD tables** to
**job workspaces** that match declared stories and personas.

Companion stem: `examples/support_tickets/stems/story-driven-jobs.md`.
HM gallery blueprints: `ops-queue`, `triage-drawer`, `manager-sla-strip`.

## Rule

> **Story → persona → default_workspace → Hyperpart composition.**
> If the primary region is a generic `list` of the whole entity, the story
> probably wants a **queue**, **metrics strip**, **kanban**, or **scoped** list.

## Steps

### 1. Inventory stories by persona

Group `stories.dsl` (or product jobs) by `persona:`. Flag:

- **CRUD stories** (create/edit entity) → surfaces, not workspace primaries.
- **Job stories** (“views open tickets”, “reviews team performance”) → workspaces.

### 2. Map each job story to a display mode

| Signal in the story | Prefer |
|---------------------|--------|
| Open / unacked / unassigned / “work the pile” | `display: queue` |
| Counts, SLA, team health | `display: metrics` (+ `tones:`) |
| Readiness / checklist / policy strip | `display: status_list` |
| Move through states on a board | `display: kanban` |
| Lifecycle pressure | `funnel_chart` / `progress` |
| “What needs me” multi-source | `task_inbox` (ops_dashboard dogfood) |
| My scoped history | filtered `list` or `queue` |

Dogfood: `examples/ops_dashboard` (`ack_queue`, `ops_inbox`, `health_summary`).

### 3. Freeze the composition before editing DSL

Write a short table (region → display → story ids). Keep secondaries
(kanban, timeline) **below** the job primary. Do not add regions “because
they exist in the catalogue.”

### 4. Wire personas honestly

- `default_workspace:` must be the composition that matches the persona’s
  **first job**, not the densest demo surface.
- If two personas share a queue, set `access: persona(...)` on that workspace.
- Align `stories.dsl` `given:` lines with the real workspace name (see ST-027).

### 5. Implement in DSL

```dsl
workspace ticket_queue "Ticket Queue":
  purpose: "Agent workspace for open support work"
  stage: "scanner_table"
  access: persona(agent, manager)

  queue_metrics:
    source: Ticket
    display: metrics
    aggregate:
      total_open: count(Ticket where status = open)
      critical: count(Ticket where priority = critical and status != closed)
    tones:
      critical: destructive

  open_queue:
    source: Ticket
    filter: status != closed
    sort: priority desc, created_at asc
    display: queue
    action: ticket_edit
    empty: "No open tickets"
```

Validate: `uv run dazzle validate examples/<app>`.

### 6. Mirror in HM when the motif is reusable

If the composition is a page-scale motif (not app-specific data), add a
**Blueprint** in `packages/hatchi-maxchi/site/blueprints.py` composed only of
published Hyperparts — then rebuild the gallery site. Prefer Blueprint over
a new Hyperpart (invention ladder).

### 7. Mutation feedback

Do not invent client toast state. Use framework `with_toast` / mutation
response chrome (titled toast, optional View action). Opt-in sound stays off
unless the app sets cue meta (`chrome-cue-opt-in` stem).

## Anti-patterns

| Smell | Fix |
|-------|-----|
| Persona lands on empty “my assigned” when seed assigns to others | Metrics/team queue first (TR-52 class) |
| Story says “queue” but region is `list` | Switch primary to `display: queue` |
| Manager story names workspace A, `default_workspace` is B | Rename story or default — one truth |
| Every entity gets a list surface as the home | Home is a **workspace**, lists are CRUD routes |
| New CSS for “ops page” | Compose Hyperparts / Blueprint |

## Checklist

- [ ] Job stories mapped to displays
- [ ] Composition freeze written
- [ ] `default_workspace` + story `given:` agree
- [ ] `access:` covers shared surfaces
- [ ] `dazzle validate` clean
- [ ] Optional: HM Blueprint + gallery rebuild
- [ ] Optional: trial scenario for the job persona

## Worked examples

**support_tickets** (keystone):

- Agent → `ticket_queue` = metrics + **queue** + kanban
- Manager → `manager_ops` = metrics + status_list + critical/unassigned queues + funnel
- Customer → `my_tickets` = metrics + open queue + history list

**simple_task**:

- Admin → `admin_dashboard` = metrics + urgent/overdue queues
- Manager → `team_overview` = metrics + review/unassigned/WIP queues
- Member → `my_work` = personal metrics + WIP/todo queues

**project_tracker**:

- Admin/manager → `dashboard` = portfolio metrics + open task queue + grid + kanban
- Member → `project_board` = board metrics + kanban + unassigned queue

**contact_manager**:

- User → `home` = directory metrics + favourites queue + sample list
- User → `contacts` = search + favourites queue + dual-pane list/detail

**hr_records**:

- HR/manager → `staff_directory` = headcount metrics + directory lists
- Finance → `compensation_review` = compensation metrics + salary list

**invoice_ops**:

- Approver/finance → `finance_ops` = metrics + awaiting_approval / ready_to_pay /
  disputed **queues** + funnel + payment chart

**acme_billing**:

- Admin/owner/auditor → `billing` = portfolio metrics + invoice queue + entity lists
