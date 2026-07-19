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

  section main "Users":
    field email "Email"
    field name "Name"
    field org "Organization"
    field created_at "Created"

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

  open_bills:
    source: Invoice
    display: queue
    sort: created_at desc
    limit: 20
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

  roster:
    source: Membership
    display: queue
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
