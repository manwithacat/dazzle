# Playbook: pick a work surface (region Hyperpart)

**Goal:** Choose the **region / board / stream** Hyperpart that matches the
operator job — not a control (use `pick-a-surface.md`), not shell measure
(use `pick-a-measure.md`).

**Open when:** Authoring a list workspace; choosing `display:` / region kind;
an agent asks “kanban or table?”; improve looks for hyperpart utility gains.

**Machine ontology:** `work_surface_utility.toml` (same directory).
**Scanner:** `python scripts/work_surface_utility.py` /
`dazzle.qa.work_surface_utility`.

## Steps

1. Name the **job** in one sentence (what the operator does every hour).
2. Name the **primary axis** of comparison: **stage**, **time**, **urgency**,
   or **fields**.
3. Name **mutation**: rearrange stage, complete next, edit many fields, read-only.
4. Match the compressed pick, then confirm with **use_when / refuse_when**.
5. Implement via DSL `display:` / region kind; do not invent a fourth board.

## Compressed pick

```
Primary axis is workflow STAGE (move cards across columns)?     → kanban
Primary axis is CLOCK / event history?                        → timeline
Primary axis is a single DAY schedule?                        → day_timeline
Primary axis is MY urgency / next action?                     → task_inbox
Primary axis is SHARED pool + claim/filter?                   → queue
Primary axis is multi-field inventory / admin table?          → list (table)
Primary axis is awareness / notifications?                    → activity_feed
Primary axis is service health rows?                          → status_list
Static FAQ / exclusive section disclosure (one open)?       → accordion
Primary axis is customer↔agent chat bubbles (thread)?       → conversation
Multi-image media strip (browse peers in a stage)?          → carousel
Spatial pins on a plan/board (no tile SDK)?                 → map (marker)
```

## Decision table (job → surface)

| If the primary job is… | **Use** | **Do not use** |
|------------------------|---------|----------------|
| Pull/prioritize work across **3–7 stages**; WIP visible by column | **kanban** | timeline, dense multi-column table |
| Read **dated events** in order (audit, payments, status changes) | **timeline** | kanban (unless stages are the job) |
| Place or review **blocks on one calendar day** | **day_timeline** | multi-week timeline, kanban |
| **My** next work ranked by SLA/urgency | **task_inbox** | kanban ceremony for one person |
| **Team pool** with filters + claim | **queue** | personal inbox, stage board |
| Compare **many fields** / search / bulk admin | **list** / table | kanban (cards hide columns) |
| **Feed** of activity to acknowledge | **activity_feed** | task completion inbox |
| **Health** of services/resources at a glance | **status_list** | kanban |

## Utility (why this is better than “any list”)

| Surface | Utility you buy | Cost if wrong |
|---------|-----------------|---------------|
| kanban | Stage progress + cheap stage mutation | Stage noise; time/urgency lost |
| timeline | Temporal truth + attention bullets | Cannot rebalance WIP by stage |
| task_inbox | Fast top-item action | Hides team stage ceremony |
| queue | Policy pull from shared pool | Weak personal ranking UX |
| list | Field comparison / density | Slow stage intuition |
| activity_feed | Awareness | Poor work completion path |

Full criteria: `work_surface_utility.toml` › `use_when` / `refuse_when` /
`utility_axes` / `measure_proxy`.

## Measuring improved utility (method)

When improve or a human **introduces** a new work surface (e.g. list → kanban):

1. **Fit residual (free, static)**
   `python scripts/work_surface_utility.py --app <example>`
   Count mismatches (DSL signals that imply surface A while display is B).
   **Success:** residual ↓ or stays 0 after the change.

2. **Opportunity / author_action**
   `dazzle qa hyperpart-opportunities -a <app>` (+ work-surface kinds).
   **Success:** author_action rows for that surface close.

3. **Trial friction delta**
   Same `trial.toml` journey before/after; compare `missing` / `confusion`
   severity on the workspace URL.
   **Success:** severity does not rise; preferably falls.

4. **Axis proxies (instrument later)**
   Each surface declares `measure_proxy` names (e.g. `time_to_first_stage_change`).
   Prefer those vocabulary tokens over one-off KPIs.

Do **not** claim utility from gallery aesthetics alone (coherence scores).
Coherence is “looks right in isolation”; this playbook is “right job in product.”

## Composition notes

- Kanban cards may compose **badge**, **avatar**, **confirm** on actions — use
  `compose-or-refuse.md` / `pick-a-surface.md` for L1 controls.
- Timeline is presentation-first; host owns any `hx-*` around it.
- Prefer **one** primary work surface per workspace; secondary related tables
  stay list/detail.

## Related

| Doc | When |
|-----|------|
| `pick-a-surface.md` | Controls (combobox, menu, dialog…) |
| `pick-a-measure.md` | Shell content width |
| `compose-or-refuse.md` | Host mounts L1 children |
| `work_surface_utility.toml` | Machine ontology + measure vocabulary |
| `site/agents/kanban.md` etc. | DOM / exchange for one stem |
