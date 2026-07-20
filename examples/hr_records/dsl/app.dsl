module hr_records.core
app hr_records "HR Records"

# =============================================================================
# HR Records — Phase 3 design-pressure surface (#1217 + #1218 follow-ups)
# =============================================================================
#
# This example is deliberately authored as a credible HR system. The point is
# to surface — through real DSL — the temporal / effective-dated patterns that
# current Dazzle can't express cleanly. Each gap is marked with a comment
# block of the form:
#
#   # TODO(#hr-temporal): description of the syntax we wished for
#   # ----- IF DAZZLE SUPPORTED IT, WE'D WRITE: -----
#   # <desired DSL>
#   # ------------------------------------------------
#
# The hand-rolled workaround sits underneath. When Phase 3 temporal support
# lands, each block collapses to the desired form.
#
# Domain: ~50-person UK consulting firm. See SPEC.md for full vision, personas,
# user flows, RBAC sketch, and out-of-scope list.
# =============================================================================


# =============================================================================
# PERSONAS
# =============================================================================

persona hr_admin "HR Admin":
  description: "Full CRUD across all entities and history. Thinks in events."
  default_workspace: staff_directory
  # WI N: job desks first — not auto entity-list soup
  uses nav hr_admin_nav

persona manager "Line Manager":
  description: "Read own direct reports (current and historical). No salary access."
  default_workspace: my_team
  uses nav manager_nav

persona finance "Finance":
  description: "Read all salary data + employment history. No manager hierarchy."
  default_workspace: compensation_review
  uses nav finance_nav

persona employee "Employee":
  description: "Read self only — own employment + salary history + current manager."
  default_workspace: person_detail
  uses nav employee_nav

# Curated sidebars: workspace destinations only (WI primary N).
nav hr_admin_nav:
  group "People":
    staff_directory
    my_team
    starters_desk
    person_detail
    reporting_desk
    employment_ops
    leavers_ops
    managers_ops
    active_staff
  group "Org & pay":
    org_chart
    compensation_review
    salary_ops
    role_ops
    dept_ops
    time_machine

nav manager_nav:
  group "Team":
    my_team
    staff_directory
    person_detail
    org_chart
    reporting_desk
    employment_ops
    salary_ops
    role_ops
    leavers_ops
    dept_ops
    managers_ops
    active_staff

nav finance_nav:
  group "Compensation":
    compensation_review
    salary_ops
    role_ops
    dept_ops
    staff_directory
    person_detail
    employment_ops
    active_staff

nav employee_nav:
  group "My record":
    person_detail
    staff_directory


# =============================================================================
# DEPARTMENT — exercises self-referencing hierarchy (#1217 Pattern 5)
# =============================================================================
#
# Departments form a tree. Engineering → Frontend, Backend, Platform.
# Sales → Direct Sales, Channel Partners. Top-level departments have
# parent_department = null.
# =============================================================================

entity Department "Department":
  intent: "Org unit. Self-referencing parent_department forms a tree."

  display_field: name
  id: uuid pk
  name: str(150) required
  parent_department: ref Department    # NULL for top-level

  # TODO(#hr-hierarchy): no DSL for recursive descendant traversal.
  # ----- IF DAZZLE SUPPORTED IT, WE'D WRITE: -----
  # all_descendants: descendants of self via parent_department
  # # auto-generates a recursive CTE; usable in scope rules, list filters,
  # # and cohort_strip sources. Powers the org-chart workspace + the
  # # "all engineers under VP" RBAC scope without hand-rolled Python.
  # ------------------------------------------------

  permit:
    create: role(hr_admin)
    read: role(hr_admin) or role(manager) or role(finance) or role(employee)
    update: role(hr_admin)
    delete: role(hr_admin)
    list: role(hr_admin) or role(manager) or role(finance) or role(employee)

  scope:
    create: all
      as: hr_admin
    read: all
      as: hr_admin, manager, finance, employee
    update: all
      as: hr_admin
    delete: all
      as: hr_admin
    list: all
      as: hr_admin, manager, finance, employee

  audit: all


# =============================================================================
# ROLE — job-title catalogue with career framework level
# =============================================================================

entity Role "Role":
  intent: "Catalogue of job titles. People hold roles via Employment rows."

  display_field: title
  id: uuid pk
  title: str(150) required
  level: enum[ic1, ic2, ic3, ic4, ic5, ic6, m1, m2, m3, m4] required
  department: ref Department required

  permit:
    create: role(hr_admin)
    read: role(hr_admin) or role(manager) or role(finance) or role(employee)
    update: role(hr_admin)
    delete: role(hr_admin)
    list: role(hr_admin) or role(manager) or role(finance) or role(employee)

  scope:
    create: all
      as: hr_admin
    read: all
      as: hr_admin, manager, finance, employee
    update: all
      as: hr_admin
    delete: all
      as: hr_admin
    list: all
      as: hr_admin, manager, finance, employee


# =============================================================================
# PERSON — staff identity record (no current-role / current-salary fields —
# those are derived from temporal entities below)
# =============================================================================

entity Person "Person":
  intent: "Staff member, past or present. Identity record with temporal lifecycle (started_at → ended_at). Per-period facts (role, salary, manager) are in Employment/Salary/ManagerLink."

  display_field: legal_name
  id: uuid pk
  legal_name: str(200) required pii(category=identity)
  preferred_name: str(100) pii(category=identity)
  email: email required unique pii(category=contact)
  started_at: date required
  ended_at: date    # NULL = currently employed

  # #1223: Person uses `temporal:` even though it's an identity record
  # (not an interval relationship). key_field: id makes the "at most
  # one active per key" constraint degenerate (id is already unique),
  # but the auto-filter behaviour is what we want: list/read paths hide
  # ex-employees by default. Append `?include_closed=true` to see them.
  temporal:
    start_field: started_at
    end_field: ended_at
    key_field: id

  # #1223 Phase 3a.v + .v.ii — current_employment / current_salary
  # resolve at read time. GET /api/person/<id> includes both as
  # nested objects (or null if the person isn't currently employed).
  current_employment: latest_one Employment via person
  current_salary: latest_one Salary via person

  permit:
    create: role(hr_admin)
    read: role(hr_admin) or role(manager) or role(finance) or role(employee)
    update: role(hr_admin)
    delete: role(hr_admin)
    list: role(hr_admin) or role(manager) or role(finance) or role(employee)

  scope:
    create: all
      as: hr_admin
    read: all
      as: hr_admin, finance
    update: all
      as: hr_admin
    delete: all
      as: hr_admin
    list: all
      as: hr_admin, finance

    # TODO(#hr-temporal): RBAC scope rules can't traverse temporal links cleanly.
    # The `manager` persona's scope should resolve "people I currently manage"
    # via ManagerLink where end_date IS NULL — but scope predicates can't
    # express the temporal filter. The workaround below evaluates the entire
    # ManagerLink table for matching reports, which would include past reports
    # (people who used to report to me but no longer do).
    # ----- IF DAZZLE SUPPORTED IT, WE'D WRITE: -----
    # read: id in (select report from ManagerLink current where manager = current_user.person)
    #   as: manager
    # ------------------------------------------------
    # Hand-rolled (returns ALL historical reports, not just current):
    read: via ManagerLink(manager = current_user.person, report = id)
      as: manager
    list: via ManagerLink(manager = current_user.person, report = id)
      as: manager

    # Employee sees self only.
    read: id = current_user.person
      as: employee
    list: id = current_user.person
      as: employee

  audit: all


# =============================================================================
# EMPLOYMENT — temporal core (#1217 Pattern 7)
# =============================================================================
#
# "Person held role in department from start_date to end_date." Promotions:
# close the old row, open a new one with the same effective date.
#
# Invariant we want: at most one row per person where end_date IS NULL.
# Current DSL: no way to express that constraint; enforced at app/DB level.
# =============================================================================

entity Employment "Employment":
  intent: "Effective-dated record of role/department assignment. NULL end_date = currently active."

  id: uuid pk
  person: ref Person required
  role: ref Role required
  department: ref Department required    # denormalised — role may move dept later
  start_date: date required
  end_date: date    # NULL = currently active

  notes: text

  # #1223 Phase 3a.i (v0.71.161) — IR + parser shipped. Runtime
  # consumers (tombstone filter on read paths, ?as_of= URL param,
  # "at most one active per key" constraint, current-row resolution)
  # land in subsequent slices (3a.ii–3a.v). DSL authoring works today;
  # this block has no runtime effect yet.
  temporal:
    start_field: start_date
    end_field: end_date
    key_field: person

  permit:
    create: role(hr_admin)
    read: role(hr_admin) or role(manager) or role(finance) or role(employee)
    update: role(hr_admin)
    delete: role(hr_admin)
    list: role(hr_admin) or role(manager) or role(finance) or role(employee)

  scope:
    create: all
      as: hr_admin
    read: all
      as: hr_admin, finance
    update: all
      as: hr_admin
    delete: all
      as: hr_admin
    list: all
      as: hr_admin, finance

    # Manager sees employment rows of their (currently/historically) reports.
    # Same temporal-traversal gap as Person.
    read: via ManagerLink(manager = current_user.person, report = person)
      as: manager
    list: via ManagerLink(manager = current_user.person, report = person)
      as: manager

    # Employee sees own employment history (all rows, including closed).
    read: person = current_user.person
      as: employee
    list: person = current_user.person
      as: employee

  audit: all


# =============================================================================
# SALARY — temporal core, same shape as Employment
# =============================================================================

entity Salary "Salary":
  intent: "Effective-dated compensation record. NULL effective_to = currently active."

  id: uuid pk
  person: ref Person required
  # First-class money type: expands to amount_minor (int, smallest
  # unit) + amount_currency (code) columns; the form renders the HM
  # money widget (currency-aware decimal input, minor-unit carrier).
  amount: money required
  effective_from: date required
  effective_to: date    # NULL = currently active

  reason: enum[new_hire, promotion, market_adjustment, annual_review, correction] required

  # #1223 Phase 3a.i (v0.71.161) — IR + parser shipped. Same shape as
  # Employment.temporal, different field names.
  temporal:
    start_field: effective_from
    end_field: effective_to
    key_field: person

  permit:
    create: role(hr_admin)
    read: role(hr_admin) or role(finance) or role(employee)    # NOT manager
    update: role(hr_admin)
    delete: role(hr_admin)
    list: role(hr_admin) or role(finance) or role(employee)

  scope:
    create: all
      as: hr_admin
    read: all
      as: hr_admin, finance
    update: all
      as: hr_admin
    delete: all
      as: hr_admin
    list: all
      as: hr_admin, finance

    # Employee sees own salary history.
    read: person = current_user.person
      as: employee
    list: person = current_user.person
      as: employee

  audit: all


# =============================================================================
# MANAGERLINK — temporal self-reference (#1217 Pattern 5 + Pattern 7)
# =============================================================================
#
# Records who reported to whom and when. Self-referencing via two `ref Person`
# fields (report + manager). At most one row per `report` where end_date IS
# NULL (a person has at most one current manager).
# =============================================================================

entity ManagerLink "Manager Link":
  intent: "Effective-dated reporting line. NULL end_date = current."

  id: uuid pk
  report: ref Person required
  manager: ref Person required
  start_date: date required
  end_date: date    # NULL = currently active

  # #1223 Phase 3a.i (v0.71.161) — IR + parser shipped. The key_field
  # is `report` here: a person can be reported-by at most one manager
  # at a time, but `manager` is unconstrained (one person can have
  # many direct reports active simultaneously).
  temporal:
    start_field: start_date
    end_field: end_date
    key_field: report

  # TODO(#hr-hierarchy): no recursive 'manager chain' / 'all reports under'
  # traversal in DSL. Use cases: "show me every IC under VP of Engineering",
  # "is X anywhere in my reporting line", "skip-level 1:1 candidates".
  # ----- IF DAZZLE SUPPORTED IT, WE'D WRITE: -----
  # all_reports_under: descendants of report via ManagerLink.manager where end_date = null
  # ------------------------------------------------

  permit:
    create: role(hr_admin)
    read: role(hr_admin) or role(manager) or role(employee)
    update: role(hr_admin)
    delete: role(hr_admin)
    list: role(hr_admin) or role(manager) or role(employee)

  scope:
    create: all
      as: hr_admin
    read: all
      as: hr_admin
    update: all
      as: hr_admin
    delete: all
      as: hr_admin
    list: all
      as: hr_admin

    # Manager sees rows where they are the manager OR the report.
    read: manager = current_user.person or report = current_user.person
      as: manager
    list: manager = current_user.person or report = current_user.person
      as: manager

    # Employee sees rows where they are the report.
    read: report = current_user.person
      as: employee
    list: report = current_user.person
      as: employee

  audit: all


# =============================================================================
# SURFACES — minimal CRUD coverage. Only what the workspaces below need to
# function; this isn't a full HR admin tool, it's a Phase 3 design-pressure
# surface.
# =============================================================================

surface person_list "People":
  uses entity Person
  mode: list
  open: Person via id
  section main:
    field legal_name "Legal name"
    field preferred_name "Preferred name"
    field email "Email"
    field started_at "Started"
  ux:
    purpose: "Staff directory — open a row for the person career hub"

surface person_detail "Person":
  uses entity Person
  mode: view
  section identity "Identity":
    field legal_name "Legal name"
    field preferred_name "Preferred name"
    field email "Email"
  section tenure "Tenure":
    layout: strip
    field started_at "Started"
    field ended_at "Ended (NULL = active)"
  related employment "Employment history":
    display: table
    show: Employment
    columns: role, department, start_date, end_date
  related compensation "Salary history":
    display: table
    show: Salary
    columns: amount, effective_from, effective_to, reason
  related reporting "Reporting lines":
    display: table
    show: ManagerLink
  ux:
    purpose: "Person hub — identity, tenure strip, employment and salary history"

surface person_create "Add Person":
  uses entity Person
  mode: create
  section main:
    field legal_name "Legal name"
    field preferred_name "Preferred name"
    field email "Email"
    field started_at "Start date"

surface person_edit "Edit Person":
  uses entity Person
  mode: edit
  section main:
    field legal_name "Legal name"
    field preferred_name "Preferred name"
    field email "Email"
    field ended_at "Ended"

surface department_list "Departments":
  uses entity Department
  mode: list
  # WI G: graph hop into department hub (not a dead warehouse row)
  open: Department via id
  section main:
    field name "Name"
    field parent_department "Parent"
  ux:
    purpose: "Org units — open a row for the department hub"

surface department_detail "Department":
  uses entity Department
  mode: view
  section main "Unit":
    field name "Name"
    field parent_department "Parent"
  related roles "Roles in unit":
    display: table
    show: Role
  ux:
    purpose: "Department hub — unit identity and roles"

surface department_create "Add Department":
  uses entity Department
  mode: create
  section main:
    field name "Name"
    field parent_department "Parent (optional)"

surface role_list "Roles":
  uses entity Role
  mode: list
  open: Role via id
  section main:
    field title "Title"
    field level "Level"
    field department "Department"
  ux:
    purpose: "Job roles — open a row for the role hub"

surface role_detail "Role":
  uses entity Role
  mode: view
  section main "Role":
    field title "Title"
    field level "Level"
    field department "Department"
  related employment "Employment in role":
    display: table
    show: Employment
  ux:
    purpose: "Role hub — title, level, and employment history"

surface role_create "Add Role":
  uses entity Role
  mode: create
  section main:
    field title "Title"
    field level "Level"
    field department "Department"

# TODO(#hr-temporal-flow): multi-entity onboarding flow.
# ----- IF DAZZLE SUPPORTED IT, WE'D WRITE: -----
# surface onboard_starter "Onboard Starter":
#   flow: atomic_create
#   creates:
#     - Person(legal_name, preferred_name, email, started_at)
#     - Employment(person = above.Person.id, role, department, start_date = above.Person.started_at)
#     - Salary(person = above.Person.id, amount, effective_from = above.Person.started_at, reason = new_hire)
#     - ManagerLink(report = above.Person.id, manager, start_date = above.Person.started_at)
#   on_failure: rollback_all
# ------------------------------------------------
# Hand-roll workaround today: four separate create surfaces + project-side
# coordination. Loses transactional atomicity.
surface employment_list "Employment history":
  uses entity Employment
  mode: list
  open: Person via person
  section main:
    field person "Person"
    field role "Role"
    field department "Department"
    field start_date "Start"
    field end_date "End"
  ux:
    purpose: "Employment history — open a row for the person career hub"

surface employment_create "Start Employment":
  uses entity Employment
  mode: create
  section main:
    field person "Person"
    field role "Role"
    field department "Department"
    field start_date "Start date"

surface employment_edit "End / Update Employment":
  uses entity Employment
  mode: edit
  section main:
    field end_date "End date (set to close)"
    field notes "Notes"

surface salary_list "Salary history":
  uses entity Salary
  mode: list
  open: Person via person
  section main:
    field person "Person"
    field amount "Amount"
    field effective_from "From"
    field effective_to "To"
    field reason "Reason"
  ux:
    purpose: "Salary history — open a row for the person career hub"

surface salary_create "New Salary":
  uses entity Salary
  mode: create
  section main:
    field person "Person"
    field amount "Amount"
    field effective_from "Effective from"
    field reason "Reason"

surface salary_edit "Close Salary":
  uses entity Salary
  mode: edit
  section main:
    field effective_to "Effective to (set to close)"

surface managerlink_create "Assign Manager":
  uses entity ManagerLink
  mode: create
  section main:
    field report "Report"
    field manager "Manager"
    field start_date "Effective from"

surface managerlink_edit "End Reporting Line":
  uses entity ManagerLink
  mode: edit
  section main:
    field end_date "End date"


# =============================================================================
# WORKSPACES
# =============================================================================
#
# #1223 Phase 3a.iv shipped `?as_of=YYYY-MM-DD` as a per-temporal-entity
# URL parameter. Any list/aggregate/read endpoint backed by a temporal
# entity automatically re-projects when the URL carries the param. The
# `time_machine` workspace below exercises this by stacking regions
# whose sources are all temporal entities — appending `?as_of=2025-06-01`
# to its URL re-projects every region to that historical snapshot.
# =============================================================================


# WI L: hr_admin default landing — denser regions (cap 6).
workspace staff_directory "Staff Directory":
  access: persona(hr_admin, manager, finance, employee)
  purpose: "Current employees, filterable by department + level"

  # Job strip first — counts before the dense directory list.
  headcount:
    source: Person
    display: metrics
    aggregate:
      people: count(Person)
      departments: count(Department)
      roles: count(Role)
      employment_rows: count(Employment)
    tones:
      people: accent

  current_staff:
    source: Person
    display: queue
    limit: 25
    action: person_detail
    empty: "No people on record"
    # TODO(#hr-temporal): `default_scope: where ended_at = null` on the
    # Person entity would obviate this region-level filter. Today we'd
    # need a `filter:` block here — but the example exists to demonstrate
    # the gap, so the region is unfiltered and the list shows everyone.

  recent_starters:
    source: Person
    display: list
    limit: 15
    action: person_detail
    empty: "No recent joiners listed"
    # TODO(#hr-temporal): "filter: started_at > today - 90d" — date
    # arithmetic in filters isn't first-class for list region filters
    # outside aggregate where clauses.

  department_context:
    source: Department
    display: list
    limit: 15
    action: department_detail
    empty: "No departments"

  role_context:
    source: Role
    display: list
    limit: 15
    action: role_detail
    empty: "No roles"

  directory_readiness:
    display: status_list
    entries:
      - title: "Person hub"
        caption: "Open a person for employment + salary career timeline"
        icon: "user"
        state: accent
      - title: "Starters desk"
        caption: "Onboarding queue lives on New Starters"
        icon: "user-plus"
        state: positive

  # WI D: grid family for people cards
  people_cards:
    source: Person
    display: grid
    limit: 20
    action: person_detail
    empty: "No people on record"

  # WI D: chart family — employment rows by department
  dept_mix:
    source: Employment
    display: bar_chart
    group_by: department
    aggregate:
      count: count(Employment)
    empty: "No employment rows"


# WI L: employee default landing — denser career desk.
workspace person_detail "Person Detail":
  access: persona(hr_admin, manager, finance, employee)
  purpose: "Career timeline — employment + salary history side-by-side"

  # TODO(#hr-temporal): "history timeline" display mode.
  # A region whose source is a temporal entity (Employment / Salary) and
  # which renders each row as a horizontal lane on a date axis, ordered
  # by start_field. Currently fieldtest_hub has a `display: timeline` for
  # event-style data, but no shape for open-interval temporal rows.
  # ----- IF DAZZLE SUPPORTED IT, WE'D WRITE: -----
  # employment_timeline:
  #   source: Employment
  #   display: temporal_timeline
  #   temporal_timeline_config:
  #     start_field: start_date
  #     end_field: end_date
  #     label: "{{ role.title }} ({{ department.name }})"
  # ------------------------------------------------
  career_pulse:
    source: Employment
    display: metrics
    aggregate:
      employment_rows: count(Employment)
      salary_rows: count(Salary)
      reporting_lines: count(ManagerLink)
    tones:
      employment_rows: accent

  employment_history:
    source: Employment
    display: queue
    limit: 20
    empty: "No employment rows"

  salary_history:
    source: Salary
    display: list
    limit: 15
    empty: "No salary rows"

  reporting_history:
    source: ManagerLink
    display: list
    limit: 15
    empty: "No reporting lines on record"

  org_context:
    source: Department
    display: list
    limit: 10
    action: department_detail
    empty: "No departments"

  record_hint:
    display: status_list
    entries:
      - title: "Your record"
        caption: "Employment and salary history scope to your person row"
        icon: "id-card"
        state: accent
      - title: "Directory"
        caption: "Browse colleagues from Staff Directory when permitted"
        icon: "users"
        state: positive

  # WI D: context family — employment trail
  employment_trail:
    source: Employment
    display: timeline
    limit: 15
    empty: "No employment rows"

  # WI D: chart family — salary reason mix
  salary_mix:
    source: Salary
    display: bar_chart
    group_by: reason
    aggregate:
      count: count(Salary)
    empty: "No salary rows"


# #1626 P0-7: honest name — not a true org *tree* until recursive_tree ships.
workspace org_chart "Departments & Roles":
  access: persona(hr_admin, manager)
  purpose: "Department roster, job roles, and reporting-line records (not a visual org tree yet)"

  org_pulse:
    source: Department
    display: metrics
    aggregate:
      departments: count(Department)
      roles: count(Role)
      reporting_lines: count(ManagerLink)
    tones:
      departments: accent

  # TODO(#hr-hierarchy): recursive tree for self-ref Department / ManagerLink.
  # WI D: grid family for department cards
  departments:
    source: Department
    display: grid
    action: department_detail
    empty: "No departments"

  # Job roles (title/level/department) are org reference data managed by
  # hr_admin — surfacing them here makes role_list/role_create reachable
  # from the workspace nav (was: defined but in no workspace → dead-construct
  # lint; #improve example-apps row 121).
  roles:
    source: Role
    display: queue
    limit: 25
    action: role_detail
    empty: "No roles"

  # TODO(#hr-hierarchy) + (#hr-temporal): manager chain visualisation.
  # The manager hierarchy is a temporal self-ref — drawing it requires
  # filtering ManagerLink to currently-active rows AND following the
  # `manager` FK recursively. Two pattern gaps compounded.
  reporting_lines:
    source: ManagerLink
    display: timeline
    limit: 20
    empty: "No reporting lines"

  # WI D: chart family — roles by level
  role_level_mix:
    source: Role
    display: bar_chart
    group_by: level
    aggregate:
      count: count(Role)
    empty: "No roles"


# WI L: finance default landing — denser regions (cap 6).
workspace compensation_review "Compensation Review":
  access: persona(hr_admin, finance)
  purpose: "Salary band analysis — by department, by role level"

  # Metrics-first finance job surface (story-to-composition).
  compensation_metrics:
    source: Salary
    display: metrics
    aggregate:
      active_salaries: count(Salary)
      people: count(Person)
      roles: count(Role)
      departments: count(Department)
    tones:
      active_salaries: accent

  # #1223 Phase 3a.ii — Salary is a temporal entity (declared above) with
  # default_filter: active, so every list / aggregate / read path against
  # it automatically filters to currently-active rows. Authors no longer
  # need `where effective_to = null` per lens — the framework injects it
  # via Repository's tombstone filter. This list region renders only
  # active salary rows by default; appending `?effective_to__isnull=false`
  # to the URL opts out for history views (the future `?include_closed`
  # hook from #1218 will surface this as a friendlier param).
  salary_queue:
    source: Salary
    display: queue
    limit: 25
    empty: "No active salaries"

  salary_list:
    source: Salary
    display: list
    limit: 20
    empty: "No active salaries"

  role_catalogue:
    source: Role
    display: list
    limit: 20
    action: role_detail
    empty: "No roles defined"

  headcount_context:
    source: Person
    display: list
    limit: 15
    action: person_detail
    empty: "No people on record"

  pay_readiness:
    display: status_list
    entries:
      - title: "Active salaries"
        caption: "Temporal default keeps closed bands out of the queue"
        icon: "banknote"
        state: accent
      - title: "Role catalogue"
        caption: "Levels and departments anchor band analysis"
        icon: "briefcase"
        state: positive

  # WI D: chart family — salary rows by reason
  reason_mix:
    source: Salary
    display: bar_chart
    group_by: reason
    aggregate:
      count: count(Salary)
    empty: "No active salaries"

  # WI D: grid family for people context
  people_cards:
    source: Person
    display: grid
    limit: 15
    action: person_detail
    empty: "No people on record"


workspace time_machine "Time Machine":
  access: persona(hr_admin)
  purpose: "Historical snapshot — append ?as_of=YYYY-MM-DD to re-project every region"

  # #1223 Phase 3a.iv shipped the as_of URL parameter as a per-temporal-
  # entity contract. Every region below has a temporal entity source
  # (Employment, Salary, ManagerLink), so URLs like
  #   /app/workspaces/time_machine?as_of=2025-06-01
  # automatically filter each region's source query to rows that were
  # active on 2025-06-01. Without the param, all three regions render
  # currently-active rows (same as default behaviour everywhere else).
  #
  # The workspace shell doesn't yet ship date-picker chrome — that's a
  # UI follow-up. For now the URL is editable by hand or via project-
  # side route override (e.g. a custom landing page that POSTs a date
  # form and redirects to the time_machine URL with ?as_of= appended).

  snapshot_pulse:
    source: Employment
    display: metrics
    aggregate:
      employment_rows: count(Employment)
      salary_rows: count(Salary)
      reporting_lines: count(ManagerLink)
    tones:
      employment_rows: accent

  employment_snapshot:
    source: Employment
    display: queue
    limit: 25
    empty: "No employment rows for this as-of"

  salary_snapshot:
    source: Salary
    display: grid
    limit: 20
    empty: "No salary rows for this as-of"

  reporting_lines_snapshot:
    source: ManagerLink
    display: timeline
    limit: 20
    empty: "No reporting lines for this as-of"

  # WI D: chart family — employment load in the snapshot
  employment_mix:
    source: Employment
    display: bar_chart
    group_by: department
    aggregate:
      count: count(Employment)
    empty: "No employment rows for this as-of"


# Sixth product workspace (WI density D): manager team desk — reports first,
# not a bare Person warehouse list.
# WI L: manager default landing — denser regions (cap 6).
workspace my_team "My Team":
  purpose: "Line manager desk — direct reports, roles, and reporting lines"
  access: persona(manager, hr_admin)

  team_pulse:
    source: Person
    display: metrics
    aggregate:
      people: count(Person)
      employment_rows: count(Employment)
      reporting_lines: count(ManagerLink)
      roles: count(Role)
    tones:
      people: accent

  reports:
    source: Person
    display: queue
    limit: 25
    action: person_detail
    empty: "No people in scope"

  team_employment:
    source: Employment
    display: list
    limit: 20
    empty: "No employment rows for your team"

  reporting_lines:
    source: ManagerLink
    display: list
    limit: 20
    empty: "No reporting lines yet"

  role_mix:
    source: Role
    display: list
    limit: 15
    action: role_detail
    empty: "No roles defined"

  team_readiness:
    display: status_list
    entries:
      - title: "Reports first"
        caption: "Open a person for career timeline without warehouse chrome"
        icon: "users"
        state: accent
      - title: "Reporting lines"
        caption: "ManagerLink history also lives on the Reporting desk"
        icon: "git-branch"
        state: positive

  # WI D: grid family for report cards
  report_cards:
    source: Person
    display: grid
    limit: 20
    action: person_detail
    empty: "No people in scope"

  # WI D: chart family — role mix on the team
  role_mix_chart:
    source: Role
    display: bar_chart
    group_by: level
    aggregate:
      count: count(Role)
    empty: "No roles defined"


# Seventh product workspace (WI density D): HR starters / onboarding desk.
workspace starters_desk "New Starters":
  purpose: "HR desk for recent joiners — headcount pulse and onboarding queue"
  access: persona(hr_admin)

  starter_pulse:
    source: Person
    display: metrics
    aggregate:
      people: count(Person)
      employment_rows: count(Employment)
      open_salaries: count(Salary)
    tones:
      people: accent

  recent_people:
    source: Person
    display: queue
    limit: 25
    action: person_detail
    empty: "No people on record"

  # WI D: grid family for starter cards
  starter_cards:
    source: Person
    display: grid
    limit: 20
    action: person_detail
    empty: "No people on record"

  # WI D: context family — employment trail
  employment_trail:
    source: Employment
    display: timeline
    limit: 15
    empty: "No employment rows yet"

  # WI D: chart family — salary setup by reason
  salary_mix:
    source: Salary
    display: bar_chart
    group_by: reason
    aggregate:
      count: count(Salary)
    empty: "No salary rows yet"

# Eighth product workspace (WI density D): reporting-line desk.
workspace reporting_desk "Reporting":
  purpose: "ManagerLink trail — who reports to whom across the org"
  access: persona(hr_admin, manager)

  reporting_pulse:
    source: ManagerLink
    display: metrics
    aggregate:
      links: count(ManagerLink)
      people: count(Person)
      departments: count(Department)
    tones:
      links: accent

  active_links:
    source: ManagerLink
    display: queue
    limit: 25
    empty: "No reporting lines yet"

  # WI D: grid family for people context
  people_cards:
    source: Person
    display: grid
    limit: 20
    action: person_detail
    empty: "No people on record"

  # WI D: context family — reporting trail
  link_trail:
    source: ManagerLink
    display: timeline
    limit: 20
    empty: "No reporting lines yet"

  # WI D: chart family — links by department context
  dept_mix:
    source: Department
    display: bar_chart
    group_by: name
    aggregate:
      count: count(Department)
    empty: "No departments"

  chain_hint:
    display: status_list
    entries:
      - title: "Temporal links"
        caption: "ManagerLink rows are time-bounded — use Time Machine for as-of snapshots"
        icon: "clock"
        state: accent
      - title: "Team desk"
        caption: "Line managers start from My Team for report-first work"
        icon: "users"
        state: positive

# Ninth product desk (WI D): 5 lists floor dens ~0.38 with 8 full desks — need 9.
workspace employment_ops "Employment Ops":
  purpose: "Employment pressure — active and ending assignments without warehouse CRUD"
  access: persona(hr_admin, manager, finance)

  employment_pulse:
    source: Employment
    display: metrics
    aggregate:
      assignments: count(Employment)
      people: count(Person)
      open_ended: count(Employment where end_date = null)
    tones:
      open_ended: positive
      assignments: accent

  # WI D: queue family — open-ended (current) assignments first
  active_queue:
    source: Employment
    filter: end_date = null
    sort: start_date desc
    limit: 25
    display: queue
    empty: "No active employments"

  # WI D: grid family — people context for HR ops
  people_grid:
    source: Person
    display: grid
    limit: 20
    action: person_detail
    empty: "No people on record"

  # WI D: context family — recent assignment trail
  assignment_trail:
    source: Employment
    sort: start_date desc
    limit: 15
    display: timeline
    empty: "No employment history yet"

  # WI D: chart family — department mix of roles via employment
  dept_mix:
    source: Department
    display: bar_chart
    group_by: name
    aggregate:
      count: count(Department)
    empty: "No departments"

# Tenth product desk (WI D): 5 lists floor dens ~0.36 with 9 full desks — need 10.
workspace salary_ops "Salary Ops":
  purpose: "Salary pressure — active compensation rows and change reasons without warehouse CRUD"
  access: persona(hr_admin, manager, finance)

  salary_pulse:
    source: Salary
    display: metrics
    aggregate:
      active: count(Salary where effective_to = null)
      rows: count(Salary)
      people: count(Person)
    tones:
      active: positive
      rows: accent

  # WI D: queue family — currently effective salaries first
  active_salary_queue:
    source: Salary
    filter: effective_to = null
    sort: effective_from desc
    limit: 25
    display: queue
    empty: "No active salaries"

  # WI D: grid family — people context for pay ops
  people_grid:
    source: Person
    display: grid
    limit: 20
    action: person_detail
    empty: "No people on record"

  # WI D: context family — recent compensation trail
  salary_trail:
    source: Salary
    sort: effective_from desc
    limit: 15
    display: timeline
    empty: "No salary history yet"

  # WI D: chart family — change-reason mix
  reason_mix:
    source: Salary
    display: bar_chart
    group_by: reason
    aggregate:
      count: count(Salary)
    empty: "No salary rows to chart"

# Eleventh product desk (WI D): 5 lists floor dens ~0.33 with 10 full desks — need 11.
workspace role_ops "Role Ops":
  purpose: "Role catalogue pressure — career levels and department spread without warehouse CRUD"
  access: persona(hr_admin, manager, finance)

  role_pulse:
    source: Role
    display: metrics
    aggregate:
      roles: count(Role)
      departments: count(Department)
      people: count(Person)
    tones:
      roles: accent
      departments: positive
      people: accent

  # WI D: queue family — roles by title
  role_queue:
    source: Role
    sort: title asc
    limit: 25
    display: queue
    empty: "No roles in the catalogue"

  # WI D: grid family — people context for staffing
  people_grid:
    source: Person
    display: grid
    limit: 20
    action: person_detail
    empty: "No people on record"

  # WI D: context family — active employment trail
  employment_trail:
    source: Employment
    filter: end_date = null
    sort: start_date desc
    limit: 15
    display: timeline
    empty: "No active employments yet"

  # WI D: chart family — career level mix
  level_mix:
    source: Role
    display: bar_chart
    group_by: level
    aggregate:
      count: count(Role)
    empty: "No roles to chart"

# Twelfth product desk (WI D): 5 lists floor dens ~0.31 with 11 full desks — need 12.
workspace leavers_ops "Leavers Ops":
  purpose: "Leaver pressure — ended assignments and offboarding trail without warehouse CRUD"
  access: persona(hr_admin, manager)

  leaver_pulse:
    source: Employment
    display: metrics
    aggregate:
      ended: count(Employment where end_date != null)
      active: count(Employment where end_date = null)
      people: count(Person)
    tones:
      ended: warning
      active: positive
      people: accent

  # WI D: queue family — ended assignments first
  ended_queue:
    source: Employment
    filter: end_date != null
    sort: end_date desc
    limit: 25
    display: queue
    empty: "No ended employments"

  # WI D: grid family — people context for offboarding
  people_grid:
    source: Person
    display: grid
    limit: 20
    action: person_detail
    empty: "No people on record"

  # WI D: context family — leaver trail
  leaver_trail:
    source: Employment
    filter: end_date != null
    sort: end_date desc
    limit: 15
    display: timeline
    empty: "No leaver history yet"

  # WI D: chart family — department mix
  dept_mix:
    source: Department
    display: bar_chart
    group_by: name
    aggregate:
      count: count(Department)
    empty: "No departments"

# Thirteenth product desk (WI D): skip invoice_ops desk-cap; densify hr_records.
workspace dept_ops "Dept Ops":
  purpose: "Department pressure — org units and staffing context without warehouse CRUD"
  access: persona(hr_admin, manager, finance)

  dept_pulse:
    source: Department
    display: metrics
    aggregate:
      departments: count(Department)
      roles: count(Role)
      people: count(Person)
    tones:
      departments: accent
      roles: positive
      people: accent

  # WI D: queue family — departments first
  dept_queue:
    source: Department
    sort: name asc
    limit: 25
    display: queue
    empty: "No departments"

  # WI D: grid family — people context
  people_grid:
    source: Person
    display: grid
    limit: 20
    action: person_detail
    empty: "No people on record"

  # WI D: context family — active employment trail
  employment_trail:
    source: Employment
    filter: end_date = null
    sort: start_date desc
    limit: 15
    display: timeline
    empty: "No active employments yet"

  # WI D: chart family — role level mix across the org
  level_mix:
    source: Role
    display: bar_chart
    group_by: level
    aggregate:
      count: count(Role)
    empty: "No roles to chart"

# Fourteenth product desk (WI D): skip invoice_ops desk-cap; densify hr_records.
workspace managers_ops "Managers Ops":
  purpose: "Reporting-line pressure — active manager links and team context without warehouse CRUD"
  access: persona(hr_admin, manager)

  link_pulse:
    source: ManagerLink
    display: metrics
    aggregate:
      links: count(ManagerLink where end_date = null)
      people: count(Person where ended_at = null)
      roles: count(Role)
    tones:
      links: accent
      people: positive
      roles: muted

  # WI D: queue family — active reporting lines first
  link_queue:
    source: ManagerLink
    filter: end_date = null
    sort: start_date desc
    limit: 25
    display: queue
    empty: "No active manager links"

  # WI D: grid family — people context
  people_grid:
    source: Person
    filter: ended_at = null
    display: grid
    limit: 20
    action: person_detail
    empty: "No active people on record"

  # WI D: context family — recent manager-link trail
  link_trail:
    source: ManagerLink
    sort: start_date desc
    limit: 15
    display: timeline
    empty: "No manager links yet"

  # WI D: chart family — role level mix (team shape)
  level_mix:
    source: Role
    display: bar_chart
    group_by: level
    aggregate:
      count: count(Role)
    empty: "No roles to chart"

# Fifteenth product desk (WI D): skip invoice_ops desk-cap; densify hr_records.
workspace active_staff "Active Staff":
  purpose: "Headcount pressure — currently employed people without warehouse CRUD"
  access: persona(hr_admin, manager, finance)

  headcount_pulse:
    source: Person
    display: metrics
    aggregate:
      active: count(Person where ended_at = null)
      leavers: count(Person where ended_at != null)
      employments: count(Employment where end_date = null)
    tones:
      active: positive
      leavers: warning
      employments: accent

  # WI D: queue family — active people first
  active_queue:
    source: Person
    filter: ended_at = null
    sort: started_at desc
    limit: 25
    display: queue
    action: person_detail
    empty: "No active people on record"

  # WI D: grid family — active people cards
  active_grid:
    source: Person
    filter: ended_at = null
    sort: legal_name asc
    limit: 20
    display: grid
    action: person_detail
    empty: "No active people on record"

  # WI D: context family — recent hire trail
  hire_trail:
    source: Person
    filter: ended_at = null
    sort: started_at desc
    limit: 15
    display: timeline
    action: person_detail
    empty: "No active hires yet"

  # WI D: chart family — role level mix for org shape
  level_mix:
    source: Role
    display: bar_chart
    group_by: level
    aggregate:
      count: count(Role)
    empty: "No roles to chart"
