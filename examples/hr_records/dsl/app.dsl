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

persona manager "Line Manager":
  description: "Read own direct reports (current and historical). No salary access."
  default_workspace: staff_directory

persona finance "Finance":
  description: "Read all salary data + employment history. No manager hierarchy."
  default_workspace: compensation_review

persona employee "Employee":
  description: "Read self only — own employment + salary history + current manager."
  default_workspace: person_detail


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
  legal_name: str(200) required
  preferred_name: str(100)
  email: email required unique
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
  amount_minor: int required
  currency: enum[gbp, eur, usd]=gbp
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

surface person_list "Staff Directory":
  uses entity Person
  mode: list
  section main:
    field legal_name "Legal name"
    field preferred_name "Preferred name"
    field email "Email"
    field started_at "Started"

surface person_detail "Person":
  uses entity Person
  mode: view
  section main:
    field legal_name "Legal name"
    field preferred_name "Preferred name"
    field email "Email"
    field started_at "Started"
    field ended_at "Ended (NULL = active)"

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
  section main:
    field name "Name"
    field parent_department "Parent"

surface department_create "Add Department":
  uses entity Department
  mode: create
  section main:
    field name "Name"
    field parent_department "Parent (optional)"

surface role_list "Roles":
  uses entity Role
  mode: list
  section main:
    field title "Title"
    field level "Level"
    field department "Department"

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
#     - Salary(person = above.Person.id, amount_minor, currency, effective_from = above.Person.started_at, reason = new_hire)
#     - ManagerLink(report = above.Person.id, manager, start_date = above.Person.started_at)
#   on_failure: rollback_all
# ------------------------------------------------
# Hand-roll workaround today: four separate create surfaces + project-side
# coordination. Loses transactional atomicity.
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

surface salary_create "New Salary":
  uses entity Salary
  mode: create
  section main:
    field person "Person"
    field amount_minor "Amount (pence)"
    field currency "Currency"
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


workspace staff_directory "Staff Directory":
  access: persona(hr_admin, manager, finance, employee)
  purpose: "Current employees, filterable by department + level"

  current_staff:
    source: Person
    display: list
    # TODO(#hr-temporal): `default_scope: where ended_at = null` on the
    # Person entity would obviate this region-level filter. Today we'd
    # need a `filter:` block here — but the example exists to demonstrate
    # the gap, so the region is unfiltered and the list shows everyone.

  recent_starters:
    source: Person
    display: list
    # TODO(#hr-temporal): "filter: started_at > today - 90d" — date
    # arithmetic in filters isn't first-class for list region filters
    # outside aggregate where clauses.


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
  employment_history:
    source: Employment
    display: list

  salary_history:
    source: Salary
    display: list


workspace org_chart "Org Chart":
  access: persona(hr_admin, manager)
  purpose: "Department tree + manager hierarchy"

  # TODO(#hr-hierarchy): no recursive tree display for self-referencing
  # entities. We have `display: tree` on group-keyed sources; we need a
  # variant that follows a self-reference (parent_department or
  # ManagerLink.manager) to N levels.
  # ----- IF DAZZLE SUPPORTED IT, WE'D WRITE: -----
  # department_tree:
  #   source: Department
  #   display: recursive_tree
  #   recursive_tree_config:
  #     parent_field: parent_department
  #     label: name
  #     expand_default: 2_levels
  # ------------------------------------------------
  departments:
    source: Department
    display: list

  # Job roles (title/level/department) are org reference data managed by
  # hr_admin — surfacing them here makes role_list/role_create reachable
  # from the workspace nav (was: defined but in no workspace → dead-construct
  # lint; #improve example-apps row 121).
  roles:
    source: Role
    display: list

  # TODO(#hr-hierarchy) + (#hr-temporal): manager chain visualisation.
  # The manager hierarchy is a temporal self-ref — drawing it requires
  # filtering ManagerLink to currently-active rows AND following the
  # `manager` FK recursively. Two pattern gaps compounded.
  reporting_lines:
    source: ManagerLink
    display: list


workspace compensation_review "Compensation Review":
  access: persona(hr_admin, finance)
  purpose: "Salary band analysis — by department, by role level"

  # #1223 Phase 3a.ii — Salary is a temporal entity (declared above) with
  # default_filter: active, so every list / aggregate / read path against
  # it automatically filters to currently-active rows. Authors no longer
  # need `where effective_to = null` per lens — the framework injects it
  # via Repository's tombstone filter. This list region renders only
  # active salary rows by default; appending `?effective_to__isnull=false`
  # to the URL opts out for history views (the future `?include_closed`
  # hook from #1218 will surface this as a friendlier param).
  salary_list:
    source: Salary
    display: list


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

  employment_snapshot:
    source: Employment
    display: list

  salary_snapshot:
    source: Salary
    display: list

  reporting_lines_snapshot:
    source: ManagerLink
    display: list
