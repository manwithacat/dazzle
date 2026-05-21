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

# =============================================================================
# WORKSPACE
# =============================================================================

workspace billing "Acme Billing":
  purpose: "Manage organizations, projects, invoices and team memberships"
  stage: "simple_list"

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

  invoices:
    source: Invoice
    display: list
    sort: created_at desc
    empty: "No invoices found"

  memberships:
    source: Membership
    display: list
    empty: "No memberships found"
