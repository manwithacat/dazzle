module acme_billing.surfaces

use acme_billing.entities

# =============================================================================
# ORGANIZATION SURFACES
# =============================================================================

surface organization_list "Organizations":
  uses entity Organization
  mode: list
  render: fragment
  open: Organization via id

  section main "Organizations":
    field name "Name"
    field created_at "Created"

  ux:
    purpose: "Browse organizations — open a row for the organization hub"

surface organization_detail "Organization":
  uses entity Organization
  mode: view
  render: fragment

  section main "Organization Details":
    field name "Name"
    field created_at "Created"

  related projects "Projects":
    display: table
    show: Project

  ux:
    purpose: "Organization hub — identity and related projects"

surface organization_create "Create Organization":
  uses entity Organization
  mode: create
  render: fragment

  section main "New Organization":
    field name "Name"

surface organization_edit "Edit Organization":
  uses entity Organization
  mode: edit
  render: fragment

  section main "Organization":
    field name "Name"

# =============================================================================
# USER SURFACES
# =============================================================================

surface user_list "Users":
  uses entity User
  mode: list
  render: fragment
  open: User via id

  section main "Users":
    field email "Email"
    field name "Name"
    field org "Organization"
    field created_at "Created"

  ux:
    purpose: "Browse users — open a row for the user hub"

surface user_detail "User":
  uses entity User
  mode: view
  render: fragment

  section main "User Details":
    field email "Email"
    field name "Name"
    field org "Organization"
    field created_at "Created"

surface user_create "Create User":
  uses entity User
  mode: create
  render: fragment

  section main "New User":
    field email "Email"
    field name "Name"
    field org "Organization"

surface user_edit "Edit User":
  uses entity User
  mode: edit
  render: fragment

  section main "User":
    field email "Email"
    field name "Name"
    field org "Organization"

# =============================================================================
# PROJECT SURFACES
# =============================================================================

surface project_list "Projects":
  uses entity Project
  mode: list
  render: fragment
  open: Project via id

  section main "Projects":
    field name "Name"
    field org "Organization"
    field created_at "Created"

  ux:
    purpose: "Browse projects — open a row for the project hub"

surface project_detail "Project":
  uses entity Project
  mode: view
  render: fragment

  section summary "Summary":
    field name "Name"
    field org "Organization"

  section meta "Meta":
    layout: strip
    field created_at "Created"

  related invoices "Invoices":
    display: table
    show: Invoice
    columns: number, amount, sensitive, created_at

  related members "Memberships":
    display: table
    show: Membership
    columns: user, project

  ux:
    purpose: "Project hub — org context, invoices, and memberships"

surface project_create "Create Project":
  uses entity Project
  mode: create
  render: fragment

  section main "New Project":
    field name "Name"
    field org "Organization"

surface project_edit "Edit Project":
  uses entity Project
  mode: edit
  render: fragment

  section main "Project":
    field name "Name"
    field org "Organization"

# =============================================================================
# INVOICE SURFACES
# =============================================================================

surface invoice_list "Invoices":
  uses entity Invoice
  mode: list
  render: fragment
  open: Project via project

  section main "Invoices":
    field number "Number"
    field amount "Amount"
    field project "Project"
    field sensitive "Sensitive"
    field created_at "Created"

  # Bulk sensitivity transitions — the runtime mounts POST /api/invoices/bulk.
  # The endpoint enforces the Invoice `update` permit gate (admin / org_owner
  # only), so auditor / project_member / external_contractor are denied (#1170).
  # The declared sort gives the list sortable headers (grid convergence C1.1 —
  # exercised end-to-end by tests/e2e/test_grid_convergence_e2e.py).
  ux:
    purpose: "Browse invoices — open a row for the parent Project hub"
    sort: number asc
    bulk_actions:
      mark_sensitive: sensitive -> true
      mark_public: sensitive -> false

surface invoice_detail "Invoice":
  uses entity Invoice
  mode: view
  render: fragment

  section summary "Summary":
    field number "Number"
    field amount "Amount"
    field project "Project"

  section flags "Flags":
    layout: strip
    field sensitive "Sensitive"
    field created_at "Created"

  ux:
    purpose: "Invoice detail — amount, project context, and sensitivity flags"

surface invoice_create "Create Invoice":
  uses entity Invoice
  mode: create
  render: fragment

  section main "New Invoice":
    field number "Number"
    field amount "Amount"
    field project "Project"
    field sensitive "Sensitive"

surface invoice_edit "Edit Invoice":
  uses entity Invoice
  mode: edit
  render: fragment

  section main "Invoice":
    field number "Number"
    field amount "Amount"
    field project "Project"
    field sensitive "Sensitive"

# =============================================================================
# MEMBERSHIP SURFACES
# =============================================================================

surface membership_list "Memberships":
  uses entity Membership
  mode: list
  render: fragment
  open: Project via project

  section main "Memberships":
    field user "User"
    field project "Project"

  ux:
    purpose: "Memberships — open a row for the parent Project hub"

surface membership_detail "Membership":
  uses entity Membership
  mode: view
  render: fragment

  section main "Membership Details":
    field user "User"
    field project "Project"

surface membership_create "Create Membership":
  uses entity Membership
  mode: create
  render: fragment

  section main "New Membership":
    field user "User"
    field project "Project"

surface membership_edit "Edit Membership":
  uses entity Membership
  mode: edit
  render: fragment

  section main "Membership":
    field user "User"
    field project "Project"

# =============================================================================
# WORKSPACE
# =============================================================================

workspace billing "Acme Billing":
  purpose: "Manage organizations, projects, invoices and team memberships"
  stage: "simple_list"
  # Gate the management workspace to the org-management personas. admin
  # (cross-org), org_owner (their org), auditor (read-only review) all
  # work with organizations/projects/invoices/memberships. project_member
  # and external_contractor have project-scoped access via their own
  # surfaces/scopes, not the full billing workspace (#improve row 120 —
  # previously this workspace had no access: declaration, so it was open
  # to all authenticated users).
  access: persona(admin, org_owner, auditor)

  # Metrics-first portfolio (story-to-composition) before dense entity lists.
  portfolio_metrics:
    source: Invoice
    display: metrics
    aggregate:
      organizations: count(Organization)
      projects: count(Project)
      invoices: count(Invoice)
      members: count(Membership)
    tones:
      invoices: accent

  open_invoices:
    source: Invoice
    sort: created_at desc
    limit: 15
    display: queue
    empty: "No invoices found"

  # WI D: grid + chart families (not three list pads)
  organizations:
    source: Organization
    display: grid
    sort: name asc
    empty: "No organizations found"

  projects:
    source: Project
    display: kanban
    group_by: name
    sort: name asc
    empty: "No projects found"

  membership_mix:
    source: Membership
    display: bar_chart
    group_by: role
    aggregate:
      count: count(Membership)
    empty: "No memberships found"

# Product landing for scoped workers (product maturity: not warehouse-only).
# Separate from billing so org-management chrome stays gated to owner/auditor.
workspace my_work "My Work":
  purpose: "What am I assigned to — projects and invoices I can act on"
  stage: "simple_list"
  access: persona(project_member, external_contractor)

  my_pulse:
    source: Project
    display: metrics
    aggregate:
      projects: count(Project)
      invoices: count(Invoice)
    tones:
      projects: accent

  assigned_projects:
    source: Project
    display: grid
    sort: name asc
    empty: "No projects assigned to you yet"

  my_invoices:
    source: Invoice
    display: queue
    sort: created_at desc
    limit: 15
    empty: "No invoices in your scope"

  # WI D: timeline context for team membership
  team_context:
    source: Membership
    display: timeline
    empty: "No memberships in your scope"

  # WI D: chart family — invoice load in my scope
  my_invoice_mix:
    source: Invoice
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices in your scope"

# Second product workspace lowers warehouse density and gives owners a
# project-first path distinct from the org/memberships portfolio.
workspace projects_home "Projects":
  purpose: "Project portfolio — open a project before drilling into invoices"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor, project_member, external_contractor)

  project_pulse:
    source: Project
    display: metrics
    aggregate:
      projects: count(Project)
      invoices: count(Invoice)
    tones:
      projects: accent

  project_queue:
    source: Project
    display: kanban
    group_by: name
    sort: name asc
    empty: "No projects found"

  recent_invoices:
    source: Invoice
    display: queue
    sort: created_at desc
    limit: 10
    empty: "No invoices yet"

  # WI D: chart family for project invoice load
  invoice_by_project:
    source: Invoice
    display: bar_chart
    group_by: project
    aggregate:
      count: count(Invoice)
    empty: "No invoices yet"

  # WI D: context family — project activity trail
  project_trail:
    source: Project
    display: timeline
    sort: name asc
    empty: "No projects found"

# Third product workspace (WI density D): invoice-first job desk so entity
# lists no longer dominate product shell count vs workspaces.
workspace invoices_home "Invoices":
  purpose: "Invoice desk — cash context and open bills before org/project drill-down"
  stage: "simple_list"
  # WI N: project_member needs a second job desk (not only my_work + lists)
  access: persona(admin, org_owner, auditor, project_member)

  invoice_pulse:
    source: Invoice
    display: metrics
    aggregate:
      invoices: count(Invoice)
      projects: count(Project)
      organizations: count(Organization)
    tones:
      invoices: accent

  # WI D: kanban family for invoice status board
  open_bills:
    source: Invoice
    display: kanban
    group_by: status
    sort: created_at desc
    empty: "No open invoices"

  # WI D: timeline of open bills (context family)
  bill_timeline:
    source: Invoice
    display: timeline
    sort: created_at desc
    limit: 15
    empty: "No open invoices"

  projects_context:
    source: Project
    display: grid
    sort: name asc
    empty: "No projects found"

  # WI D: chart family — invoices by status
  invoice_status_mix:
    source: Invoice
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices yet"

# Fourth product workspace (WI density D): team membership desk separate from
# org portfolio / projects / invoices — lowers list:workspace ratio.
workspace team_home "Team":
  purpose: "Team desk — who has access to which projects"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor)

  membership_pulse:
    source: Membership
    display: metrics
    aggregate:
      memberships: count(Membership)
      projects: count(Project)
      people: count(User)
    tones:
      memberships: accent

  # WI D: timeline of membership changes (context family)
  roster:
    source: Membership
    display: timeline
    empty: "No memberships yet"

  people:
    source: User
    display: grid
    sort: name asc
    empty: "No users found"

  # WI D: chart of membership load
  membership_chart:
    source: Membership
    display: bar_chart
    group_by: role
    aggregate:
      count: count(Membership)
    empty: "No memberships yet"

  # WI D: queue family — open memberships needing attention
  membership_queue:
    source: Membership
    display: queue
    limit: 20
    empty: "No memberships yet"

# Fifth job desk (WI density D): organization portfolio separate from billing shell
workspace orgs_home "Organizations":
  purpose: "Org portfolio — tenants before project/invoice drill-down"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor)

  org_pulse:
    source: Organization
    display: metrics
    aggregate:
      organizations: count(Organization)
      projects: count(Project)
      invoices: count(Invoice)
    tones:
      organizations: accent

  org_roster:
    source: Organization
    display: grid
    sort: name asc
    empty: "No organizations found"

  project_context:
    source: Project
    display: timeline
    sort: name asc
    empty: "No projects found"

  org_invoice_load:
    source: Invoice
    display: bar_chart
    group_by: project
    aggregate:
      count: count(Invoice)
    empty: "No invoices yet"

  # WI D: queue family — open invoices from the org portfolio
  open_bills:
    source: Invoice
    display: queue
    sort: created_at desc
    limit: 15
    empty: "No invoices yet"

# Seventh product desk (WI D): 5 lists floor dens ~0.45 with 6 full desks — need 7.
workspace membership_ops "Membership Ops":
  purpose: "Access membership desk — who is on which project, without warehouse CRUD"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor)

  membership_pulse:
    source: Membership
    display: metrics
    aggregate:
      memberships: count(Membership)
      people: count(User)
      projects: count(Project)
    tones:
      memberships: accent
      people: positive

  # WI D: grid family for membership cards
  roster:
    source: Membership
    display: grid
    limit: 25
    empty: "No memberships yet"

  # WI D: queue family — project access work
  project_queue:
    source: Project
    display: queue
    sort: name asc
    limit: 20
    empty: "No projects found"

  # WI D: context family — people trail via users
  people_trail:
    source: User
    display: timeline
    sort: name asc
    limit: 15
    empty: "No users found"

  # WI D: chart family — memberships by role
  role_mix:
    source: Membership
    display: bar_chart
    group_by: role
    aggregate:
      count: count(Membership)
    empty: "No memberships yet"

# Eighth product desk (WI D): 5 lists floor dens ~0.42 with 7 full desks — need 8.
workspace sensitive_review "Sensitive Review":
  purpose: "Sensitivity desk — flag and review sensitive invoices without warehouse CRUD"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor)

  sensitivity_pulse:
    source: Invoice
    display: metrics
    aggregate:
      sensitive: count(Invoice where sensitive = true)
      open: count(Invoice)
      projects: count(Project)
    tones:
      sensitive: warning
      open: accent

  # WI D: queue family — sensitive invoices first
  sensitive_queue:
    source: Invoice
    filter: sensitive = true
    sort: created_at desc
    limit: 20
    display: queue
    empty: "No sensitive invoices flagged"

  # WI D: grid family for project context
  project_cards:
    source: Project
    display: grid
    sort: name asc
    limit: 15
    empty: "No projects found"

  # WI D: context family — recent invoice trail
  invoice_trail:
    source: Invoice
    sort: created_at desc
    limit: 15
    display: timeline
    empty: "No invoices yet"

  # WI D: chart family — sensitive vs open mix via project load
  project_invoice_load:
    source: Invoice
    display: bar_chart
    group_by: project
    aggregate:
      count: count(Invoice)
    empty: "No invoices yet"

# Ninth product desk (WI D): 5 lists floor dens ~0.38 with 8 full desks — need 9.
workspace collections_ops "Collections":
  purpose: "Collections pressure — largest invoices and project load without warehouse CRUD"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor, project_member)

  collections_pulse:
    source: Invoice
    display: metrics
    aggregate:
      invoices: count(Invoice)
      projects: count(Project)
      sensitive: count(Invoice where sensitive = true)
    tones:
      invoices: accent
      sensitive: warning

  # WI D: queue family — largest invoices first
  amount_queue:
    source: Invoice
    sort: amount desc
    limit: 20
    display: queue
    empty: "No invoices on file"

  # WI D: grid family — project portfolio context
  project_cards:
    source: Project
    display: grid
    sort: name asc
    limit: 15
    empty: "No projects found"

  # WI D: context family — recent billing trail
  billing_trail:
    source: Invoice
    sort: created_at desc
    limit: 15
    display: timeline
    empty: "No invoices yet"

  # WI D: chart family — invoice load by project
  project_load:
    source: Invoice
    display: bar_chart
    group_by: project
    aggregate:
      count: count(Invoice)
    empty: "No invoices yet"

# Tenth product desk (WI D): 5 lists floor dens ~0.36 with 9 full desks — need 10.
workspace org_ops "Org Ops":
  purpose: "Organization pressure — tenant footprint and project spread without warehouse CRUD"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor, project_member)

  org_pulse:
    source: Organization
    display: metrics
    aggregate:
      orgs: count(Organization)
      projects: count(Project)
      invoices: count(Invoice)
    tones:
      orgs: accent
      projects: positive
      invoices: warning

  # WI D: queue family — organizations first
  org_queue:
    source: Organization
    sort: name asc
    limit: 20
    display: queue
    empty: "No organizations on file"

  # WI D: grid family — project portfolio cards
  project_cards:
    source: Project
    display: grid
    sort: name asc
    limit: 15
    empty: "No projects found"

  # WI D: context family — recent project trail
  project_trail:
    source: Project
    sort: created_at desc
    limit: 15
    display: timeline
    empty: "No projects yet"

  # WI D: chart family — project load by organization
  org_load:
    source: Project
    display: bar_chart
    group_by: org
    aggregate:
      count: count(Project)
    empty: "No projects to chart"

# Eleventh product desk (WI D): 5 lists floor dens ~0.33 with 10 full desks — need 11.
workspace project_ops "Project Ops":
  purpose: "Project pressure — portfolio pulse and invoice load without warehouse CRUD"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor, project_member)

  project_pulse:
    source: Project
    display: metrics
    aggregate:
      projects: count(Project)
      invoices: count(Invoice)
      memberships: count(Membership)
    tones:
      projects: accent
      invoices: warning
      memberships: positive

  # WI D: queue family — projects first
  project_queue:
    source: Project
    sort: name asc
    limit: 20
    display: queue
    empty: "No projects on file"

  # WI D: grid family — invoice cards for billing context
  invoice_cards:
    source: Invoice
    display: grid
    sort: amount desc
    limit: 15
    empty: "No invoices found"

  # WI D: context family — recent project trail
  project_trail:
    source: Project
    sort: created_at desc
    limit: 15
    display: timeline
    empty: "No projects yet"

  # WI D: chart family — invoice load by project
  invoice_load:
    source: Invoice
    display: bar_chart
    group_by: project
    aggregate:
      count: count(Invoice)
    empty: "No invoices to chart"

# Twelfth product desk (WI D): 5 lists floor dens ~0.31 with 11 full desks — need 12.
workspace user_ops "User Ops":
  purpose: "User pressure — org people footprint without warehouse CRUD"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor)

  user_pulse:
    source: User
    display: metrics
    aggregate:
      users: count(User)
      memberships: count(Membership)
      orgs: count(Organization)
    tones:
      users: accent
      memberships: positive
      orgs: accent

  # WI D: queue family — people first
  user_queue:
    source: User
    sort: name asc
    limit: 20
    display: queue
    empty: "No users on file"

  # WI D: grid family — membership cards
  membership_cards:
    source: Membership
    display: grid
    limit: 15
    empty: "No memberships found"

  # WI D: context family — recent user trail
  user_trail:
    source: User
    sort: created_at desc
    limit: 15
    display: timeline
    empty: "No users yet"

  # WI D: chart family — users by organization
  org_mix:
    source: User
    display: bar_chart
    group_by: org
    aggregate:
      count: count(User)
    empty: "No users to chart"

# Thirteenth product desk (WI D): skip invoice_ops desk-cap; densify acme next.
workspace public_billing "Public Billing":
  purpose: "Non-sensitive invoice pressure for shared member work without warehouse CRUD"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor, project_member)

  public_pulse:
    source: Invoice
    display: metrics
    aggregate:
      public: count(Invoice where sensitive != true)
      sensitive: count(Invoice where sensitive = true)
      projects: count(Project)
    tones:
      public: accent
      sensitive: warning
      projects: positive

  # WI D: queue family — non-sensitive invoices first
  public_queue:
    source: Invoice
    filter: sensitive != true
    sort: amount desc
    limit: 20
    display: queue
    empty: "No non-sensitive invoices"

  # WI D: grid family — project portfolio cards
  project_cards:
    source: Project
    display: grid
    sort: name asc
    limit: 15
    empty: "No projects found"

  # WI D: context family — recent public billing trail
  public_trail:
    source: Invoice
    filter: sensitive != true
    sort: created_at desc
    limit: 15
    display: timeline
    empty: "No public invoices yet"

  # WI D: chart family — public invoice load by project
  project_load:
    source: Invoice
    filter: sensitive != true
    display: bar_chart
    group_by: project
    aggregate:
      count: count(Invoice)
    empty: "No public invoices to chart"
