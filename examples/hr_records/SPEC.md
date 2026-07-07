# HR Records — Product Specification

> **Document Status**: First-draft specification ready for DSL generation
> **Complexity Level**: Intermediate (RBAC + temporal data)
> **DSL Features Exercised**: state-machine-free entity lifecycle, effective-dated rows, current-row resolution, hierarchical traversal (department tree + manager chain), RBAC scope rules differentiating tenant-wide vs team-only vs self-only
> **Phase 3 Design Pressure Target**: temporal / slowly-changing-dimension support (#1217 Pattern 7); secondary pressure on self-referencing hierarchy (#1217 Pattern 5)

---

## Vision Statement

A personnel system of record for a UK consulting firm of ~50 staff. The system answers four classes of question authoritatively: *who works here right now*, *who worked here and when*, *what they're paid and how that's changed*, and *how the reporting structure looks today (or on any past date)*. It is the canonical source for downstream payroll, finance, and access-management systems; it does **not** itself run payroll or manage tax codes.

The point of the system is **history**. Hiring someone, promoting them, raising their salary, changing their manager, and offboarding them are all *temporal facts* — each event opens a new row and closes the previous one. Every entity that describes a person's relationship to the firm carries `start_date` / `end_date` and is queried predominantly via "what is true *now*" (or "what was true *then*").

---

## User Personas

### HR Admin (`hr_admin`)
- **Scope**: Full CRUD across all entities, all people, all history
- **Daily use**: Onboarding new starters, processing promotions, handling leavers, correcting historical records (back-dated joiners, retroactive salary changes)
- **Mental model**: thinks in events ("Alice was promoted to Senior on 2026-04-01") rather than current state

### Line Manager (`manager`)
- **Scope**: Read access to own direct reports (current and historical reports); read-only on their compensation; can submit promotion/salary-change *requests* (not change records directly)
- **Daily use**: Quarterly performance reviews, team headcount planning, salary benchmarking against role-level peers
- **Mental model**: thinks in *people on my team right now*, occasionally "team six months ago vs today"

### Finance (`finance`)
- **Scope**: Read all salary data + employment history (no manager hierarchy, no contact details)
- **Daily use**: Salary band analysis by department + role-level, monthly cost-of-employment rollups, year-on-year compensation trend
- **Mental model**: aggregates over current-only rows for monthly reports; full history for trend analysis

### Employee (`employee`)
- **Scope**: Read self only — own employment history, own salary history, own current manager
- **Daily use**: Confirming the system is correct after a promotion or salary review; viewing their own career timeline
- **Mental model**: a personal record of "what's happened to me here"

### Out of scope: applicant / candidate
- Recruitment is upstream; the system only knows people *from* their first employment row onwards.

---

## Domain Model

### Entity: `Person`

A staff member, past or present. The identity record — name, contact details, the date they first started. **Does not carry current role, current salary, or current manager** — those are derived from the temporal entities below.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | UUID | Yes | PK |
| `legal_name` | str(200) | Yes | Full legal name for HMRC/contracts |
| `preferred_name` | str(100) | No | Display name in UI |
| `email` | email | Yes | Unique; work email |
| `started_at` | date | Yes | First day at the firm — **not** the start of any individual Employment row, but the firm-wide anchor for tenure calculations |
| `ended_at` | date? | No | If set, the person has left the firm; downstream temporal rows should be closed on or before this date |

### Entity: `Department`

A unit within the firm. Departments form a tree via `parent_department` — Engineering has Frontend, Backend, Platform; Sales has Direct Sales and Channel Partners.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | UUID | Yes | PK |
| `name` | str(150) | Yes | Unique within parent (Engineering / Frontend ≠ Sales / Frontend) |
| `parent_department` | ref Department? | No | Nullable for top-level depts; self-reference exercises Pattern 5 |

### Entity: `Role`

A job title with a career level. "Software Engineer" at level "IC2", "Senior Engineer" at "IC3", "Engineering Manager" at "M1". The role is a catalogue entry; people don't *own* roles, they *hold* them via Employment rows.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | UUID | Yes | PK |
| `title` | str(150) | Yes | Display title |
| `level` | enum[ic1, ic2, ic3, ic4, ic5, ic6, m1, m2, m3, m4] | Yes | Career framework level |
| `department` | ref Department | Yes | Roles belong to a department (Engineering's "Software Engineer" is distinct from Sales's "Account Executive") |

### Entity: `Employment` ← **Pattern 7 temporal core**

The record of "person X held role Y in department Z, from start_date to end_date." A Person typically has one *active* Employment at a time (end_date IS NULL); historical rows are closed by setting end_date. Promotions = close the old row + open a new one with the same effective_date.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | UUID | Yes | PK |
| `person` | ref Person | Yes |  |
| `role` | ref Role | Yes |  |
| `department` | ref Department | Yes | Denormalised from `role.department` for as-of queries — a role might move departments later, but the historical employment should remember the department-at-the-time |
| `start_date` | date | Yes |  |
| `end_date` | date? | No | NULL = currently active. Invariant: at most one row per person where end_date IS NULL. |
| `notes` | text? | No | Free-form (e.g., "Promoted from IC2", "Joined via acquisition") |

### Entity: `Salary` ← **Pattern 7 temporal core**

The record of "person X earned £Y from effective_from to effective_to." Same temporal shape as Employment.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | UUID | Yes | PK |
| `person` | ref Person | Yes |  |
| `amount` | money | Yes | Annual gross — stored as minor units + currency code (default GBP) |
| `effective_from` | date | Yes |  |
| `effective_to` | date? | No | NULL = currently active. Invariant: at most one row per person where effective_to IS NULL. |
| `reason` | enum[new_hire, promotion, market_adjustment, annual_review, correction] | Yes | Why this salary level applied — useful for trend analysis |

### Entity: `ManagerLink` ← **Pattern 7 + Pattern 5 (temporal self-ref)**

"Person X reported to person Y, from start_date to end_date." Re-orgs and manager changes are tracked here; both sides of the link are `ref Person`.

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | UUID | Yes | PK |
| `report` | ref Person | Yes | The person being managed |
| `manager` | ref Person | Yes | The manager |
| `start_date` | date | Yes |  |
| `end_date` | date? | No | NULL = currently active. Invariant: at most one row per `report` where end_date IS NULL. |

A Person *can* have multiple direct reports active simultaneously (the inverse — being a manager — is unconstrained), but can only *be reported by* at most one person at a time (or zero, for the top of the org).

---

## Key User Flows

### 1. Onboarding a new starter (HR Admin)
- Create `Person` (legal_name, preferred_name, email, started_at)
- Create initial `Employment` (person, role, department, start_date = started_at, end_date = NULL)
- Create initial `Salary` (person, amount, effective_from = started_at, effective_to = NULL, reason = new_hire)
- Create initial `ManagerLink` (report = new person, manager = chosen, start_date = started_at, end_date = NULL)
- Four entity creates, all sharing the same effective date.

### 2. Processing a promotion (HR Admin)
On the effective date:
- Close the current `Employment` row (set end_date = effective_date - 1 day)
- Open a new `Employment` row (new role, possibly new department, start_date = effective_date, end_date = NULL)
- Close the current `Salary` row (set effective_to = effective_date - 1 day)
- Open a new `Salary` row (new amount, effective_from = effective_date, effective_to = NULL, reason = promotion)
- ManagerLink usually unchanged.

### 3. Manager change (HR Admin)
- Close the current `ManagerLink` for the report (set end_date)
- Open a new `ManagerLink` (new manager, start_date, end_date = NULL)

### 4. Leaver (HR Admin)
- Set `Person.ended_at`
- Close all currently-active temporal rows for the person — Employment, Salary, ManagerLink — to the same end_date

### 5. Manager views team (Line Manager)
- Filtered list of all `ManagerLink` rows where `manager = current_user.person` and `end_date IS NULL`
- For each, resolve current Employment + current Salary (NULL is_finance) of the report
- Default sort: by report's legal_name

### 6. Compensation review dashboard (Finance)
- For each Department: sum/avg current Salary amount across all people whose current Employment is in that department
- Group by Role.level (compare IC2 salaries across departments)
- Year-on-year: compare current salaries against salaries that were active 12 months ago (uses historical Salary rows)

### 7. Time-machine view (HR Admin)
- Date picker at the top of the page selects an as-of date
- Staff directory re-projects to show employment + salary + manager *as of* that date
- Org chart re-projects to show reporting structure *as of* that date
- This is the most demanding query class — every entity needs to be filterable by "row whose start_date ≤ as_of AND (end_date IS NULL OR end_date > as_of)"

### 8. Employee self-service (Employee)
- View own profile — current role, current salary, current manager
- View own Employment history timeline (all rows, ordered by start_date)
- View own Salary history timeline (all rows, ordered by effective_from)

---

## Workspace Surfaces

### Workspace: `staff_directory` (default landing for hr_admin + manager)
- **Staff list** — current employees (active Employment), columns: name, role, department, manager
- **Filters**: by department, by role level, by "starting in last 90 days", by "ended in last 90 days"
- **Sort**: by name, by tenure (started_at desc), by department
- For `manager` persona: scoped to own reports

### Workspace: `person_detail`
- **Header**: name, email, tenure, current role+department
- **Tabs**:
  - **Employment history** — timeline of Employment rows
  - **Salary history** — timeline of Salary rows (hr_admin + finance + self only)
  - **Reporting line** — current manager + (if applicable) current direct reports

### Workspace: `org_chart`
- Department tree (uses Department.parent_department recursive descent)
- For each department: count of currently-active employees
- For each currently-active person: their place in the manager chain (drill-down via ManagerLink)

### Workspace: `compensation_review` (finance + hr_admin only)
- Total annual cost-of-employment, broken down by department, by role level
- Average salary by role level + department (cross-tab)
- Distribution histogram per role level (boxplot would be nice but not in scope)
- Compare current totals to "12 months ago" totals using historical Salary rows

### Workspace: `time_machine` (hr_admin only)
- Date picker (the as-of input)
- When a date is picked, the staff_directory + org_chart re-project to that date
- The picker defaults to today (giving the current state); choosing a past date is the historical projection

---

## RBAC Sketch

| Persona | Person | Department | Role | Employment | Salary | ManagerLink |
|---|---|---|---|---|---|---|
| hr_admin | CRUD all | CRUD all | CRUD all | CRUD all | CRUD all | CRUD all |
| manager | R own reports + self | R all | R all | R own reports + self | — (none) | R links where I am manager or report |
| finance | R all (no contact) | R all | R all | R all | R all | — (none) |
| employee | R self | R all | R all | R self | R self | R links where I am report |

The "manager scope" requires walking the *current* ManagerLink graph — itself a temporal entity. This is the demonstration that RBAC scope rules need first-class temporal awareness.

---

## Out of Scope (Explicit Non-Goals)

- Payroll calculations, tax codes, NI numbers
- Leave / time-off / sick pay
- Performance reviews, 1:1s, goals
- Recruitment / candidate pipeline
- Equity, bonuses, benefits packages
- Multi-currency conversion for reporting (salaries stored in their native currency; reports compare like-with-like)
- Document storage (contracts, right-to-work evidence)
- Two-way sync with payroll / finance systems
- Audit log (the framework already provides `audit on Entity:` — this example would use it; we just don't spec it here)

---

## Phase 3 Design Pressure — Expected DSL Gaps

The whole point of this example is to *surface* what current Dazzle DSL can't express cleanly. Predictions (each becomes a Phase 3 issue line item):

1. **No first-class "current row" relationship** — `Person.current_employment` requires hand-rolled `latest_one` or compute fields with `where end_date = null`
2. **No entity-level `default_scope`** — every read surface must repeat `scope: end_date = null` instead of declaring it once on `Employment` itself
3. **No "at most one active row per key" constraint** — the invariant "one active Employment per Person" can't be expressed; it's a runtime check or a DB unique index on `(person, end_date)` with NULL-only-once semantics
4. **No `as_of: date` URL query param** — the time-machine workspace would need a bespoke query handler per surface
5. **No first-class temporal entity shape** — `Employment` and `Salary` have the same `start_date / end_date` shape repeated by hand; no declarative `temporal: start_date, end_date` keyword
6. **Aggregates over current-only rows are verbose** — `cohort_strip` with `primary_aggregate` needs the same `where end_date = null` repeated for every lens
7. **No recursive `descendants of` traversal** — both `Department.parent_department` and `ManagerLink` chains need recursive CTE support; today users hand-roll via Python service stubs
8. **RBAC scope rules can't traverse temporal links cleanly** — the `manager` persona's scope ("see my reports") needs to evaluate the *current* `ManagerLink`, which scope predicates can't express without `current_for:` or similar

Each of these is a candidate Phase 3 line item. The DSL we generate next will mark each gap with a `# TODO(#NNNN-temporal):` block showing the desired syntax adjacent to the hand-rolled workaround.
