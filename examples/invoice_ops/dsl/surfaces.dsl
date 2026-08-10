module invoice_ops.surfaces

use invoice_ops.entities

# =============================================================================
# INVOICE SURFACES
# =============================================================================

surface invoice_list "Invoices":
  uses entity Invoice
  mode: list
  # Triple open (story_walk dig cycle 1597): invoice hub, supplier vendor,
  # submitter teammate (when submitted_by is set).
  open: Invoice via id | Supplier via supplier | User via submitted_by
  section main:
    field invoice_number "Number"
    field amount "Amount" format: currency:GBP
    field currency "Currency"
    field status "Status"
    field submitted_by "Submitted By"
  ux:
    purpose: "Browse invoices — open invoice hub, supplier context, or submitter hub"

surface invoice_detail "Invoice":
  uses entity Invoice
  mode: view
  section summary "Summary":
    field invoice_number "Number"
    field supplier "Supplier"
    field amount "Amount" format: currency:GBP
    field currency "Currency"
  section status "Status":
    layout: strip
    field status "Status"
    field po_number "PO Number"
  section review "Review notes":
    field rejection_reason "Rejection Reason"
    field dispute_reason "Dispute Reason"
    field submitted_by "Submitted By"
  # Document composition (Goal B): line items are the invoice body, not a
  # warehouse table — ST-002/003/005 acceptance path scans composition then
  # settlement trail.
  related lines "Line items":
    display: queue
    show: LineItem
    columns: description, quantity, unit_amount
    limit: 8
  # Goal B document: named AP packets (remittance / credit memo / PO) on the hub.
  related documents "Documents":
    display: queue
    show: InvoiceDocument
    columns: headline, doc_kind, status, author
    limit: 6
  related payments "Payment attempts":
    display: queue
    show: PaymentAttempt
    columns: attempt_number, status, failure_reason, created_at
    limit: 5
  # Goal B conversation: AP discussion pull queue on the invoice hub.
  related discussion "Discussion":
    display: queue
    show: InvoiceNote
    columns: body, author, created_at
    limit: 5
  ux:
    purpose: "Invoice document — header, line composition, named packets, discussion, and payment trail"

surface invoice_create "New Invoice":
  uses entity Invoice
  mode: create
  section main:
    field invoice_number "Number"
    field supplier "Supplier"
    field amount "Amount"
    field currency "Currency"

surface invoice_note_list "Invoice Notes":
  uses entity InvoiceNote
  mode: list
  open: InvoiceNote via id | Invoice via invoice
  section main:
    field body "Note"
    field author "Author"
    field invoice "Invoice"
    field created_at "When"
  ux:
    purpose: "AP discussion — open a note or its parent invoice"
    sort: created_at desc
    search: body, author
    empty: "No invoice notes yet"

surface invoice_note_detail "Invoice Note":
  uses entity InvoiceNote
  mode: view
  section summary "Note":
    field body "Note"
    field author "Author"
    field invoice "Invoice"
    field created_at "When"
  ux:
    purpose: "Read an AP discussion note in context of its parent invoice"

surface invoice_note_create "Add Invoice Note":
  uses entity InvoiceNote
  mode: create
  section main:
    field invoice "Invoice"
    field author "Author"
    field body "Note"

# =============================================================================
# SUPPLIER SURFACES
# =============================================================================

surface supplier_list "Suppliers":
  uses entity Supplier
  mode: list
  # Dual open: supplier hub first, tenant root second (multi-tenant AP admin).
  open: Supplier via id | Tenant via tenant_id
  section main:
    field name "Name"
    field contact_email "Contact"
    field region "Region"
  ux:
    purpose: "Browse suppliers by region — open supplier hub or hop to tenant root"
    filter: region
    search: name, contact_email, region
    sort: name asc

surface supplier_detail "Supplier":
  uses entity Supplier
  mode: view
  section identity "Identity":
    field name "Name"
    field contact_email "Contact"
    field region "Region"
  related bank "Bank accounts":
    display: queue
    show: SupplierBankAccount
  related invoices "Invoices":
    display: queue
    show: Invoice
    columns: invoice_number, amount, status
  ux:
    purpose: "Supplier hub — identity, bank-ref queue, and invoice history queue"

# =============================================================================
# PAYMENT ATTEMPT SURFACES
# =============================================================================

surface payment_attempt_list "Payment Attempts":
  uses entity PaymentAttempt
  mode: list
  # Triple open (story_walk dig cycle 1597): attempt hub, parent invoice, tenant root.
  open: PaymentAttempt via id | Invoice via invoice | Tenant via tenant_id
  section main:
    field invoice "Invoice"
    field attempt_number "Attempt"
    field status "Status"
    field failure_reason "Failure Reason"
  ux:
    purpose: "Payment trail — open a row for the attempt, invoice, or tenant hub"

# View surface so dual-open PaymentAttempt via id lands a readable attempt note.
surface payment_attempt_detail "Payment Attempt":
  uses entity PaymentAttempt
  mode: view
  section summary "Attempt":
    field invoice "Invoice"
    field attempt_number "Attempt"
    field status "Status"
  section provider "Provider":
    layout: strip
    field provider_reference "Provider reference"
    field failure_reason "Failure Reason"
  ux:
    purpose: "Read one settlement attempt with invoice context"

surface payment_attempt_create "New Payment Attempt":
  uses entity PaymentAttempt
  mode: create
  section main:
    field invoice "Invoice"
    field attempt_number "Attempt"
    field status "Status"
    field provider_reference "Provider reference"
  ux:
    purpose: "Record a settlement attempt against an approved invoice"

# =============================================================================
# AUDIT EXPORT SURFACE
# =============================================================================

# NOTE: a second `mode: list` surface on Invoice (e.g. an "Audit Export" view)
# can't be reached — it resolves to the same GET /invoices route as invoice_list
# and is dropped at boot (#1489). For a secondary invoice view, use a workspace
# region or a filtered list, not a second list surface on the same entity.

# =============================================================================
# TENANT SURFACES
# =============================================================================

surface tenant_list "Tenants":
  uses entity Tenant
  mode: list
  open: Tenant via id
  section main:
    field name "Name"
    field region "Region"
    field status "Status"
  ux:
    purpose: "Tenant roster — open a row for the tenant hub"

surface tenant_detail "Tenant":
  uses entity Tenant
  mode: view
  section identity "Identity":
    field name "Name"
    field slug "Slug"
  section ops "Ops":
    layout: strip
    field region "Region"
    field status "Status"
  related people "Users":
    display: queue
    show: User
    columns: name, email
  related suppliers "Suppliers":
    display: queue
    show: Supplier
    columns: name, region, contact_email
  ux:
    purpose: "Tenant hub — identity, people queue, and supplier roster queue"

# =============================================================================
# USER SURFACES
# =============================================================================

surface user_list "Users":
  uses entity User
  mode: list
  # Dual open: person hub first, tenant root second (admin roster context).
  open: User via id | Tenant via tenant_id
  section main:
    field photo_url "Photo"
    field email "Email"
    field name "Name"
    field job_title "Job Title"
    field department "Department"
    field tenant_id "Tenant"
  ux:
    purpose: "Team roster — open person hub or hop to tenant root"
    sort: department asc, name asc
    filter: department, job_title
    search: name, email, department, job_title

surface user_detail "User":
  uses entity User
  mode: view
  section identity "Identity":
    field photo_url "Photo"
    field name "Name"
    field email "Email"
  section org "Org placement":
    layout: strip
    field job_title "Job Title"
    field department "Department"
  section tenant_link "Tenant":
    layout: strip
    field tenant_id "Tenant"
  related invoices_raised "Invoices raised":
    display: queue
    show: Invoice
    columns: invoice_number, amount, status
  ux:
    purpose: "Person hub — identity, org placement, and submitted-invoice pull queue"

# =============================================================================
# LINE ITEM SURFACES
# =============================================================================

surface line_item_list "Line Items":
  uses entity LineItem
  mode: list
  # Triple open: line hub, parent invoice, tenant root (ST-005 path + multi-tenant AP).
  open: LineItem via id | Invoice via invoice | Tenant via tenant_id
  section main:
    field invoice "Invoice"
    field description "Description"
    field quantity "Qty"
    field unit_amount "Unit Amount" format: currency:GBP
  ux:
    purpose: "Document lines — open a row for the line, parent invoice document, or tenant root"

# Explicit VIEW so related-table drills and synthetic #1421 detail routes
# share one authored surface (substrate + sections) instead of an empty shell.
surface lineitem_detail "Line Item":
  uses entity LineItem
  mode: view
  section main "Line":
    field invoice "Invoice"
    field description "Description"
    field quantity "Qty"
    field unit_amount "Unit Amount" format: currency:GBP
  ux:
    purpose: "One line on an invoice document — hop to the parent invoice for composition + settlement"

# =============================================================================
# INVOICE DOCUMENT SURFACES (Goal B document composition — named AP packets)
# =============================================================================

surface invoice_document_list "Invoice Documents":
  uses entity InvoiceDocument
  mode: list
  # Dual open: document hub first; parent Invoice document second.
  open: InvoiceDocument via id | Invoice via invoice
  section main:
    field headline "Headline"
    field invoice "Invoice"
    field doc_kind "Kind"
    field status "Status"
    field author "Author"
    field created_at "Created"
  ux:
    purpose: "Scan remittance, credit memos, and PO packets — open a row for the packet or parent invoice"
    sort: created_at desc
    filter: doc_kind, status
    search: headline, body, author
    empty: "No invoice documents yet — attach a remittance or PO packet on an invoice hub"

surface invoice_document_detail "Invoice Document":
  uses entity InvoiceDocument
  mode: view
  section summary "Document":
    field headline "Headline"
    field invoice "Invoice"
    field doc_kind "Kind"
    field author "Author"
  section lifecycle "Lifecycle":
    layout: strip
    field status "Status"
    field created_at "Created"
  section body "Body":
    field body "Body"
  ux:
    purpose: "Invoice document hub — named packet, lifecycle strip, parent invoice, and body in one place"

surface invoice_document_create "Add Invoice Document":
  uses entity InvoiceDocument
  mode: create
  section main "New document":
    field invoice "Invoice"
    field headline "Headline"
    field doc_kind "Kind"
    field body "Body"
    field status "Status"
    field author "Author"
  ux:
    purpose: "Attach a named remittance, credit memo, or PO packet to an invoice"

surface invoice_document_edit "Edit Invoice Document":
  uses entity InvoiceDocument
  mode: edit
  section main "Edit document":
    field headline "Headline"
    field doc_kind "Kind"
    field body "Body"
    field status "Status"
    field author "Author"
  ux:
    purpose: "Update invoice document headline, kind, or status"

# =============================================================================
# INVOICE EDIT SURFACE — generates PUT /invoices/{id} + drives state machine
# =============================================================================

surface invoice_edit "Edit Invoice":
  uses entity Invoice
  mode: edit
  section main:
    field invoice_number "Number"
    field supplier "Supplier"
    field amount "Amount"
    field currency "Currency"
    field status "Status"
    field rejection_reason "Rejection Reason"
    field dispute_reason "Dispute Reason"

# =============================================================================
# SUPPLIER CREATE / EDIT SURFACES — tenant_admin & finance manage suppliers
# =============================================================================

surface supplier_create "New Supplier":
  uses entity Supplier
  mode: create
  section main:
    field name "Name"
    field contact_email "Contact"
    field region "Region"

surface supplier_edit "Edit Supplier":
  uses entity Supplier
  mode: edit
  section main:
    field name "Name"
    field contact_email "Contact"
    field region "Region"

surface supplier_bank_account_list "Supplier Bank Accounts":
  uses entity SupplierBankAccount
  mode: list
  # Triple open: bank-ref hub, supplier hub, tenant root (finance isolation path).
  open: SupplierBankAccount via id | Supplier via supplier | Tenant via tenant_id
  section main:
    field supplier "Supplier"
    field bank_account_ref "Bank Ref"
    field account_name "Account Name"
  ux:
    purpose: "Bank refs — open a row for the bank hub, parent supplier hub, or tenant root"

surface supplier_bank_account_detail "Supplier Bank Account":
  uses entity SupplierBankAccount
  mode: view
  section summary "Account":
    field supplier "Supplier"
    field bank_account_ref "Bank Ref"
    field account_name "Account Name"
  ux:
    purpose: "Read one supplier bank reference with supplier context"

surface supplier_bank_account_edit "Edit Supplier Bank Account":
  uses entity SupplierBankAccount
  mode: edit
  section main:
    field bank_account_ref "Bank Ref"
    field account_name "Account Name"
    field iban "IBAN"

# =============================================================================
# USER CREATE / EDIT SURFACES — tenant_admin manages domain users
# (user_edit deliberately omits tenant_id — users must not be moved between tenants)
# =============================================================================

surface user_create "New User":
  uses entity User
  mode: create
  section main:
    field photo_url "Photo URL"
    field email "Email"
    field name "Name"
    field job_title "Job Title"
    field department "Department"
    field tenant_id "Tenant"

surface user_edit "Edit User":
  uses entity User
  mode: edit
  section main:
    field photo_url "Photo URL"
    field email "Email"
    field name "Name"
    field job_title "Job Title"
    field department "Department"

# =============================================================================
# LINE ITEM CREATE SURFACE — requester adds line items to an invoice
# =============================================================================

surface lineitem_create "New Line Item":
  uses entity LineItem
  mode: create
  section main:
    field invoice "Invoice"
    field description "Description"
    field quantity "Qty"
    field unit_amount "Unit Amount"

# ── Finance operations workspace (#1537) ─────────────────────────────────────
# The app's home surface for fleet capture rounds: a persona-homed
# workspace (the framework-injected `_platform_admin` is gated to
# framework roles and is never a capture target).
# Story-driven (docs/guides/story-to-composition.md): metrics + review
# queues — not bare invoice lists named "queue".
workspace finance_ops "Finance Operations":
  # Goal B media (cycle 1885) + conversation + document + empty_region
  # (1820/1879): peer AP tools (Bill.com / Tipalti / Coupa) put teammate
  # headshots first, then dual attention, named AP packets, line composition,
  # and live discussion — not name-only ops theater or funnel voids.
  purpose: "Day-to-day invoice throughput — headshots, dual attention, named packets, line composition, and live discussion"
  access: persona(requester, approver, finance, finance_admin, auditor, tenant_admin)

  # Goal B media FIRST — finance ops home is a people shelf (photo_url thumbs).
  # Newest department staff first so non-STABLE seeded faces win the fold;
  # STABLE auth-mirror rows get photo_url via media enrichment (#1630).
  media_shelf:
    source: User
    filter: department != null and photo_url != null
    display: grid
    sort: created_at desc
    limit: 4
    action: user_detail
    empty: "No teammate headshots yet — add photo URLs on team members"

  ops_metrics:
    source: Invoice
    display: metrics
    aggregate:
      submitted: count(Invoice where status = submitted)
      approved: count(Invoice where status = approved)
      disputed: count(Invoice where status = disputed)
      conversation: count(InvoiceNote)
    tones:
      submitted: warning
      disputed: destructive
      conversation: accent
      approved: accent

  # Goal B document metric — named AP packets only (InvoiceDocument source).
  # Cross-entity count(LineItem) / count(Invoice) under this source paints 0
  # theater; line body pulse lives on line_items_desk / my_invoices.
  document_pulse:
    source: InvoiceDocument
    display: metrics
    aggregate:
      documents: count(InvoiceDocument)
      published: count(InvoiceDocument where status = published)
      draft: count(InvoiceDocument where status = draft)
    tones:
      documents: accent
      published: positive
      draft: warning

  # Goal B document composition ABOVE dual attention — named remittance /
  # credit memo / PO packets so hero stills read packet titles above the fold.
  composition:
    source: InvoiceDocument
    sort: created_at desc
    limit: 5
    display: queue
    action: invoice_document_detail
    empty: "No invoice documents yet — attach a remittance or PO packet on an invoice hub"

  # Dual attention after named packets (fold share with capped conversation).
  awaiting_approval:
    source: Invoice
    filter: status = submitted
    sort: amount desc
    limit: 3
    display: queue
    action: invoice_detail
    empty: "Nothing awaiting approval"

  ready_to_pay:
    source: Invoice
    filter: status = approved
    sort: amount desc
    limit: 3
    display: queue
    action: invoice_detail
    empty: "Nothing ready to pay"

  # Line body under dual attention (still domain-true composition, not warehouse).
  line_composition:
    source: LineItem
    sort: created_at desc
    limit: 4
    display: queue
    action: invoice_detail
    empty: "No line items yet — add lines to a draft invoice"

  # Goal B conversation spine AFTER packets + dual attention.
  # display: conversation → MessageScroller / Message + Bubble (not queue meta rows).
  live_conversation:
    source: InvoiceNote
    sort: created_at desc
    limit: 4
    display: conversation
    action: invoice_note_detail
    empty: "No conversation yet — approval and payment notes appear here"

  disputed_queue:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 8
    display: queue
    action: invoice_detail
    empty: "No disputes open"

  ops_board:
    source: Invoice
    filter: status != draft
    display: kanban
    group_by: status
    sort: amount desc
    action: invoice_detail
    empty: "No invoices in the pipeline"

  ux:
    as finance_admin:
      purpose: "AP ops — headshots, document pulse, named packets, dual attention, then discussion"
      focus: media_shelf, ops_metrics, document_pulse, composition, awaiting_approval, ready_to_pay, line_composition, live_conversation
    as tenant_admin:
      purpose: "AP ops — headshots, document pulse, named packets, dual attention, then discussion"
      focus: media_shelf, ops_metrics, document_pulse, composition, awaiting_approval, ready_to_pay, line_composition, live_conversation
    as finance:
      purpose: "AP ops — headshots, named packets, then settle queues"
      focus: media_shelf, ops_metrics, document_pulse, composition, ready_to_pay, disputed_queue, live_conversation
    as approver:
      purpose: "AP ops — headshots, named packets, then review queue"
      focus: media_shelf, ops_metrics, document_pulse, composition, awaiting_approval, live_conversation
    as auditor:
      purpose: "AP ops — headshots, evidence packets with conversation spine"
      focus: media_shelf, ops_metrics, document_pulse, composition, live_conversation, disputed_queue
    as requester:
      purpose: "AP ops overview — headshots, packets, lines, and conversation"
      focus: media_shelf, ops_metrics, composition, line_composition, live_conversation, awaiting_approval

# ── Job workspaces (product maturity: anti-warehouse) ────────────────────────
# Separate product landings per role so density is not one mega-desk + 9 lists.
# finance_ops remains the shared ops overview for admin/oversight personas.

workspace my_invoices "My Invoices":
  # Goal B document + empty_region (cycle 1820): requester home shows line
  # composition + draft/submit queues + kanban — not status bar-chart voids or
  # twin invoice timelines under the fold.
  purpose: "Requester desk — line composition, drafts, submissions, and line-item work on my invoices"
  access: persona(requester)

  my_pipeline:
    source: Invoice
    display: metrics
    aggregate:
      draft: count(Invoice where status = draft)
      submitted: count(Invoice where status = submitted)
      approved: count(Invoice where status = approved)
      paid: count(Invoice where status = paid)
    tones:
      draft: warning
      submitted: accent
      paid: positive

  # Goal B document metric from LineItem source (honest line count).
  document_pulse:
    source: LineItem
    display: metrics
    aggregate:
      documents: count(LineItem)
    tones:
      documents: accent

  # Goal B document spine on requester home — composition lines pull open the
  # parent invoice document hub (description as title).
  composition:
    source: LineItem
    sort: created_at desc
    limit: 12
    display: queue
    action: invoice_detail
    empty: "No line items yet — add lines to a draft invoice"

  drafts:
    source: Invoice
    filter: status = draft
    sort: updated_at desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "No draft invoices — create one to get started"

  in_flight:
    source: Invoice
    filter: status = submitted
    sort: amount desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "Nothing waiting on approval"

  my_status_board:
    source: Invoice
    filter: status = draft or status = submitted or status = approved or status = paid
    display: kanban
    group_by: status
    sort: updated_at desc
    action: invoice_detail
    empty: "No invoices yet"

  suppliers_nearby:
    source: Supplier
    sort: name asc
    limit: 10
    display: queue
    action: supplier_detail
    empty: "No suppliers yet"

  ux:
    as requester:
      purpose: "My invoices — composition and draft/submit queues (no chart voids)"
      focus: my_pipeline, document_pulse, composition, drafts, in_flight, my_status_board

workspace approval_desk "Approval Desk":
  # Goal B document (cycle 1879): peer AP approval homes (Bill.com / Coupa)
  # put named remittance / PO packets above the discussion trail — not notes-only.
  purpose: "Approver job — awaiting queue, named AP packets, then live discussion"
  access: persona(approver, finance_admin)

  approval_load:
    source: Invoice
    display: metrics
    aggregate:
      awaiting: count(Invoice where status = submitted)
      approved: count(Invoice where status = approved)
      conversation: count(InvoiceNote)
    tones:
      awaiting: warning
      approved: positive
      conversation: accent

  # Honest document counts — source InvoiceDocument (not cross-entity under Invoice).
  document_pulse:
    source: InvoiceDocument
    display: metrics
    aggregate:
      documents: count(InvoiceDocument)
      published: count(InvoiceDocument where status = published)
    tones:
      documents: accent
      published: positive

  # Goal B document composition — named packets before conversation trail.
  composition:
    source: InvoiceDocument
    sort: created_at desc
    limit: 5
    display: queue
    action: invoice_document_detail
    empty: "No invoice documents yet — attach a remittance or PO packet on an invoice hub"

  awaiting_approval:
    source: Invoice
    filter: status = submitted
    sort: amount desc
    limit: 6
    display: queue
    action: invoice_detail
    empty: "Nothing awaiting approval"

  # display: conversation → Message/Bubble chrome (not queue meta of note rows).
  live_conversation:
    source: InvoiceNote
    sort: created_at desc
    limit: 6
    display: conversation
    action: invoice_note_detail
    empty: "No conversation yet — notes on invoices in review appear here"

  approval_board:
    source: Invoice
    filter: status = submitted or status = approved or status = rejected
    display: kanban
    group_by: status
    sort: amount desc
    action: invoice_detail
    empty: "No invoices in the approval pipeline"

  suppliers_nearby:
    source: Supplier
    sort: name asc
    limit: 12
    display: queue
    action: supplier_detail
    empty: "No suppliers yet"

  ux:
    as approver:
      purpose: "Approval — named packets, queue, conversation (no decision-timeline dump)"
      focus: approval_load, document_pulse, composition, awaiting_approval, live_conversation
    as finance_admin:
      purpose: "Approval — named packets, queue, conversation (no decision-timeline dump)"
      focus: approval_load, document_pulse, composition, awaiting_approval, live_conversation

workspace pay_desk "Pay Desk":
  # Goal B command_density + document (cycle 1820/1879): dual attention then
  # remittance / payment-confirmation packets before notes.
  purpose: "Multi-panel settlement — dual attention, named packets, then live AP notes"
  access: persona(finance, finance_admin)

  settle_metrics:
    source: Invoice
    display: metrics
    aggregate:
      ready: count(Invoice where status = approved)
      disputed: count(Invoice where status = disputed)
      conversation: count(InvoiceNote)
    tones:
      ready: accent
      disputed: destructive
      conversation: accent

  # Honest document pulse (InvoiceDocument source — not cross-entity under Invoice).
  document_pulse:
    source: InvoiceDocument
    display: metrics
    aggregate:
      documents: count(InvoiceDocument)
      published: count(InvoiceDocument where status = published)
    tones:
      documents: accent
      published: positive

  # Goal B document composition — remittance / payment-confirmation packets
  # above dual attention so hero stills show titles above the fold.
  composition:
    source: InvoiceDocument
    sort: created_at desc
    limit: 4
    display: queue
    action: invoice_document_detail
    empty: "No invoice documents yet — attach remittance or payment confirmation"

  # Dual attention after named packets.
  ready_to_pay:
    source: Invoice
    filter: status = approved
    sort: amount desc
    limit: 3
    display: queue
    action: invoice_detail
    empty: "Nothing ready to pay"

  disputed_queue:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 3
    display: queue
    action: invoice_detail
    empty: "No disputes open"

  # Goal B conversation spine AFTER packets + dual attention.
  # display: conversation → Message/Bubble chrome (not queue meta of note rows).
  live_conversation:
    source: InvoiceNote
    sort: created_at desc
    limit: 5
    display: conversation
    action: invoice_note_detail
    empty: "No conversation yet — payment and dispute notes appear here"

  ux:
    as finance:
      purpose: "Multi-panel settlement — packets, dual attention, then live AP notes"
      focus: settle_metrics, document_pulse, composition, ready_to_pay, disputed_queue, live_conversation
    as finance_admin:
      purpose: "Multi-panel settlement — packets, dual attention, then live AP notes"
      focus: settle_metrics, document_pulse, composition, ready_to_pay, disputed_queue, live_conversation

  settle_board:
    source: Invoice
    filter: status = approved or status = disputed or status = paid
    display: kanban
    group_by: status
    sort: updated_at desc
    action: invoice_detail
    empty: "No invoices in settle pipeline"

workspace audit_review "Audit Review":
  purpose: "Auditor job — payment trail and invoice evidence without warehouse CRUD"
  access: persona(auditor, finance_admin, tenant_admin)

  trail_metrics:
    source: Invoice
    display: metrics
    aggregate:
      paid: count(Invoice where status = paid)
      disputed: count(Invoice where status = disputed)
      attempts: count(PaymentAttempt)
    tones:
      disputed: destructive
      paid: positive

  # Work-surface utility: payment attempts are dated events → timeline.
  payment_attempts:
    source: PaymentAttempt
    display: timeline
    sort: created_at desc
    limit: 20
    empty: "No payment attempts to review"

  settled_invoices:
    source: Invoice
    filter: status = paid
    sort: updated_at desc
    limit: 15
    display: timeline
    action: invoice_detail
    empty: "No paid invoices yet"

  audit_mix:
    source: Invoice
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices to chart"

  disputed_queue:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "No disputes open"

  audit_board:
    source: Invoice
    filter: status = paid or status = disputed or status = rejected
    display: kanban
    group_by: status
    sort: updated_at desc
    action: invoice_detail
    empty: "No invoices in the audit trail"

# Sixth product workspace: supplier / vendor desk so list shells
# no longer dominate vs job workspaces (vendors + bank refs, not bare CRUD).
# Goal B org_structure (cycle 1863): peer AP tools (Tipalti / Bill.com / Coupa)
# show vendor geography and multi-invoice supplier load before a flat A–Z
# roster + status bar dump — buyers call suppliers by region and account load.
workspace suppliers_desk "Suppliers":
  purpose: "Vendor org structure — region board and multi-invoice load before flat roster"
  access: persona(finance, tenant_admin, finance_admin, approver)

  vendor_pulse:
    source: Supplier
    display: metrics
    aggregate:
      suppliers: count(Supplier)
      bank_accounts: count(SupplierBankAccount)
      invoices: count(Invoice)
    tones:
      suppliers: accent

  # Region board — geographic org of the vendor book (EMEA / AMER / APAC).
  by_region:
    source: Supplier
    display: kanban
    group_by: region
    sort: name asc
    limit: 24
    action: supplier_detail
    empty: "No suppliers in this region"

  # Multi-invoice supplier placement — open AP load grouped by vendor before
  # flat recents (not a warehouse A–Z dump of invoices).
  by_supplier:
    source: Invoice
    filter: status != paid and status != rejected
    display: kanban
    group_by: supplier
    sort: amount desc
    limit: 30
    action: invoice_detail
    empty: "No open invoices by supplier"

  # Secondary flat roster after hierarchy.
  roster:
    source: Supplier
    display: queue
    sort: name asc
    limit: 25
    action: supplier_detail
    empty: "No suppliers yet"

  bank_refs:
    source: SupplierBankAccount
    display: queue
    limit: 20
    empty: "No bank accounts on file"

  recent_invoices:
    source: Invoice
    sort: updated_at desc
    limit: 12
    display: queue
    action: invoice_detail
    empty: "No invoices yet"

  ux:
    as finance:
      purpose: "Vendor org structure — region and multi-invoice load before flat roster"
      focus: vendor_pulse, by_region, by_supplier, roster, bank_refs
    as finance_admin:
      purpose: "Vendor org structure — region board then supplier AP load"
      focus: vendor_pulse, by_region, by_supplier, roster, bank_refs
    as tenant_admin:
      purpose: "Vendor org shape — region board then open invoices by supplier"
      focus: vendor_pulse, by_region, by_supplier, roster
    as approver:
      purpose: "See which region and supplier carries open AP before flat recents"
      focus: vendor_pulse, by_region, by_supplier, recent_invoices


# Seventh product workspace: tenant admin people desk.
workspace team_desk "Team":
  # Goal B org_structure (cycle 1863): peer AP tools (Coupa / Bill.com / NetSuite)
  # show finance staff by job title and department before open invoice load —
  # admins reassign and audit from org shape, not a flat people dump.
  purpose: "Org structure for AP — title and department before flat roster and open load"
  access: persona(tenant_admin, finance_admin, auditor)

  team_pulse:
    source: User
    display: metrics
    aggregate:
      people: count(User)
      suppliers: count(Supplier)
      open_invoices: count(Invoice where status = submitted or status = approved)
    tones:
      people: accent
      open_invoices: warning

  # Title board — Requester / Approver / Finance / Auditor columns.
  by_title:
    source: User
    display: kanban
    group_by: job_title
    sort: name asc
    limit: 40
    action: user_detail
    empty: "No titled staff yet"

  # Department placement — AP / Treasury / Controllership / Audit before flat roster.
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
    empty: "No users yet"

  # Open load after org shape — who owns pressure, not before hierarchy.
  open_invoices:
    source: Invoice
    filter: status = submitted or status = approved
    sort: amount desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "Nothing awaiting action"

  org_hint:
    display: status_list
    entries:
      - title: "By title board"
        caption: "Requester / Approver / Finance / Auditor columns show who can act"
        icon: "users"
        state: accent
      - title: "Department queue"
        caption: "AP / Treasury / Controllership / Audit placement before flat roster"
        icon: "building-2"
        state: positive
      - title: "Open load last"
        caption: "Submitted and approved invoices after you read org shape"
        icon: "file-text"
        state: warning

  ux:
    as tenant_admin:
      purpose: "See staff by title and department before open invoice load"
      focus: team_pulse, by_title, by_department, people
    as finance_admin:
      purpose: "Org structure for finance oversight — role board then department"
      focus: team_pulse, by_title, by_department, people
    as auditor:
      purpose: "Read team org shape before open invoice pressure"
      focus: team_pulse, by_title, by_department, people

# Eighth product workspace: payment trail desk.
workspace payments_trail "Payments":
  purpose: "Payment attempt trail — health metrics and recent attempts"
  access: persona(finance, finance_admin, auditor)

  payment_pulse:
    source: PaymentAttempt
    display: metrics
    aggregate:
      attempts: count(PaymentAttempt)
      invoices: count(Invoice)
      paid: count(Invoice where status = paid)
    tones:
      paid: positive
      attempts: accent

  recent_attempts:
    source: PaymentAttempt
    sort: created_at desc
    limit: 25
    display: queue
    empty: "No payment attempts yet"

  settled:
    source: Invoice
    filter: status = paid
    sort: updated_at desc
    limit: 15
    display: timeline
    action: invoice_detail
    empty: "No paid invoices yet"

  ready_context:
    source: Invoice
    filter: status = approved
    sort: amount desc
    limit: 10
    display: queue
    action: invoice_detail
    empty: "Nothing ready to pay"

  settle_board:
    source: Invoice
    filter: status = approved or status = disputed or status = paid
    display: kanban
    group_by: status
    sort: amount desc
    action: invoice_detail
    empty: "No invoices in settle pipeline"

  attempt_health:
    source: PaymentAttempt
    display: bar_chart
    group_by: status
    aggregate:
      count: count(PaymentAttempt)
    empty: "No payment attempts"

# Ninth product workspace: invoice document composition desk (Goal B document).
# Peer tools (Bill.com / Tipalti) show line composition with invoice numbers —
# not UUID shells or bare CRUD lists.
workspace line_items_desk "Line Items":
  purpose: "Invoice document composition — line descriptions, qty × unit, open docs (not warehouse CRUD)"
  access: persona(requester, finance, finance_admin, auditor)

  line_pulse:
    source: LineItem
    display: metrics
    aggregate:
      lines: count(LineItem)
      invoices: count(Invoice)
      open_invoices: count(Invoice where status != paid and status != rejected)
    tones:
      open_invoices: accent
      lines: positive

  # Document body first (Goal B): composition lines pull open the parent
  # invoice document hub — description as title, invoice number + qty × unit
  # as meta (framework ref display resolves invoice_number).
  composition:
    source: LineItem
    sort: created_at desc
    limit: 25
    display: queue
    action: invoice_detail
    empty: "No line items yet — add lines to a draft invoice"

  # Open invoice documents still in flight (header roster under composition).
  open_documents:
    source: Invoice
    filter: status = draft or status = submitted or status = approved
    sort: updated_at desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "No open invoice documents"

  invoice_trail:
    source: Invoice
    sort: updated_at desc
    limit: 15
    display: timeline
    action: invoice_detail
    empty: "No invoices yet"

  invoice_status_mix:
    source: Invoice
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices to chart"
