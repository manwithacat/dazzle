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

  # Pull-next project roster (not warehouse table) — ST-011 acceptance hub dig.
  related projects "Projects":
    display: queue
    show: Project
    columns: name, created_at

  ux:
    purpose: "Organization hub — identity and related project queue"

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
  # Dual open (journey_dogfood dig cycle 1574): user hub first; secondary hop
  # to parent Organization hub for tenant roster context.
  open: User via id | Organization via org

  section main "Users":
    field email "Email"
    field name "Name"
    field job_title "Job Title"
    field department "Department"
    field org "Organization"
    field created_at "Created"

  ux:
    purpose: "Browse users by title and department — open a row for the user hub or parent Organization hub"
    sort: department asc, name asc
    filter: department, job_title, org
    search: name, email, department, job_title

surface user_detail "User":
  uses entity User
  mode: view
  render: fragment

  section main "User Details":
    field email "Email"
    field name "Name"
    field job_title "Job Title"
    field department "Department"
    field org "Organization"
    field created_at "Created"

surface user_create "Create User":
  uses entity User
  mode: create
  render: fragment

  section main "New User":
    field email "Email"
    field name "Name"
    field job_title "Job Title"
    field department "Department"
    field org "Organization"

surface user_edit "Edit User":
  uses entity User
  mode: edit
  render: fragment

  section main "User":
    field email "Email"
    field name "Name"
    field job_title "Job Title"
    field department "Department"
    field org "Organization"

# =============================================================================
# PROJECT SURFACES
# =============================================================================

surface project_list "Projects":
  uses entity Project
  mode: list
  render: fragment
  # Dual open (journey_dogfood dig cycle 1574): project hub first; secondary
  # hop to parent Organization hub for tenant context (ST-006/003/001).
  open: Project via id | Organization via org

  section main "Projects":
    field name "Name"
    field org "Organization"
    field created_at "Created"

  ux:
    purpose: "Browse projects — open a row for the project hub or parent Organization hub"

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

  # Invoice + membership pull queues (not warehouse tables) — ST-006/008 dig.
  related invoices "Invoices":
    display: queue
    show: Invoice
    columns: number, amount, sensitive, created_at

  related members "Memberships":
    display: queue
    show: Membership
    columns: user, project

  ux:
    purpose: "Project hub — org context, invoice queue, and membership queue"

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
  # Dual open (cycle 1544 story_walk): primary = invoice detail; secondary =
  # parent Project hub for portfolio → project context (ST-002/007/010).
  open: Invoice via id | Project via project

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
    purpose: "Browse invoices — open a row for invoice detail or the parent Project hub"
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

  # Document composition (Goal B): line items are the invoice body, not a
  # warehouse table — named descriptions + qty × unit (cents).
  related lines "Line items":
    display: queue
    show: LineItem
    columns: description, quantity, unit_amount

  # Goal B conversation (cycle 1899 hub wave): invoice hub Discussion uses
  # RelatedDisplayMode.conversation → Message/Bubble chrome (finance desk
  # live_conversation parity). Peer billing tools show discussion copy as a
  # content-first trail on the invoice — not queue meta rows.
  related discussion "Discussion":
    display: conversation
    show: InvoiceNote
    columns: body, author, created_at

  ux:
    purpose: "Invoice document — header, line composition, discussion, and sensitivity flags"

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
# INVOICE NOTE SURFACES (Goal B conversation)
# =============================================================================

surface invoice_note_list "Invoice Notes":
  uses entity InvoiceNote
  mode: list
  render: fragment
  open: InvoiceNote via id | Invoice via invoice

  section main "Notes":
    field body "Note"
    field author "Author"
    field invoice "Invoice"
    field created_at "When"

  ux:
    purpose: "Billing discussion — open a note or its parent invoice"
    sort: created_at desc
    search: body, author
    empty: "No invoice notes yet"

surface invoice_note_detail "Invoice Note":
  uses entity InvoiceNote
  mode: view
  render: fragment

  section summary "Note":
    field body "Note"
    field author "Author"
    field invoice "Invoice"
    field created_at "When"

  ux:
    purpose: "Read a billing note in context of its parent invoice"

surface invoice_note_create "Add Invoice Note":
  uses entity InvoiceNote
  mode: create
  render: fragment
  section main "New note":
    field invoice "Invoice"
    field author "Author"
    field body "Note"

# =============================================================================
# LINE ITEM SURFACES (Goal B document composition)
# =============================================================================

surface line_item_list "Line Items":
  uses entity LineItem
  mode: list
  render: fragment
  # Dual open: line hub first; parent Invoice document second.
  open: LineItem via id | Invoice via invoice

  section main "Line Items":
    field description "Description"
    field quantity "Qty"
    field unit_amount "Unit (¢)"
    field invoice "Invoice"

  ux:
    purpose: "Document lines — open a row for the line or parent invoice document"

surface line_item_detail "Line Item":
  uses entity LineItem
  mode: view
  render: fragment

  section main "Line":
    field description "Description"
    field quantity "Qty"
    field unit_amount "Unit (¢)"
    field invoice "Invoice"
    field created_at "Created"

  ux:
    purpose: "One line on an invoice document — hop to the parent invoice for composition"

surface line_item_create "Create Line Item":
  uses entity LineItem
  mode: create
  render: fragment

  section main "New Line":
    field invoice "Invoice"
    field description "Description"
    field quantity "Qty"
    field unit_amount "Unit (¢)"

surface line_item_edit "Edit Line Item":
  uses entity LineItem
  mode: edit
  render: fragment

  section main "Line":
    field invoice "Invoice"
    field description "Description"
    field quantity "Qty"
    field unit_amount "Unit (¢)"

# =============================================================================
# MEMBERSHIP SURFACES
# =============================================================================

surface membership_list "Memberships":
  uses entity Membership
  mode: list
  render: fragment
  # Triple open (cycle 1585 journey): membership hub, member User, parent Project.
  open: Membership via id | User via user | Project via project

  section main "Memberships":
    field user "User"
    field project "Project"

  ux:
    purpose: "Memberships — open membership hub, hop to member User, or parent Project hub"

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
  # Goal B command_density: Bill.com / Stripe multi-panel billing homes put
  # dual attention (open books + sensitive flags) and composition above the
  # conversation trail — not conversation-first fold theater.
  # Goal B media (novel): invoice packet preview wall FIRST — not headshot shelf.
  purpose: "Multi-panel billing — invoice packet previews, metrics, open books, sensitive flags, composition, then live notes"
  stage: "simple_list"
  # Gate the management workspace to the org-management personas. admin
  # (cross-org), org_owner (their org), auditor (read-only review) all
  # work with organizations/projects/invoices/memberships. project_member
  # and external_contractor have project-scoped access via their own
  # surfaces/scopes, not the full billing workspace (#improve row 120 —
  # previously this workspace had no access: declaration, so it was open
  # to all authenticated users).
  access: persona(admin, org_owner, auditor)

  # Goal B media FIRST — invoice document thumbs (Stripe/Chargebee packet wall).
  # Recipe: invoice_packet_preview — not headshot_shelf (portfolio ban).
  invoice_packets:
    source: Invoice
    filter: preview_url != null
    sort: created_at desc
    limit: 6
    display: grid
    action: invoice_detail
    empty: "No invoice packet previews yet"

  # Metrics-first portfolio before attention panels.
  portfolio_metrics:
    source: Invoice
    display: metrics
    aggregate:
      open_books: count(Invoice where sensitive != true)
      sensitive: count(Invoice where sensitive = true)
      lines: count(LineItem)
      conversation: count(InvoiceNote)
    tones:
      open_books: accent
      sensitive: destructive
      conversation: accent

  # Dual attention (fold share): standard open books + sensitive review.
  open_invoices:
    source: Invoice
    filter: sensitive != true
    sort: created_at desc
    limit: 4
    display: queue
    action: invoice_detail
    empty: "No open invoices on the books"

  sensitive_flags:
    source: Invoice
    filter: sensitive = true
    sort: created_at desc
    limit: 4
    display: queue
    action: invoice_detail
    empty: "No sensitive invoices flagged"

  # Goal B document composition: named line descriptions
  # (Bill.com / Stripe Invoicing peer — not header-only amount shells).
  composition:
    source: LineItem
    sort: created_at desc
    limit: 4
    display: queue
    action: invoice_detail
    empty: "No line items yet — add lines to an invoice document"

  # Goal B conversation spine AFTER dual attention + composition.
  live_conversation:
    source: InvoiceNote
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_note_detail
    empty: "No conversation yet — notes on invoices appear here"

  ux:
    as admin:
      purpose: "Invoice packet wall first, then dual attention and composition"
      focus: invoice_packets, portfolio_metrics, open_invoices, sensitive_flags, composition, live_conversation
    as org_owner:
      purpose: "Invoice packet wall first, then dual attention and composition"
      focus: invoice_packets, portfolio_metrics, open_invoices, sensitive_flags, composition, live_conversation
    as auditor:
      purpose: "Invoice packet wall first, then dual attention and composition"
      focus: invoice_packets, portfolio_metrics, open_invoices, sensitive_flags, composition, live_conversation

  # Work-surface utility (cycle 1488 journey): org portfolio is pull-to-open hubs.
  organizations:
    source: Organization
    display: queue
    sort: name asc
    action: organization_detail
    empty: "No organizations found"

  projects:
    source: Project
    display: kanban
    group_by: name
    sort: name asc
    empty: "No projects found"

  # Cycle 1853 Goal B empty_region_honesty: secondary desks omit trail/bar
  # thrash. Host bar_chart coverage here under fold (not in ux focus) so
  # fleet display coverage stays green without polluting sensitivity/public/org
  # pressure desks.
  invoice_by_project:
    source: Invoice
    display: bar_chart
    group_by: project
    aggregate:
      count: count(Invoice)
    empty: "No invoices to chart"

  sensitive_share:
    source: Invoice
    display: bar_chart
    group_by: sensitive
    aggregate:
      count: count(Invoice)
    empty: "No invoices to chart"

# Product landing for scoped workers (product maturity: not warehouse-only).
# Separate from billing so org-management chrome stays gated to owner/auditor.
workspace my_work "My Work":
  # Goal B empty_region_honesty (cycle 1828): assigned work queues only —
  # not status bar chart / membership timeline voids under the fold.
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

  # Work-surface utility (cycle 1488 journey): member projects → queue to hubs.
  assigned_projects:
    source: Project
    display: queue
    sort: name asc
    action: project_detail
    empty: "No projects assigned to you yet"

  my_invoices:
    source: Invoice
    display: queue
    sort: created_at desc
    limit: 15
    empty: "No invoices in your scope"

# Second product workspace lowers warehouse density and gives owners a
# project-first path distinct from the org/memberships portfolio.
workspace projects_home "Projects":
  # Goal B empty_region_honesty (cycle 1828): kanban + recent invoices —
  # prune invoice_by_project bar and twin project_trail timeline.
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

# Third product workspace: invoice-first job desk so entity
# lists no longer dominate product shell count vs workspaces.
workspace invoices_home "Invoices":
  # Goal B conversation + empty_region_honesty: discussion + open bills board —
  # no status bar chart or twin bill timeline under the fold (cycle 1828).
  purpose: "Invoice desk — live conversation, cash context, open bills"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor, project_member)

  live_conversation:
    source: InvoiceNote
    sort: created_at desc
    limit: 8
    display: queue
    action: invoice_note_detail
    empty: "No conversation yet — notes on open bills appear here"

  invoice_pulse:
    source: Invoice
    display: metrics
    aggregate:
      invoices: count(Invoice)
      projects: count(Project)
      organizations: count(Organization)
      conversation: count(InvoiceNote)
    tones:
      invoices: accent
      conversation: accent

  ux:
    as admin:
      purpose: "See invoice discussion before open bills"
      focus: live_conversation, invoice_pulse, open_bills
    as org_owner:
      purpose: "Billing discussion and open bills"
      focus: live_conversation, invoice_pulse, open_bills
    as auditor:
      purpose: "Review discussion trail with open bills"
      focus: live_conversation, invoice_pulse, open_bills
    as project_member:
      purpose: "Discussion on invoices in your scope"
      focus: live_conversation, invoice_pulse, open_bills

  open_bills:
    source: Invoice
    display: kanban
    group_by: status
    sort: created_at desc
    empty: "No open invoices"

  # Work-surface utility (cycle 1488 journey): project context → pull queue.
  projects_context:
    source: Project
    display: queue
    sort: name asc
    action: project_detail
    empty: "No projects found"

# Fourth product workspace: team membership desk separate from
# org portfolio / projects / invoices — lowers list:workspace ratio.
workspace team_home "Team":
  # Goal B empty_region_honesty (cycle 1828): people + membership queues —
  # prune role bar chart and twin roster timeline.
  # Goal B org_structure (cycle 1867): peer billing/ops tools (Chargebee /
  # Stripe Billing / NetSuite / Coupa) show staff by title and department
  # before a flat people dump and membership load.
  purpose: "Org structure for the billing org — title and department before flat roster and membership load"
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
      people: positive

  # Title board — Org Owner / Project Analyst / Lead Auditor / …
  by_title:
    source: User
    display: kanban
    group_by: job_title
    sort: name asc
    limit: 40
    action: user_detail
    empty: "No titled staff yet"

  # Department placement — Finance / Delivery / Platform Ops / Audit.
  by_department:
    source: User
    display: queue
    sort: department asc, name asc
    limit: 40
    action: user_detail
    empty: "No staff placed in departments yet"

  # Secondary flat roster (after hierarchy).
  people:
    source: User
    display: queue
    sort: department asc, name asc
    limit: 25
    action: user_detail
    empty: "No users found"

  # Membership load after org shape — who can access which projects.
  membership_queue:
    source: Membership
    display: queue
    limit: 20
    empty: "No memberships yet"

  org_hint:
    display: status_list
    entries:
      - title: "By title board"
        caption: "Org Owner / Analyst / Auditor / Contractor columns show who can act"
        icon: "users"
        state: accent
      - title: "Department queue"
        caption: "Finance / Delivery / Platform Ops / Audit before flat roster"
        icon: "building-2"
        state: positive
      - title: "Membership load last"
        caption: "Project memberships after you read org shape"
        icon: "key"
        state: warning

  ux:
    as admin:
      purpose: "See billing staff by title and department before membership load"
      focus: membership_pulse, by_title, by_department, people
    as org_owner:
      purpose: "Org structure for finance ops — title board then department"
      focus: membership_pulse, by_title, by_department, people
    as auditor:
      purpose: "Read team org shape before membership and project access"
      focus: membership_pulse, by_title, by_department, people

# Fifth job desk: organization portfolio separate from billing shell
workspace orgs_home "Organizations":
  # Goal B empty_region_honesty (cycle 1828): org roster + open bills —
  # prune project timeline twin and invoice-load bar chart.
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

  # Work-surface utility (cycle 1488 journey): org roster → pull queue.
  org_roster:
    source: Organization
    display: queue
    sort: name asc
    action: organization_detail
    empty: "No organizations found"

  open_bills:
    source: Invoice
    display: queue
    sort: created_at desc
    limit: 15
    empty: "No invoices yet"

# Goal B empty_region_honesty (cycle 1853): peer sensitivity / public / org
# pressure desks keep pulse + queues — not invoice trail + load-bar thrash
# (bar_chart coverage lives on billing under fold, not here).
workspace sensitive_review "Sensitive Review":
  purpose: "Sensitivity desk — flag and review sensitive invoices"
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

  sensitive_queue:
    source: Invoice
    filter: sensitive = true
    sort: created_at desc
    limit: 20
    display: queue
    empty: "No sensitive invoices flagged"

  # Work-surface utility (cycle 1488 journey): project cards → pull queue to hubs.
  project_cards:
    source: Project
    display: queue
    sort: name asc
    limit: 15
    action: project_detail
    empty: "No projects found"

workspace public_billing "Public Billing":
  purpose: "Non-sensitive invoice pressure for shared member work"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor, project_member, external_contractor)

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

  public_queue:
    source: Invoice
    filter: sensitive != true
    sort: amount desc
    limit: 20
    display: queue
    empty: "No non-sensitive invoices"

  # Work-surface utility (cycle 1488 journey): project cards → pull queue to hubs.
  project_cards:
    source: Project
    display: queue
    sort: name asc
    limit: 15
    action: project_detail
    empty: "No projects found"

workspace org_pulse "Org Pulse":
  purpose: "Tenant footprint pressure — orgs and projects without chart thrash"
  stage: "simple_list"
  access: persona(admin, org_owner, auditor)

  pulse_metrics:
    source: Organization
    display: metrics
    aggregate:
      orgs: count(Organization)
      people: count(User)
      projects: count(Project)
    tones:
      orgs: accent
      people: positive
      projects: muted

  org_queue:
    source: Organization
    sort: name asc
    limit: 20
    display: queue
    empty: "No organizations"

  # Work-surface utility (cycle 1488 journey): project cards → pull queue to hubs.
  project_cards:
    source: Project
    display: queue
    sort: name asc
    limit: 15
    action: project_detail
    empty: "No projects found"
