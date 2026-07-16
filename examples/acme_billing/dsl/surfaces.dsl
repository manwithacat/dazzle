module acme_billing.surfaces

use acme_billing.entities

# =============================================================================
# ORGANIZATION SURFACES
# =============================================================================

surface organization_list "Organizations":
  uses entity Organization
  mode: list
  render: fragment

  section main "Organizations":
    field name "Name"
    field created_at "Created"

surface organization_detail "Organization":
  uses entity Organization
  mode: view
  render: fragment

  section main "Organization Details":
    field name "Name"
    field created_at "Created"

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

  section main "Projects":
    field name "Name"
    field org "Organization"
    field created_at "Created"

surface project_detail "Project":
  uses entity Project
  mode: view
  render: fragment

  section main "Project Details":
    field name "Name"
    field org "Organization"
    field created_at "Created"

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
    sort: number asc
    bulk_actions:
      mark_sensitive: sensitive -> true
      mark_public: sensitive -> false

surface invoice_detail "Invoice":
  uses entity Invoice
  mode: view
  render: fragment

  section main "Invoice Details":
    field number "Number"
    field amount "Amount"
    field project "Project"
    field sensitive "Sensitive"
    field created_at "Created"

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

  section main "Memberships":
    field user "User"
    field project "Project"

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

  organizations:
    source: Organization
    display: list
    sort: name asc
    empty: "No organizations found"

  projects:
    source: Project
    display: list
    sort: name asc
    empty: "No projects found"

  memberships:
    source: Membership
    display: list
    empty: "No memberships found"
