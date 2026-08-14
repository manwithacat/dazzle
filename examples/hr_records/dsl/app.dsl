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
  # career_desk (not person_detail): workspace must not shadow surface person_detail
  # so Staff Directory row open lands the Person career hub (/app/person/{id}).
  default_workspace: career_desk
  uses nav employee_nav

# Curated sidebars: workspace destinations only (prefer desks over bare entity lists).
nav hr_admin_nav:
  group "People":
    staff_directory
    my_team
    starters_desk
    career_desk
    reporting_desk
    active_staff
  group "Org & pay":
    org_chart
    compensation_review
    time_machine

nav manager_nav:
  group "Team":
    my_team
    staff_directory
    career_desk
    org_chart
    reporting_desk
    active_staff

nav finance_nav:
  group "Compensation":
    compensation_review
    staff_directory
    career_desk
    active_staff

nav employee_nav:
  group "My record":
    career_desk
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
  # Goal B media (cycle 1879): peer HR tools (Workday / BambooHR / Personio)
  # put headshot thumbs on the staff home — not name-only directory theater.
  photo_url: url
  # Goal B org_structure peer upgrade (cycle 1914): work_location grain —
  # BambooHR / Workday people partners parse HQ vs remote vs hybrid, not only
  # level/dept boards. Recipe work_location_grain (not headshot_shelf).
  work_location: enum[london_hq,manchester,remote_uk,hybrid,client_site]=london_hq
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
    # Hand-rolled (returns ALL historical reports, not just current).
    # Cycle 1647 Goal B: Person rows for manager/employee/hr_admin/finance use
    # STABLE_PERSONA_USER_IDS so bare current_user == Person.id (no User entity).
    read: via ManagerLink(manager = current_user, report = id)
      as: manager
    list: via ManagerLink(manager = current_user, report = id)
      as: manager

    # Employee sees self only.
    read: id = current_user
      as: employee
    list: id = current_user
      as: employee

  fitness:
    # Location + name first so org boards and list rows read place grain.
    # Cycle 1935 agent_acceptance: staff media/people cards skip Email schema
    # dump (peer support_tickets User 1933, fieldtest Tester 1935). email stays
    # on list/detail; photo_url still media-injects.
    repr_fields: [legal_name, preferred_name, work_location, started_at]

  index work_location

  audit: all



# Goal B conversation: peer HR tools (Workday / BambooHR / Personio) show
# people notes on the staff desk — not only directory queues and metric tiles.
entity PersonNote "Person Note":
  intent: "HR discussion on a Person — the conversation that moves onboarding, leave, or promotion forward"
  domain: hr
  patterns: messaging, audit_trail
  display_field: body
  id: uuid pk
  person: ref Person required
  author: str(120) required
  body: text required
  created_at: datetime auto_add

  permit:
    list: role(hr_admin) or role(manager) or role(finance) or role(employee)
    read: role(hr_admin) or role(manager) or role(finance) or role(employee)
    create: role(hr_admin) or role(manager)
    update: role(hr_admin) or role(manager)
    delete: role(hr_admin)

  scope:
    list: all
      as: hr_admin, manager, finance, employee
    read: all
      as: hr_admin, manager, finance, employee
    create: all
      as: hr_admin, manager
    update: all
      as: hr_admin, manager
    delete: all
      as: hr_admin

  fitness:
    repr_fields: [person, author, body]


# =============================================================================
# HR DOCUMENT — document composition body on a Person (Goal B document)
# =============================================================================
#
# Peer HR dens (Workday / BambooHR / Lattice) put named offer / policy /
# promotion letters on staff homes — not only headcount queues and notes.
# display_field drives composition titles so hero stills read as documents.
# =============================================================================

entity HrDocument "HR Document":
  intent: "A named employment document on a Person — offer, policy ack, promotion letter, or contract buyers scan above the fold"
  domain: hr
  patterns: documentation, audit_trail
  display_field: headline
  id: uuid pk
  person: ref Person required
  headline: str(200) required
  doc_kind: enum[offer, policy, promo, contract, onboarding]=offer
  body: text
  status: enum[draft, issued, signed, archived]=draft
  author: str(120)
  created_at: datetime auto_add

  # Domain residual status∄transitions (cycle 1845): offers/policies issue → sign → archive.
  transitions:
    draft -> issued: role(hr_admin) or role(manager)
    issued -> signed: role(hr_admin) or role(manager)
    signed -> archived: role(hr_admin)
    draft -> archived: role(hr_admin)
    issued -> archived: role(hr_admin)

  permit:
    list: role(hr_admin) or role(manager) or role(finance) or role(employee)
    read: role(hr_admin) or role(manager) or role(finance) or role(employee)
    create: role(hr_admin) or role(manager)
    update: role(hr_admin) or role(manager)
    delete: role(hr_admin)

  scope:
    list: all
      as: hr_admin, manager, finance, employee
    read: all
      as: hr_admin, manager, finance, employee
    create: all
      as: hr_admin, manager
    update: all
      as: hr_admin, manager
    delete: all
      as: hr_admin

  fitness:
    repr_fields: [person, headline, doc_kind, status, author]


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
  # Assignment lifecycle phase (cycle 1476): complements temporal start/end —
  # status is the state machine; dates are the effective range.
  status: enum[active,on_leave,terminated]=active
  notes: text

  transitions:
    active -> on_leave: role(hr_admin)
    on_leave -> active: role(hr_admin)
    active -> terminated: role(hr_admin)
    on_leave -> terminated: role(hr_admin)
    terminated -> active: role(hr_admin)

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
    read: via ManagerLink(manager = current_user, report = person)
      as: manager
    list: via ManagerLink(manager = current_user, report = person)
      as: manager

    # Employee sees own employment history (all rows, including closed).
    read: person = current_user
      as: employee
    list: person = current_user
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
    read: person = current_user
      as: employee
    list: person = current_user
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
  display_field: report

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

    # Manager sees outbound reporting lines (people they manage).
    # Mixed-field OR (manager=… or report=…) fail-closes at runtime (#1630) —
    # so do not combine directions in one predicate. Inbound "my manager" is
    # visible on career_desk reporting_history for the manager's own row.
    read: manager = current_user
      as: manager
    list: manager = current_user
      as: manager

    # Employee sees rows where they are the report.
    read: report = current_user
      as: employee
    list: report = current_user
      as: employee

  audit: all

  fitness:
    repr_fields: [report, manager, start_date, end_date]


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
    field work_location "Work location"
    field email "Email"
    field photo_url "Photo"
    field started_at "Started"
  ux:
    purpose: "Staff directory — open a row for the person career hub (location grain)"

surface person_detail "Person":
  uses entity Person
  mode: view
  section identity "Identity":
    field legal_name "Legal name"
    field preferred_name "Preferred name"
    field email "Email"
    field photo_url "Photo"
    field work_location "Work location"
  section tenure "Tenure":
    layout: strip
    field started_at "Started"
    # Pilot-facing label (acceptance 1946): blank end date = still employed —
    # never surface SQL NULL jargon on the person hub.
    field ended_at "End date"
  # Person hub pull queues (RelatedDisplayMode.QUEUE) — role/amount-first
  # career roster, not warehouse tables (cycle 1506 story_walk / ST-002 path).
  related employment "Employment history":
    display: queue
    show: Employment
    columns: role, department, status, start_date, end_date
  related compensation "Salary history":
    display: queue
    show: Salary
    columns: amount, effective_from, effective_to, reason
  related reporting "Reporting lines":
    display: queue
    show: ManagerLink
    columns: report, manager, start_date, end_date
  # Goal B conversation (cycle 1899 hub wave): person hub Discussion uses
  # RelatedDisplayMode.conversation → Message/Bubble chrome (staff desk
  # live_conversation parity). Peer Lattice/Rippling people notes read as
  # content-first trails on the person — not queue meta rows.
  related discussion "Discussion":
    display: conversation
    show: PersonNote
    columns: body, author, created_at
  # Goal B document: named employment letters on the person hub.
  related documents "Documents":
    display: queue
    show: HrDocument
    columns: headline, doc_kind, status, created_at
  ux:
    purpose: "Person hub — identity photo, tenure, employment, salary, reporting, discussion, and HR documents"

surface person_create "Add Person":
  uses entity Person
  mode: create
  section main:
    field legal_name "Legal name"
    field preferred_name "Preferred name"
    field email "Email"
    field photo_url "Photo URL"
    field work_location "Work location"
    field started_at "Start date"

surface person_edit "Edit Person":
  uses entity Person
  mode: edit
  section main:
    field legal_name "Legal name"
    field preferred_name "Preferred name"
    field email "Email"
    field photo_url "Photo URL"
    field work_location "Work location"
    field ended_at "Ended"


surface person_note_list "Person Notes":
  uses entity PersonNote
  mode: list
  render: fragment
  open: PersonNote via id | Person via person

  section main "Notes":
    field body "Note"
    field author "Author"
    field person "Person"
    field created_at "When"

  ux:
    purpose: "HR discussion — open a note or its parent person"
    sort: created_at desc
    search: body, author
    empty: "No person notes yet"


# HrDocument surfaces (Goal B document composition)
surface hr_document_list "HR Documents":
  uses entity HrDocument
  mode: list
  render: fragment
  open: HrDocument via id | Person via person

  section main "Documents":
    field headline "Document"
    field doc_kind "Kind"
    field status "Status"
    field person "Person"
    field author "Author"
    field created_at "When"

  ux:
    purpose: "Document composition queue — named employment letters; open a letter hub or hop to the Person"
    filter: doc_kind, status
    sort: created_at desc
    search: headline, author
    empty: "No HR documents yet — open a person hub to attach an offer or policy letter"

surface hr_document_detail "HR Document":
  uses entity HrDocument
  mode: view
  render: fragment

  section summary "Document":
    layout: strip
    field headline "Headline"
    field doc_kind "Kind"
    field status "Status"
  section parties "Parties":
    field person "Person"
    field author "Author"
    field created_at "Created"
  section body "Body":
    field body "Body"

  ux:
    purpose: "HR document hub — named letter, lifecycle strip, parties, and body in one place"

surface hr_document_create "Add HR Document":
  uses entity HrDocument
  mode: create

  section main "New document":
    field person "Person"
    field headline "Headline"
    field doc_kind "Kind"
    field status "Status"
    field body "Body"
    field author "Author"

  ux:
    purpose: "Attach a named employment document to a person"

surface hr_document_edit "Edit HR Document":
  uses entity HrDocument
  mode: edit

  section main "Edit document":
    field headline "Headline"
    field doc_kind "Kind"
    field status "Status"
    field body "Body"
    field author "Author"

  ux:
    purpose: "Update employment document headline, kind, or status"

surface person_note_detail "Person Note":
  uses entity PersonNote
  mode: view
  render: fragment

  section summary "Note":
    field body "Note"
    field author "Author"
    field person "Person"
    field created_at "When"

  ux:
    purpose: "Read an HR note in context of its parent person"

surface person_note_create "Add Person Note":
  uses entity PersonNote
  mode: create
  render: fragment
  section main "New note":
    field person "Person"
    field author "Author"
    field body "Note"

# Edit surface so permit.update rows do not 404 on /app/personnote/{id}/edit
# (smoke dig 2026-08-06: auto_seed http_error on Edit for seeded PersonNotes).
surface person_note_edit "Edit Person Note":
  uses entity PersonNote
  mode: edit
  render: fragment
  section main "Edit note":
    field body "Note"
    field author "Author"
  ux:
    purpose: "Correct an HR discussion note without losing person context"

surface department_list "Departments":
  uses entity Department
  mode: list
  # Dual open: unit hub first, parent org unit second (tree context for ST-001 path).
  open: Department via id | Department via parent_department
  section main:
    field name "Name"
    field parent_department "Parent"
  ux:
    purpose: "Org units — open unit hub or hop to parent department"

surface department_detail "Department":
  uses entity Department
  mode: view
  section main "Unit":
    field name "Name"
    field parent_department "Parent"
  # Department hub role roster as pull queue (title-first), not warehouse table.
  related roles "Roles in unit":
    display: queue
    show: Role
  ux:
    purpose: "Department hub — unit identity and role pull queue"

surface department_create "Add Department":
  uses entity Department
  mode: create
  section main:
    field name "Name"
    field parent_department "Parent (optional)"

surface role_list "Roles":
  uses entity Role
  mode: list
  # Dual open: role hub first, owning department second (catalogue ST-003 path).
  open: Role via id | Department via department
  section main:
    field title "Title"
    field level "Level"
    field department "Department"
  ux:
    purpose: "Job roles — open role hub or hop to owning department"

surface role_detail "Role":
  uses entity Role
  mode: view
  section main "Role":
    field title "Title"
    field level "Level"
    field department "Department"
  # Role hub employment as pull queue (person/status-first), not warehouse table.
  related employment "Employment in role":
    display: queue
    show: Employment
  ux:
    purpose: "Role hub — title, level, and employment pull queue"

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
  # Triple open (acceptance dig cycle 1600): assignment hub, person career, role catalogue.
  open: Employment via id | Person via person | Role via role
  section main:
    field person "Person"
    field role "Role"
    field department "Department"
    field status "Status"
    field start_date "Start"
    field end_date "End"
  ux:
    purpose: "Employment history — open assignment hub, person career hub, or role catalogue"

# View surface so open Employment via id lands a readable assignment note.
surface employment_detail "Employment Detail":
  uses entity Employment
  mode: view
  section summary "Assignment":
    field person "Person"
    field role "Role"
    field department "Department"
  section tenure "Tenure":
    layout: strip
    field status "Status"
    field start_date "Start"
    field end_date "End"
  ux:
    purpose: "Read one employment assignment with person/role context"

surface employment_create "Start Employment":
  uses entity Employment
  mode: create
  section main:
    field person "Person"
    field role "Role"
    field department "Department"
    field start_date "Start date"
    field status "Status"

surface employment_edit "End / Update Employment":
  uses entity Employment
  mode: edit
  section main:
    field status "Status"
    field end_date "End date (set to close)"
    field notes "Notes"

surface salary_list "Salary history":
  uses entity Salary
  mode: list
  # Dual open: salary band hub first, person career hub second (ST-003 finance path).
  open: Salary via id | Person via person
  section main:
    field person "Person"
    field amount "Amount"
    field effective_from "From"
    field effective_to "To"
    field reason "Reason"
  ux:
    purpose: "Salary history — open a row for the band hub or person career hub"

# View surface so dual-open Salary via id lands a readable band note.
surface salary_detail "Salary Detail":
  uses entity Salary
  mode: view
  section summary "Band":
    field person "Person"
    field amount "Amount"
    field reason "Reason"
  section effective "Effective":
    layout: strip
    field effective_from "From"
    field effective_to "To"
  ux:
    purpose: "Read one salary band with person context"

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

surface managerlink_list "Reporting lines":
  uses entity ManagerLink
  mode: list
  # Triple open (story dig cycle 1609): link hub, report person, manager person.
  open: ManagerLink via id | Person via report | Person via manager
  section main:
    field report "Report"
    field manager "Manager"
    field start_date "From"
    field end_date "To"
  ux:
    purpose: "Reporting lines — open link hub, report career hub, or manager hub"

# View surface so open ManagerLink via id lands a readable edge note.
surface managerlink_detail "Reporting Line":
  uses entity ManagerLink
  mode: view
  section summary "Line":
    field report "Report"
    field manager "Manager"
  section effective "Effective":
    layout: strip
    field start_date "From"
    field end_date "To"
  ux:
    purpose: "Read one reporting line with report and manager person context"

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
  # Goal B media (cycle 1879) + command_density (1837) + document (1838):
  # headshot shelf first, then dual attention + employment documents before
  # notes — peer Workday / BambooHR put pixels + letters above discussion.
  purpose: "Multi-panel staff home — headshots, dual attention, document composition, then people notes"

  # Goal B media FIRST — staff home is a people shelf (photo_url thumbs).
  media_shelf:
    source: Person
    filter: ended_at = null
    display: grid
    sort: started_at desc
    # Cap 2 so dual attention + docs share the above-fold command dens.
    limit: 2
    action: person_detail
    empty: "No headshots yet — add photo URLs on people records"

  # Job strip — headcount + assignment status mix (acceptance criteria:
  # active / on leave / terminated visible without hunting employment rows).
  headcount:
    source: Person
    display: metrics
    aggregate:
      people: count(Person)
      departments: count(Department)
      roles: count(Role)
      active: count(Employment where status = active and end_date = null)
      on_leave: count(Employment where status = on_leave and end_date = null)
      terminated: count(Employment where status = terminated)
      documents: count(HrDocument)
      conversation: count(PersonNote)
    tones:
      people: accent
      active: accent
      on_leave: warning
      terminated: danger
      documents: accent
      conversation: accent

  # Dual attention — active roster + onboarding starters above fold (caps
  # for fold share with media + documents + notes trail).
  current_staff:
    source: Person
    filter: ended_at = null
    sort: started_at desc
    display: queue
    limit: 4
    action: person_detail
    empty: "No active people on record"
    # TODO(#hr-temporal): entity default_scope for ended_at = null would
    # make this region-level filter redundant; kept explicit for fold proof.

  # Work-surface utility: recent joiners are an onboarding pull queue, not inventory.
  recent_starters:
    source: Person
    sort: started_at desc
    display: queue
    limit: 4
    action: person_detail
    empty: "No recent joiners listed"
    # TODO(#hr-temporal): "filter: started_at > today - 90d" — date
    # arithmetic in filters isn't first-class for list region filters
    # outside aggregate where clauses.

  # Goal B document composition AFTER dual attention — named offer/policy
  # headlines (display_field: headline) before the notes trail.
  composition:
    source: HrDocument
    sort: created_at desc
    limit: 4
    display: queue
    action: hr_document_detail
    empty: "No documents yet — attach an offer or policy letter on a person"

  # Conversation trail after dual attention + documents — domain-true
  # people prose (display_field: body). Cap so pressure + docs keep fold share.
  live_conversation:
    source: PersonNote
    sort: created_at desc
    limit: 4
    display: queue
    action: person_note_detail
    empty: "No conversation yet — notes on people and onboarding appear here"

  ux:
    # Focus ≤4 (cycle 1950): full 6-name focus expanded fold to _MAX and
    # stormed nested Playwright (ERR_INSUFFICIENT_RESOURCES / htmx Failed
    # to fetch). Keep acceptance-critical shelf + status mix + dual
    # attention eager; composition + conversation remain on the desk but
    # intersect-once after scroll (still in region list above org queues).
    as hr_admin:
      purpose: "Multi-panel staff — headshots, dual attention, documents before notes"
      focus: media_shelf, headcount, current_staff, recent_starters
    as manager:
      purpose: "Multi-panel team view — headshots, roster, starters, documents before notes"
      focus: media_shelf, headcount, current_staff, recent_starters
    as finance:
      purpose: "Headshots + headcount dual attention + documents before compensation hop"
      focus: media_shelf, headcount, current_staff, recent_starters
    as employee:
      purpose: "Directory headshots, dual attention, and documents before notes"
      focus: media_shelf, headcount, current_staff, recent_starters

  # Org context as pull queues (agent_acceptance cycle 1522) — open hubs, not inventory lists.
  department_context:
    source: Department
    display: queue
    sort: name asc
    limit: 15
    action: department_detail
    empty: "No departments"

  role_context:
    source: Role
    display: queue
    sort: title asc
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
      - title: "Assignment status"
        caption: "Employment moves active → on leave → terminated under HR control"
        icon: "badge-check"
        state: positive

  # Cycle 1819 Goal B empty_region: drop twin people_cards + under-fold
  # dept/status bar-chart theater. Peer Workday/BambooHR homes lead with
  # dual attention + notes; lifecycle status lives on employment list/detail
  # (ST-001/ST-005). Secondary desks keep bar_chart for coverage.


# Named career_desk (not person_detail) so region action: person_detail resolves
# to surface person_detail — the Person entity hub — not a workspace that ignores
# context_id and shows company-wide timelines (agent_acceptance cycle 1918).
workspace career_desk "Career Desk":
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

  # Work-surface utility: employment rows are dated history — timeline not queue.
  employment_history:
    source: Employment
    display: timeline
    limit: 20
    empty: "No employment rows"

  # HMC-065 / work_surface_utility: salary + reporting rows are dated events
  # (effective_from / link dates) — timeline matches use_when time_order over list.
  salary_history:
    source: Salary
    display: timeline
    limit: 15
    empty: "No salary rows"

  reporting_history:
    source: ManagerLink
    display: timeline
    limit: 15
    empty: "No reporting lines on record"

  # Department roster as pull queue toward hubs (not bare inventory list).
  org_context:
    source: Department
    display: queue
    sort: name asc
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

  employment_trail:
    source: Employment
    display: timeline
    limit: 15
    empty: "No employment rows"

  salary_mix:
    source: Salary
    display: bar_chart
    group_by: reason
    aggregate:
      count: count(Salary)
    empty: "No salary rows"


# #1626 P0-7 / P1: department hierarchy via display:tree + parent_department.
# Post-5.8 Goal B org_structure: people reporting lines above the fold (queue
# of report→manager), not only dept units. Full recursive tree remains a
# pattern gap (TODO #hr-hierarchy); queue + person hubs is buyer-true.
workspace org_chart "Departments & Roles":
  access: persona(hr_admin, manager)
  purpose: "Who reports to whom, nested departments, and job roles — org hierarchy people can parse"

  org_pulse:
    source: Department
    display: metrics
    aggregate:
      departments: count(Department)
      roles: count(Role)
      reporting_lines: count(ManagerLink)
    tones:
      departments: accent
      reporting_lines: positive

  # People first (Goal B org_structure): report/manager names + avatars in a
  # pull-to-open queue, not an edge timeline buried below depts.
  reporting_lines:
    source: ManagerLink
    sort: start_date desc
    limit: 20
    display: queue
    action: managerlink_detail
    empty: "No reporting lines yet — assign a manager to a person"

  # Nested org units (Engineering → Frontend/Backend/Platform, etc.).
  # group_by parent_department matches fieldtest device_tree pattern.
  departments:
    source: Department
    display: tree
    group_by: parent_department
    sort: name asc
    limit: 40
    action: department_detail
    empty: "No departments yet — add one to start the org roster"

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

  role_level_mix:
    source: Role
    display: bar_chart
    group_by: level
    aggregate:
      count: count(Role)
    empty: "No roles"


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

  # Work-surface utility: salary bands read as dated events → timeline (queue is salary_queue).
  salary_list:
    source: Salary
    display: timeline
    limit: 20
    empty: "No active salaries"

  # Role catalogue + headcount as pull queues for compensation pilots (not inventory lists).
  role_catalogue:
    source: Role
    display: queue
    sort: title asc
    limit: 20
    action: role_detail
    empty: "No roles defined"

  headcount_context:
    source: Person
    display: queue
    sort: legal_name asc
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

  reason_mix:
    source: Salary
    display: bar_chart
    group_by: reason
    aggregate:
      count: count(Salary)
    empty: "No active salaries"

  # Work-surface utility (cycle 1482 acceptance): people are a pull-to-open
  # queue on the compensation desk, not a gallery grid.
  people_cards:
    source: Person
    display: queue
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

  # Work-surface utility (cycle 1482 acceptance): as-of salary rows are dated
  # band events → timeline (matches employment_snapshot queue + reporting timeline).
  salary_snapshot:
    source: Salary
    display: timeline
    limit: 20
    empty: "No salary rows for this as-of"

  reporting_lines_snapshot:
    source: ManagerLink
    display: timeline
    limit: 20
    empty: "No reporting lines for this as-of"

  employment_mix:
    source: Employment
    display: bar_chart
    group_by: department
    aggregate:
      count: count(Employment)
    empty: "No employment rows for this as-of"


# Sixth product workspace: manager team desk — reports first,
# not a bare Person warehouse list.
workspace my_team "My Team":
  # Goal B org_structure peer-pack (cycle 2065): recipe career_track_density —
  # BambooHR / Workday / Lattice put exclusive IC track vs people-manager track
  # role queues before a mixed by_level kanban (not office_remote-only or dept
  # metric tiles alone — people partners lean into career ladder shape).
  purpose: "Multi-panel manager desk — IC vs manager career-track density, then location/dept boards, documents, notes"
  access: persona(manager, hr_admin)

  team_pulse:
    source: Person
    display: metrics
    aggregate:
      people: count(Person)
      employment_rows: count(Employment)
      reporting_lines: count(ManagerLink)
      roles: count(Role)
      remote_uk: count(Person where work_location = remote_uk and ended_at = null)
      hybrid: count(Person where work_location = hybrid and ended_at = null)
      office_sites: count(Person where ended_at = null and (work_location = london_hq or work_location = manchester or work_location = client_site))
      remote_flex: count(Person where ended_at = null and (work_location = remote_uk or work_location = hybrid))
      documents: count(HrDocument)
      conversation: count(PersonNote)
    tones:
      people: accent
      reporting_lines: positive
      remote_uk: warning
      hybrid: accent
      office_sites: accent
      remote_flex: warning
      documents: accent
      conversation: accent

  # Career-track pulse — honest Role-source counts (IC vs people managers).
  career_pulse:
    source: Role
    display: metrics
    aggregate:
      ic_roles: count(Role where level = ic1 or level = ic2 or level = ic3 or level = ic4 or level = ic5 or level = ic6)
      manager_roles: count(Role where level = m1 or level = m2 or level = m3 or level = m4)
      roles: count(Role)
    tones:
      ic_roles: accent
      manager_roles: warning
      roles: positive

  # Dual exclusive career tracks (soft IC ladder vs hard people-manager track).
  ic_track:
    source: Role
    filter: level = ic1 or level = ic2 or level = ic3 or level = ic4 or level = ic5 or level = ic6
    sort: title asc
    limit: 8
    display: queue
    action: role_detail
    empty: "No IC-track roles — seed individual-contributor levels"

  manager_track:
    source: Role
    filter: level = m1 or level = m2 or level = m3 or level = m4
    sort: title asc
    limit: 8
    display: queue
    action: role_detail
    empty: "No people-manager roles — seed m1–m4 levels"

  # Office/remote density (cycle 2050) — secondary after career tracks.
  office_sites:
    source: Person
    filter: ended_at = null and (work_location = london_hq or work_location = manchester or work_location = client_site)
    sort: legal_name asc
    limit: 4
    display: queue
    action: person_detail
    empty: "No active people at office or client sites"

  remote_flex:
    source: Person
    filter: ended_at = null and (work_location = remote_uk or work_location = hybrid)
    sort: legal_name asc
    limit: 4
    display: queue
    action: person_detail
    empty: "No active remote or hybrid people"

  # Full level kanban under dual career tracks.
  by_level:
    source: Role
    display: kanban
    group_by: level
    sort: title asc
    limit: 40
    action: role_detail
    empty: "No roles defined yet"

  # Active assignments grouped by department — who sits where in the org.
  by_department:
    source: Employment
    filter: end_date = null
    display: kanban
    group_by: department
    sort: start_date desc
    limit: 40
    action: employment_detail
    empty: "No active employment rows"

  # Goal B org_structure peer upgrade (cycle 1914): work_location board.
  by_location:
    source: Person
    filter: ended_at = null
    display: kanban
    group_by: work_location
    sort: legal_name asc
    limit: 40
    action: person_detail
    empty: "No active people with work locations yet"

  # Who reports to whom — pull-to-open ManagerLink queue (capped for fold share).
  reporting_lines:
    source: ManagerLink
    sort: start_date desc
    limit: 4
    display: queue
    action: managerlink_detail
    empty: "No reporting lines yet — assign a manager to a person"

  # Goal B document composition AFTER dual attention / reporting.
  composition:
    source: HrDocument
    sort: created_at desc
    limit: 4
    display: queue
    action: hr_document_detail
    empty: "No team documents yet — attach an offer or promo letter on a report"

  ux:
    # Cycle 2065: career-track density eager (≤4); office/remote secondary.
    as manager:
      purpose: "IC vs people-manager career-track density before location and department boards"
      focus: career_pulse, ic_track, manager_track, by_department
    as hr_admin:
      purpose: "IC vs people-manager career-track density before placement boards"
      focus: career_pulse, ic_track, manager_track, by_department

  # Conversation trail after dual attention org boards + documents.
  live_conversation:
    source: PersonNote
    sort: created_at desc
    limit: 4
    display: queue
    action: person_note_detail
    empty: "No team conversation yet — notes on reports appear here"

  # Flat report roster after hierarchy (secondary, capped).
  reports:
    source: Person
    display: queue
    limit: 4
    action: person_detail
    empty: "No people in scope"

  team_readiness:
    display: status_list
    entries:
      - title: "Org structure"
        caption: "Level, department, and work-location boards before notes"
        icon: "network"
        state: accent
      - title: "Work location grain"
        caption: "HQ / Manchester / remote / hybrid columns a people partner uses"
        icon: "map-pin"
        state: accent
      - title: "Reporting lines"
        caption: "ManagerLink also lives on the Reporting desk"
        icon: "git-branch"
        state: positive

  # Cycle 1819 Goal B empty_region: drop dept_mix + role_mix_chart bar
  # theater — by_level / by_department kanbans already show org shape.
  # org_chart + compensation + active_staff retain bar_chart coverage.


# Seventh product workspace: HR starters / onboarding desk.
# Cycle 2057 empty_region (recipe hr_desk_twin_queue_prune): drop starter_cards
# twin of recent_people — peer BambooHR/Workday put one onboarding queue + hire
# trail, not two Person dumps with the same empty (support people_desk twin prune).
workspace starters_desk "New Starters":
  purpose: "HR desk for recent joiners — pulse, one onboarding queue, hire trail (no twin starter cards)"
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

  # Single onboarding pull queue (capped for fold share with hire trail).
  recent_people:
    source: Person
    sort: started_at desc
    display: queue
    limit: 8
    action: person_detail
    empty: "No people on record"

  employment_trail:
    source: Employment
    display: timeline
    limit: 12
    empty: "No employment rows yet"

  ux:
    as hr_admin:
      purpose: "Onboarding pulse + one starter queue + hire trail — no twin Person card dump"
      focus: starter_pulse, recent_people, employment_trail

  # Secondary mix under fold — bar_chart coverage for fleet display modes.
  salary_mix:
    source: Salary
    display: bar_chart
    group_by: reason
    aggregate:
      count: count(Salary)
    empty: "No salary rows yet"

# Eighth product workspace: reporting-line desk.
# Post-5.8 Goal B org_structure (cycle 1802) + empty_region_honesty (cycle 1946):
# peer Workday / Lattice / BambooHR put real report→manager lines above the fold.
# Cycle 1946: span_of_control was a group_by:manager kanban that rendered a
# giant empty void while Links metric counted 8 — honesty is a filled queue of
# active ManagerLink rows + department/location placement boards (not empty
# kanban theater). Full recursive tree remains TODO #hr-hierarchy.
workspace reporting_desk "Reporting":
  purpose: "People hierarchy — office/remote density, filled report→manager span, department + work-location placement (no empty span void)"
  access: persona(hr_admin, manager)

  reporting_pulse:
    source: ManagerLink
    display: metrics
    aggregate:
      links: count(ManagerLink)
      people: count(Person)
      departments: count(Department)
      roles: count(Role)
      remote_uk: count(Person where work_location = remote_uk and ended_at = null)
      hybrid: count(Person where work_location = hybrid and ended_at = null)
      office_sites: count(Person where ended_at = null and (work_location = london_hq or work_location = manchester or work_location = client_site))
      remote_flex: count(Person where ended_at = null and (work_location = remote_uk or work_location = hybrid))
    tones:
      links: accent
      people: positive
      remote_uk: warning
      hybrid: accent
      office_sites: accent
      remote_flex: warning

  # Goal B org_structure (cycle 2050): office↔remote dual presence before span
  # (recipe office_remote_density — peer BambooHR hybrid workforce view).
  office_sites:
    source: Person
    filter: ended_at = null and (work_location = london_hq or work_location = manchester or work_location = client_site)
    sort: legal_name asc
    limit: 4
    display: queue
    action: person_detail
    empty: "No active people at office or client sites"

  remote_flex:
    source: Person
    filter: ended_at = null and (work_location = remote_uk or work_location = hybrid)
    sort: legal_name asc
    limit: 4
    display: queue
    action: person_detail
    empty: "No active remote or hybrid people"

  # Span of control — active report→manager lines as a pull queue (fitness
  # shows report + manager names). Queue fills when Links>0; empty kanban
  # group_by:manager was a buyer-visible void (cycle 1946 still proof).
  span_of_control:
    source: ManagerLink
    filter: end_date = null
    sort: start_date desc
    limit: 12
    display: queue
    action: managerlink_detail
    empty: "No reporting lines yet — assign a manager to a person"

  # Active assignments by department — who sits where (people placement).
  by_department:
    source: Employment
    filter: end_date = null
    display: kanban
    group_by: department
    sort: start_date desc
    limit: 24
    action: employment_detail
    empty: "No active employment rows"

  # Cycle 1914: work_location board — place grain next to span-of-control.
  by_location:
    source: Person
    filter: ended_at = null
    display: kanban
    group_by: work_location
    sort: legal_name asc
    limit: 24
    action: person_detail
    empty: "No active people with work locations yet"

  ux:
    as hr_admin:
      purpose: "Office/remote density + filled reporting lines + department/location placement — no empty span theater"
      focus: reporting_pulse, office_sites, remote_flex, span_of_control, by_department, by_location
    as manager:
      purpose: "See office/remote density, report→manager lines, and open a reporting line or person hub"
      focus: reporting_pulse, office_sites, remote_flex, span_of_control, by_department, by_location

  # Dated link history under the fold (not a second empty primary region).
  link_trail:
    source: ManagerLink
    display: timeline
    limit: 8
    empty: "No reporting lines yet"

  org_readiness:
    display: status_list
    entries:
      - title: "Span of control"
        caption: "Active ManagerLink queue — open a row for report and manager hubs"
        icon: "network"
        state: accent
      - title: "Temporal links"
        caption: "ManagerLink rows are time-bounded — use Time Machine for as-of snapshots"
        icon: "clock"
        state: positive
      - title: "Team desk"
        caption: "Line managers start from My Team for level and department boards"
        icon: "users"
        state: positive

# Cycle 2057 empty_region (recipe hr_desk_twin_queue_prune): drop active_grid
# twin of active_queue — same Person source + same empty was scroll theater after
# headcount (peer BambooHR: one active roster + hire trail, not dual twin dumps).
workspace active_staff "Active Staff":
  purpose: "Headcount pressure — one active queue + hire trail (no twin grid dump)"
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

  # Single active headcount queue (capped; hire_trail timeline is distinct grain).
  active_queue:
    source: Person
    filter: ended_at = null
    sort: started_at desc
    limit: 8
    display: queue
    action: person_detail
    empty: "No active people on record"

  hire_trail:
    source: Person
    filter: ended_at = null
    sort: started_at desc
    limit: 12
    display: timeline
    action: person_detail
    empty: "No active hires yet"

  ux:
    as hr_admin:
      purpose: "Active headcount + hire trail — no twin Person grid dump"
      focus: headcount_pulse, active_queue, hire_trail
    as manager:
      purpose: "Active roster pressure without twin card theater"
      focus: headcount_pulse, active_queue, hire_trail
    as finance:
      purpose: "Active headcount before compensation hop — no twin dump"
      focus: headcount_pulse, active_queue, hire_trail

  # Secondary level mix under fold — bar_chart coverage retained.
  level_mix:
    source: Role
    display: bar_chart
    group_by: level
    aggregate:
      count: count(Role)
    empty: "No roles to chart"
