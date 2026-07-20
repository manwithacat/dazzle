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
  # Product home — not framework platform chrome (#1626 P0-3/4).
  default_workspace: home

# #1324: curated per-persona navigation. The `user` persona gets an
# explicit, hand-ordered sidebar via `uses nav contact_nav` (below);
# `admin` is left without a binding so it auto-discovers its sidebar
# from accessible workspaces — exercising both nav paths in one app.
persona user "User":
  # TR-2: land on a welcome/overview workspace, not a bare contact list.
  default_workspace: home
  uses nav contact_nav

# Curated sidebar for the `user` persona (#1324). Each item is a bare
# entity or workspace name (no `item` keyword): an entity resolves to its
# list surface, a workspace to its page. Both targets here are real —
# Contact has a `mode: list` surface and `contacts` is a declared workspace.
nav contact_nav:
  # TR-2 / WI N: job desks first — workspaces only (not auto entity-list soup).
  group "Home":
    home
    favorites_ops
    company_ops
    independent_ops
  group "Directory":
    contacts
    companies
  # #1324 FR-4: optional Browse group still exposes the contacts desk when
  # the tenant enables `show_browse` (workspace target, not bare Contact list).
  group "Browse" when: tenant_config.show_browse = true:
    contacts
    favorites_ops
    company_ops
    independent_ops

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
  first_name: str(100) required pii(category=identity)
  last_name: str(100) required pii(category=identity)
  email: email unique required pii(category=contact)
  phone: str(20) pii(category=contact)
  company: str(200)
  job_title: str(150)
  notes: text pii(category=freeform)
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
surface contact_list "Contacts":
  uses entity Contact
  mode: list
  render: fragment
  open: Contact via id

  section main "Contacts":
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email"
    field phone "Phone"
    field company "Company"
    field is_favorite "Favorite"

  ux:
    purpose: "Browse and search contacts — open a row for the contact hub"
    sort: last_name asc, first_name asc
    filter: is_favorite
    search: first_name, last_name, email, company
    empty: "No contacts yet. Add your first contact!"

# Detail view — contact hub (identity / employment / notes)
surface contact_detail "Contact Detail":
  uses entity Contact
  mode: view
  render: fragment

  section identity "Identity":
    field first_name "First Name"
    field last_name "Last Name"
    field email "Email"
    field phone "Phone"

  section employment "Employment":
    layout: strip
    field company "Company"
    field job_title "Job Title"
    field is_favorite "Favorite"

  section notes "Notes & timeline":
    field notes "Notes"
    field created_at "Created"
    field updated_at "Updated"

  ux:
    purpose: "Contact hub — identity, employment, and notes in one place"

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

# TR-2: first-run / post-login welcome — overview before the dense list.
# Story-driven (docs/guides/story-to-composition.md): metrics + favourites
# queue first (ST-007), then a short directory sample (ST-004).
workspace home "Home":
  purpose: "Welcome overview for your contact directory"
  access: persona(user, admin)

  directory_stats:
    source: Contact
    display: metrics
    aggregate:
      total_contacts: count(Contact)
      favourites: count(Contact where is_favorite = true)
      companies: count(Contact where company != null)
    tones:
      favourites: accent
      total_contacts: positive

  # ST-007 — favourites as a work queue, not buried in the full list sort.
  favourite_contacts:
    source: Contact
    filter: is_favorite = true
    sort: last_name asc, first_name asc
    limit: 10
    display: queue
    action: contact_detail
    empty: "No favourites yet — star a contact from the directory."

  # WI D/L: grid + timeline families (not dual list pads)
  recent_contacts:
    source: Contact
    sort: last_name asc, first_name asc
    limit: 8
    display: grid
    action: contact_detail
    empty: "No contacts yet. Open Contacts or use New Contact to add your first person or company."

  company_contacts:
    source: Contact
    filter: company != null
    sort: company asc, last_name asc
    limit: 8
    display: timeline
    action: contact_detail
    empty: "No company contacts yet"

  # WI D: chart of company mix on the home landing
  company_mix:
    source: Contact
    filter: company != null
    display: bar_chart
    group_by: company
    aggregate:
      count: count(Contact)
    empty: "No company contacts yet"

  find_contact:
    source: Contact
    display: search_box
    title: "Find a contact"

  ux:
    as user:
      purpose: "See a friendly overview before diving into the full list"
      focus: directory_stats, favourite_contacts, recent_contacts
    as admin:
      purpose: "Directory overview"
      focus: directory_stats, favourite_contacts, recent_contacts

# Workspace with list + detail pattern
workspace contacts "Contacts":
  # #1626 P0-7: dual_pane_flow stage selects list+detail layout when the shell
  # supports it; captures may still show list-primary if selection is empty.
  purpose: "Browse contacts (list + detail hub) — favourites strip and A–Z directory"
  access: persona(user, admin)
  stage: "dual_pane_flow"

  # Search signal — htmx-driven box that hits /api/fts/Contact.
  contact_search:
    source: Contact
    display: search_box
    title: "Find a contact"

  # Favourites strip above the A–Z list (ST-007).
  favourites_queue:
    source: Contact
    filter: is_favorite = true
    sort: last_name asc, first_name asc
    limit: 8
    display: queue
    action: contact_detail
    empty: "No favourites pinned"

  # List signal - browsable contact list (dual_pane needs listish)
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

  # WI D: kanban of favourites vs rest for directory triage
  favorite_board:
    source: Contact
    display: kanban
    group_by: is_favorite
    sort: last_name asc
    action: contact_detail
    empty: "No contacts yet"

# Third product workspace (WI density D): company-first job desk.
workspace companies "Companies":
  purpose: "Company roll-up — who works where before opening a person"
  access: persona(user, admin)

  company_pulse:
    source: Contact
    display: metrics
    aggregate:
      companies: count(Contact where company != null)
      people: count(Contact)
      favourites: count(Contact where is_favorite = true)
    tones:
      companies: accent
      favourites: positive

  by_company:
    source: Contact
    filter: company != null
    sort: company asc, last_name asc
    limit: 30
    display: grid
    action: contact_detail
    empty: "No company contacts yet"

  company_chart:
    source: Contact
    filter: company != null
    display: bar_chart
    group_by: company
    aggregate:
      count: count(Contact)
    empty: "No company contacts yet"

  recent_people:
    source: Contact
    sort: updated_at desc
    limit: 12
    display: timeline
    action: contact_detail
    empty: "No contacts yet"

# Fourth product desk (WI D): skip invoice_ops desk-cap; densify contact_manager.
workspace favorites_ops "Favorites Ops":
  purpose: "Starred-contact pressure — keep VIP people close without warehouse CRUD"
  access: persona(user, admin)

  fav_pulse:
    source: Contact
    display: metrics
    aggregate:
      favourites: count(Contact where is_favorite = true)
      people: count(Contact)
      companies: count(Contact where company != null)
    tones:
      favourites: accent
      people: positive
      companies: muted

  # WI D: queue family — favourites first
  fav_queue:
    source: Contact
    filter: is_favorite = true
    sort: last_name asc, first_name asc
    limit: 20
    display: queue
    action: contact_detail
    empty: "No favourites yet — star a contact from the directory."

  # WI D: grid family — favourite cards
  fav_grid:
    source: Contact
    filter: is_favorite = true
    sort: last_name asc
    limit: 15
    display: grid
    action: contact_detail
    empty: "No favourites yet"

  # WI D: context family — recent favourite trail
  fav_trail:
    source: Contact
    filter: is_favorite = true
    sort: updated_at desc
    limit: 15
    display: timeline
    action: contact_detail
    empty: "No favourite activity yet"

  # WI D: chart family — company mix among favourites
  company_mix:
    source: Contact
    filter: is_favorite = true and company != null
    display: bar_chart
    group_by: company
    aggregate:
      count: count(Contact)
    empty: "No favourite company contacts to chart"


# Fifth product desk (WI D): skip invoice/fieldtest/acme soft-cap; densify contact_manager.
workspace company_ops "Company Ops":
  purpose: "Employed-contact pressure — people with company affiliation without warehouse CRUD"
  access: persona(user, admin)

  company_pulse:
    source: Contact
    display: metrics
    aggregate:
      with_company: count(Contact where company != null)
      favourites: count(Contact where is_favorite = true)
      people: count(Contact)
    tones:
      with_company: accent
      favourites: positive
      people: muted

  # WI D: queue family — company contacts first
  company_queue:
    source: Contact
    filter: company != null
    sort: company asc, last_name asc
    limit: 20
    display: queue
    action: contact_detail
    empty: "No company contacts yet"

  # WI D: grid family — company cards
  company_grid:
    source: Contact
    filter: company != null
    sort: company asc
    limit: 15
    display: grid
    action: contact_detail
    empty: "No company contacts yet"

  # WI D: context family — recent company-contact trail
  company_trail:
    source: Contact
    filter: company != null
    sort: updated_at desc
    limit: 15
    display: timeline
    action: contact_detail
    empty: "No company-contact activity yet"

  # WI D: chart family — contacts by company
  company_mix:
    source: Contact
    filter: company != null
    display: bar_chart
    group_by: company
    aggregate:
      count: count(Contact)
    empty: "No company contacts to chart"


# Sixth product desk (WI D): skip invoice/fieldtest/acme/hr soft-cap; densify contact_manager.
workspace independent_ops "Independent Ops":
  purpose: "Independent-contact pressure — people without company affiliation without warehouse CRUD"
  access: persona(user, admin)

  independent_pulse:
    source: Contact
    display: metrics
    aggregate:
      independent: count(Contact where company = null)
      favourites: count(Contact where is_favorite = true)
      people: count(Contact)
    tones:
      independent: accent
      favourites: positive
      people: muted

  # WI D: queue family — independents first
  independent_queue:
    source: Contact
    filter: company = null
    sort: last_name asc, first_name asc
    limit: 20
    display: queue
    action: contact_detail
    empty: "No independent contacts yet"

  # WI D: grid family — independent cards
  independent_grid:
    source: Contact
    filter: company = null
    sort: last_name asc
    limit: 15
    display: grid
    action: contact_detail
    empty: "No independent contacts yet"

  # WI D: context family — recent independent trail
  independent_trail:
    source: Contact
    filter: company = null
    sort: updated_at desc
    limit: 15
    display: timeline
    action: contact_detail
    empty: "No independent-contact activity yet"

  # WI D: chart family — favourite mix among independents
  favorite_mix:
    source: Contact
    filter: company = null
    display: bar_chart
    group_by: is_favorite
    aggregate:
      count: count(Contact)
    empty: "No independent contacts to chart"

# Stage Selection:
# - list_weight = 0.6 >= 0.3 ✓
# - detail_weight = 0.7 >= 0.3 ✓
# → DUAL_PANE_FLOW stage selected
#
# Layout:
# Desktop: Side-by-side list and detail panes
# Mobile: Stacked, detail slides over list on selection
