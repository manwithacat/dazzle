# DAZZLE Contact Manager
# Demonstrates v0.7.1+ LLM Cognition Features:
# - Intent declarations for semantic clarity
# - Domain/pattern tags for classification
# - Invariants for data integrity
# - Workspace with dual_pane_flow stage

module contact_manager.core

app contact_manager "Contact Manager":
  security_profile: basic

# #1324 FR-4: per-tenant config flag gating a nav group at render time.
# `show_browse` toggles the "Browse" sidebar group per tenant via the
# `when: tenant_config.show_browse = true` clause on `nav contact_nav`.
tenancy:
  per_tenant_config:
    show_browse: bool

persona admin "Administrator":
  default_workspace: _platform_admin

# #1324: curated per-persona navigation. The `user` persona gets an
# explicit, hand-ordered sidebar via `uses nav contact_nav` (below);
# `admin` is left without a binding so it auto-discovers its sidebar
# from accessible workspaces — exercising both nav paths in one app.
persona user "User":
  default_workspace: contacts
  uses nav contact_nav

# Curated sidebar for the `user` persona (#1324). Each item is a bare
# entity or workspace name (no `item` keyword): an entity resolves to its
# list surface, a workspace to its page. Both targets here are real —
# Contact has a `mode: list` surface and `contacts` is a declared workspace.
nav contact_nav:
  group "Contacts":
    Contact
  # #1324 FR-4: the "Browse" group is hidden unless the tenant enables the
  # `show_browse` per-tenant config flag — render-time VISIBILITY only (the
  # `contacts` workspace stays reachable by direct URL / RBAC is unchanged).
  group "Browse" when: tenant_config.show_browse = true:
    contacts

# Entity for contact information with LLM cognition metadata.
#
# Tutorial-only: permit:/scope: blocks intentionally omitted to keep
# the minimal-demo entity focused on LLM cognition metadata. Production
# DSL would declare permit + scope rules per ADR-0010 — see
# `docs/reference/rbac-scope.md` (#1123) and `examples/simple_task/`
# for the canonical write-op scope pattern.
entity Contact "Contact":
  intent: "Store professional and personal contact information for relationship management"
  domain: crm
  patterns: profile, searchable

  display_field: email
  id: uuid pk
  first_name: str(100) required
  last_name: str(100) required
  email: email unique required
  phone: str(20)
  company: str(200)
  job_title: str(150)
  notes: text
  is_favorite: bool=false
  created_at: datetime auto_add
  updated_at: datetime auto_update

  # Invariant: contacts must have either email or phone
  invariant: email != null or phone != null

  index email
  index last_name,first_name

  fitness:
    repr_fields: [first_name, last_name, email, company, is_favorite]

# List view - browsable contact directory
surface contact_list "Contact List":
  uses entity Contact
  mode: list
  render: fragment

  section main "Contacts":
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email"
    field phone "Phone"
    field company "Company"
    field is_favorite "Favorite"

  ux:
    purpose: "Browse and search contacts"
    sort: last_name asc, first_name asc
    filter: is_favorite
    search: first_name, last_name, email, company
    empty: "No contacts yet. Add your first contact!"

# Detail view - full contact information
surface contact_detail "Contact Detail":
  uses entity Contact
  mode: view
  render: fragment

  section main "Contact Details":
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email"
    field phone "Phone"
    field company "Company"
    field job_title "Job Title"
    field notes "Notes"
    field is_favorite "Favorite"
    field created_at "Created"
    field updated_at "Updated"

  ux:
    purpose: "View complete contact information"

# Create form
surface contact_create "Create Contact":
  uses entity Contact
  mode: create
  render: fragment

  section identity "Identity":
    field first_name "First Name"
    field last_name "Last Name"

  section contact_details "Contact Details":
    field email "Email"
    field phone "Phone"

  section employment "Employment":
    field company "Company"
    field job_title "Job Title"

  section extras "Additional Info":
    field notes "Notes"

  ux:
    purpose: "Add a new contact"

# Edit form
surface contact_edit "Edit Contact":
  uses entity Contact
  mode: edit
  render: fragment

  section identity "Identity":
    field first_name "First Name"
    field last_name "Last Name"

  section contact_details "Contact Details":
    field email "Email"
    field phone "Phone"

  section employment "Employment":
    field company "Company"
    field job_title "Job Title"

  section extras "Additional Info":
    field notes "Notes"
    field is_favorite "Favorite"

  ux:
    purpose: "Update contact information"

# #954 — full-text search over Contact. Indexed via tsvector + GIN
# at startup; powers the search_box region below + the
# /api/fts/Contact endpoint.
search on Contact:
  fields: first_name, last_name, email, company
  ranking:
    last_name: 4
    first_name: 3
    company: 2
    email: 1
  highlight: true
  tokenizer: english

# Workspace with list + detail pattern
workspace contacts "Contacts":
  purpose: "Browse contacts and view details"
  stage: "dual_pane_flow"

  # Search signal — htmx-driven box that hits /api/fts/Contact.
  contact_search:
    source: Contact
    display: search_box
    title: "Find a contact"

  # List signal - browsable contact list
  contact_list:
    source: Contact
    sort: last_name asc, first_name asc
    limit: 20
    display: list
    action: contact_detail
    # Weight: 0.5 (base) + 0.1 (limit) = 0.6 (ITEM_LIST)

  # Detail signal - selected contact details
  contact_detail:
    source: Contact
    display: detail
    action: contact_edit
    # Weight: 0.5 (base) + 0.2 (detail) = 0.7 (DETAIL_VIEW)

# Stage Selection:
# - list_weight = 0.6 >= 0.3 ✓
# - detail_weight = 0.7 >= 0.3 ✓
# → DUAL_PANE_FLOW stage selected
#
# Layout:
# Desktop: Side-by-side list and detail panes
# Mobile: Stacked, detail slides over list on selection
