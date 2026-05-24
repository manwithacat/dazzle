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
  intent: "Staff member, past or present. Identity only — temporal facts are in Employment/Salary/ManagerLink."

  id: uuid pk
  legal_name: str(200) required
  preferred_name: str(100)
  email: email required unique
  started_at: date required

  # TODO(#hr-temporal): no first-class concept of 'currently active employee'.
  # `ended_at IS NULL` is the convention; every query that wants 'active staff
  # only' has to add it manually to scope or where clauses.
  # ----- IF DAZZLE SUPPORTED IT, WE'D WRITE: -----
  # active_until: date soft_active   # framework treats null as 'currently active'
  # # ...so that `scope: list: active` resolves to `ended_at IS NULL OR ended_at > today`
  # ------------------------------------------------
  ended_at: date

  # TODO(#hr-temporal): no first-class 'current row' relationship.
  # We'd like `current_employment` and `current_salary` as typed traversals
  # that resolve to the row where end_date / effective_to IS NULL.
  # ----- IF DAZZLE SUPPORTED IT, WE'D WRITE: -----
  # current_employment: latest_one Employment of self where end_date = null
  # current_salary: latest_one Salary of self where effective_to = null
  # current_manager: latest_one Person via ManagerLink where end_date = null and report = self
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

# TODO(#hr-temporal): no `?as_of=YYYY-MM-DD` URL parameter for any workspace.
# The `time_machine` workspace below would need this as a first-class concept
# that re-projects every region's source query through a date filter.
# ----- IF DAZZLE SUPPORTED IT, WE'D WRITE: -----
# workspace time_machine "Time Machine":
#   as_of_param: as_of    # query string ?as_of=YYYY-MM-DD
#   # ...every region with a temporal entity source auto-filters by as_of
# ------------------------------------------------


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

  # TODO(#hr-temporal): aggregates over current-only rows.
  # cohort_strip lenses with primary_aggregate would benefit from
  # automatic "current only" filtering when the aggregated entity is
  # temporal. Today every lens needs `where effective_to = null` inside
  # the aggregate expression, repeated per lens.
  # ----- IF DAZZLE SUPPORTED IT, WE'D WRITE: -----
  # by_department:
  #   source: Department
  #   display: cohort_strip
  #   cohort_strip_config:
  #     member_via: id
  #     lenses:
  #       - id: avg_salary
  #         primary_aggregate:
  #           aggregate: avg(Salary.amount_minor where effective_to = null)
  #           via: Employment(department = id, end_date = null)
  #           share: Person
  #     # ...framework auto-applies "active only" since Salary + Employment
  #     # are both `temporal:` entities. Today each `where` must be hand-rolled.
  # ------------------------------------------------
  salary_list:
    source: Salary
    display: list


# TODO(#hr-temporal-time-machine): the time_machine workspace is the
# headline as-of demo and is the largest single Phase 3 ask. Currently
# unimplementable in DSL; would require:
#  - `as_of:` workspace-level query param declaration
#  - Every region with a temporal source re-projects via:
#      WHERE start_field <= as_of AND (end_field IS NULL OR end_field > as_of)
#  - The same predicate composes with scope: rules
#  - UI: date-picker chrome in the workspace shell, syncs ?as_of= URL param
# Until then, the workspace exists in spec only (see SPEC.md flow 7);
# implementing it would require a full route override + bespoke Jinja.
