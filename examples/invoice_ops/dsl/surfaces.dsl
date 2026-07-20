module invoice_ops.surfaces

use invoice_ops.entities

# =============================================================================
# INVOICE SURFACES
# =============================================================================

surface invoice_list "Invoices":
  uses entity Invoice
  mode: list
  open: Invoice via id
  section main:
    field invoice_number "Number"
    field amount "Amount" format: currency:GBP
    field currency "Currency"
    field status "Status"
  ux:
    purpose: "Browse invoices — open a row for the invoice hub"

surface invoice_detail "Invoice":
  uses entity Invoice
  mode: view
  section summary "Summary":
    field invoice_number "Number"
    field supplier "Supplier"
    field amount "Amount"
    field currency "Currency"
  section status "Status":
    layout: strip
    field status "Status"
    field po_number "PO Number"
  section review "Review notes":
    field rejection_reason "Rejection Reason"
    field dispute_reason "Dispute Reason"
    field submitted_by "Submitted By"
  related lines "Line items":
    display: table
    show: LineItem
    columns: description, quantity, unit_amount
  related payments "Payment attempts":
    display: table
    show: PaymentAttempt
    columns: attempt_number, status, failure_reason, created_at
  ux:
    purpose: "Invoice hub — status, lines, and settlement trail in one place"

surface invoice_create "New Invoice":
  uses entity Invoice
  mode: create
  section main:
    field invoice_number "Number"
    field supplier "Supplier"
    field amount "Amount"
    field currency "Currency"

# =============================================================================
# SUPPLIER SURFACES
# =============================================================================

surface supplier_list "Suppliers":
  uses entity Supplier
  mode: list
  open: Supplier via id
  section main:
    field name "Name"
    field contact_email "Contact"
    field region "Region"
  ux:
    purpose: "Browse suppliers — open a row for the supplier hub"

surface supplier_detail "Supplier":
  uses entity Supplier
  mode: view
  section identity "Identity":
    field name "Name"
    field contact_email "Contact"
    field region "Region"
  related bank "Bank accounts":
    display: table
    show: SupplierBankAccount
  related invoices "Invoices":
    display: table
    show: Invoice
    columns: invoice_number, amount, status
  ux:
    purpose: "Supplier hub — identity, bank refs, and invoice history"

# =============================================================================
# PAYMENT ATTEMPT SURFACES
# =============================================================================

surface payment_attempt_list "Payment Attempts":
  uses entity PaymentAttempt
  mode: list
  open: Invoice via invoice
  section main:
    field invoice "Invoice"
    field attempt_number "Attempt"
    field status "Status"
    field failure_reason "Failure Reason"
  ux:
    purpose: "Payment trail — open a row for the parent Invoice hub"

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
    display: table
    show: User
    columns: name, email
  related suppliers "Suppliers":
    display: table
    show: Supplier
    columns: name, region, contact_email
  ux:
    purpose: "Tenant hub — identity, users, and suppliers"

# =============================================================================
# USER SURFACES
# =============================================================================

surface user_list "Users":
  uses entity User
  mode: list
  open: User via id
  section main:
    field email "Email"
    field name "Name"
    field tenant_id "Tenant"
  ux:
    purpose: "Team roster — open a row for the person hub"

surface user_detail "User":
  uses entity User
  mode: view
  section identity "Identity":
    field name "Name"
    field email "Email"
  section tenant_link "Tenant":
    layout: strip
    field tenant_id "Tenant"
  related invoices_raised "Invoices raised":
    display: table
    show: Invoice
    columns: invoice_number, amount, status
  ux:
    purpose: "Person hub — identity and invoices they submitted"

# =============================================================================
# LINE ITEM SURFACES
# =============================================================================

surface line_item_list "Line Items":
  uses entity LineItem
  mode: list
  open: Invoice via invoice
  section main:
    field invoice "Invoice"
    field description "Description"
    field quantity "Qty"
    field unit_amount "Unit Amount"
  ux:
    purpose: "Line items — open a row for the parent Invoice hub"

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
  open: Supplier via supplier
  section main:
    field supplier "Supplier"
    field bank_account_ref "Bank Ref"
    field account_name "Account Name"
  ux:
    purpose: "Bank refs — open a row for the parent supplier hub"

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
    field email "Email"
    field name "Name"
    field tenant_id "Tenant"

surface user_edit "Edit User":
  uses entity User
  mode: edit
  section main:
    field email "Email"
    field name "Name"

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
  purpose: "Day-to-day invoice throughput — pipeline, payment health, and the queues that need a person"
  access: persona(requester, approver, finance, finance_admin, auditor, tenant_admin)

  ops_metrics:
    source: Invoice
    display: metrics
    aggregate:
      submitted: count(Invoice where status = submitted)
      approved: count(Invoice where status = approved)
      disputed: count(Invoice where status = disputed)
      paid: count(Invoice where status = paid)
    tones:
      submitted: warning
      disputed: destructive
      paid: positive
      approved: accent

  invoice_pipeline:
    source: Invoice
    display: funnel_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices yet"

  # Approver job — review queue with inline transitions when available.
  awaiting_approval:
    source: Invoice
    filter: status = submitted
    sort: amount desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "Nothing awaiting approval"

  # Finance job — settle approved invoices.
  ready_to_pay:
    source: Invoice
    filter: status = approved
    sort: amount desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "Nothing ready to pay"

  payment_health:
    source: PaymentAttempt
    display: bar_chart
    group_by: status
    aggregate:
      count: count(PaymentAttempt)
    empty: "No payment attempts"

  disputed_queue:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "No disputes open"

  # WI D: kanban family — full pipeline board (not another queue pad)
  ops_board:
    source: Invoice
    filter: status != draft
    display: kanban
    group_by: status
    sort: amount desc
    action: invoice_detail
    empty: "No invoices in the pipeline"

  # WI D: context family — recent paid settlements
  recent_paid:
    source: Invoice
    filter: status = paid
    sort: updated_at desc
    limit: 12
    display: timeline
    action: invoice_detail
    empty: "No paid invoices yet"

# ── Job workspaces (product maturity: anti-warehouse) ────────────────────────
# Separate product landings per role so density is not one mega-desk + 9 lists.
# finance_ops remains the shared ops overview for admin/oversight personas.

workspace my_invoices "My Invoices":
  purpose: "Requester desk — drafts, submissions, and line-item work on my invoices"
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

  # WI D: pipeline board (kanban family) for requester status overview
  my_status_board:
    source: Invoice
    filter: status = draft or status = submitted or status = approved or status = paid
    display: kanban
    group_by: status
    sort: updated_at desc
    action: invoice_detail
    empty: "No invoices yet"

  # WI D: grid family for supplier context (not list pad)
  suppliers_nearby:
    source: Supplier
    sort: name asc
    limit: 10
    display: grid
    action: supplier_detail
    empty: "No suppliers yet"

  # WI D: context family — recent invoice trail
  my_trail:
    source: Invoice
    sort: updated_at desc
    limit: 12
    display: timeline
    action: invoice_detail
    empty: "No invoices yet"

  # WI D: chart family — personal pipeline status mix
  my_status_mix:
    source: Invoice
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices yet"

workspace approval_desk "Approval Desk":
  purpose: "Approver job — clear the awaiting-approval queue, open the invoice hub"
  access: persona(approver, finance_admin)

  approval_load:
    source: Invoice
    display: metrics
    aggregate:
      awaiting: count(Invoice where status = submitted)
      approved: count(Invoice where status = approved)
      rejected: count(Invoice where status = rejected)
    tones:
      awaiting: warning
      approved: positive
      rejected: destructive

  awaiting_approval:
    source: Invoice
    filter: status = submitted
    sort: amount desc
    limit: 20
    display: queue
    action: invoice_detail
    empty: "Nothing awaiting approval"

  # WI D: kanban family (not listish) — pipeline view of invoice status
  approval_board:
    source: Invoice
    filter: status = submitted or status = approved or status = rejected
    display: kanban
    group_by: status
    sort: amount desc
    action: invoice_detail
    empty: "No invoices in the approval pipeline"

  # WI D: context family — recent decisions as a timeline, not another list pad
  recently_decided:
    source: Invoice
    filter: status = approved or status = rejected
    sort: updated_at desc
    limit: 12
    display: timeline
    action: invoice_detail
    empty: "No recent decisions"

  # WI D: supplier context grid (extra source + grid family)
  suppliers_nearby:
    source: Supplier
    sort: name asc
    limit: 12
    display: grid
    action: supplier_detail
    empty: "No suppliers yet"

workspace pay_desk "Pay Desk":
  purpose: "Finance job — settle approved invoices and resolve open disputes"
  access: persona(finance, finance_admin)

  settle_metrics:
    source: Invoice
    display: metrics
    aggregate:
      ready: count(Invoice where status = approved)
      disputed: count(Invoice where status = disputed)
      paid: count(Invoice where status = paid)
    tones:
      ready: accent
      disputed: destructive
      paid: positive

  ready_to_pay:
    source: Invoice
    filter: status = approved
    sort: amount desc
    limit: 20
    display: queue
    action: invoice_detail
    empty: "Nothing ready to pay"

  disputed_queue:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "No disputes open"

  # WI D: kanban family — settle pipeline by status (not another queue pad)
  settle_board:
    source: Invoice
    filter: status = approved or status = disputed or status = paid
    display: kanban
    group_by: status
    sort: updated_at desc
    action: invoice_detail
    empty: "No invoices in settle pipeline"

  payment_health:
    source: PaymentAttempt
    display: bar_chart
    group_by: status
    aggregate:
      count: count(PaymentAttempt)
    empty: "No payment attempts"

  # WI D: context family — recent dispute timeline
  dispute_trail:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 12
    display: timeline
    action: invoice_detail
    empty: "No dispute history"

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

  # WI D: grid family for payment attempt cards (not list pad)
  payment_attempts:
    source: PaymentAttempt
    display: grid
    sort: created_at desc
    limit: 20
    empty: "No payment attempts to review"

  # WI D: timeline of settled invoices (context family)
  settled_invoices:
    source: Invoice
    filter: status = paid
    sort: updated_at desc
    limit: 15
    display: timeline
    action: invoice_detail
    empty: "No paid invoices yet"

  # WI D: chart family — dispute vs paid mix
  audit_mix:
    source: Invoice
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices to chart"

  # WI D: queue family — disputed invoices needing review
  disputed_queue:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "No disputes open"

  # WI D: kanban family — paid/disputed trail board
  audit_board:
    source: Invoice
    filter: status = paid or status = disputed or status = rejected
    display: kanban
    group_by: status
    sort: updated_at desc
    action: invoice_detail
    empty: "No invoices in the audit trail"

# Sixth product workspace (WI density D): supplier / vendor desk so list shells
# no longer dominate vs job workspaces (vendors + bank refs, not bare CRUD).
workspace suppliers_desk "Suppliers":
  purpose: "Vendor desk — supplier roster, bank refs, and recent invoices"
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

  # WI D: grid family for vendor cards (not list pad)
  roster:
    source: Supplier
    display: grid
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
    limit: 15
    display: queue
    action: invoice_detail
    empty: "No invoices yet"

  # WI D: context family — invoice trail by vendor activity
  invoice_trail:
    source: Invoice
    sort: updated_at desc
    limit: 15
    display: timeline
    action: invoice_detail
    empty: "No invoice history"

  # WI D: chart family — invoice status mix next to vendor roster
  invoice_status_mix:
    source: Invoice
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices to chart"


# Seventh product workspace (WI density D): tenant admin people desk.
workspace team_desk "Team":
  purpose: "Tenant admin desk — people and tenant context"
  access: persona(tenant_admin, finance_admin, auditor)

  team_pulse:
    source: User
    display: metrics
    aggregate:
      people: count(User)
      suppliers: count(Supplier)
      tenants: count(Tenant)
    tones:
      people: accent

  # WI D: diversify mode families on team desk (grid + queue + chart)
  people:
    source: User
    display: grid
    sort: name asc
    limit: 25
    action: user_detail
    empty: "No users yet"

  suppliers:
    source: Supplier
    display: queue
    sort: name asc
    limit: 15
    action: supplier_detail
    empty: "No suppliers"

  tenant_mix:
    source: Tenant
    display: bar_chart
    group_by: name
    aggregate:
      count: count(Tenant)
    empty: "No tenants"

  # WI D: context family — people activity via invoice trail
  invoice_trail:
    source: Invoice
    sort: updated_at desc
    limit: 15
    display: timeline
    action: invoice_detail
    empty: "No invoices yet"

  # WI D: queue family — open invoices for admin context
  open_invoices:
    source: Invoice
    filter: status = submitted or status = approved
    sort: amount desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "Nothing awaiting action"

# Eighth product workspace (WI density D): payment trail desk.
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

  # WI D: timeline of settlements (context family)
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

  # WI D: kanban family — settle pipeline on the payment trail desk
  settle_board:
    source: Invoice
    filter: status = approved or status = disputed or status = paid
    display: kanban
    group_by: status
    sort: amount desc
    action: invoice_detail
    empty: "No invoices in settle pipeline"

  # WI D: chart family — payment attempt health mix
  attempt_health:
    source: PaymentAttempt
    display: bar_chart
    group_by: status
    aggregate:
      count: count(PaymentAttempt)
    empty: "No payment attempts"

# Ninth product workspace (WI density D): line-item composition desk vs bare list.
workspace line_items_desk "Line Items":
  purpose: "Line-item composition desk — what is on open invoices without warehouse CRUD"
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

  # WI D: grid family for line cards
  recent_lines:
    source: LineItem
    sort: id desc
    limit: 25
    display: grid
    empty: "No line items yet"

  # WI D: queue family — invoices that still need lines / review
  draft_invoices:
    source: Invoice
    filter: status = draft or status = submitted
    sort: updated_at desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "No draft or submitted invoices"

  # WI D: context family — recent invoice trail
  invoice_trail:
    source: Invoice
    sort: updated_at desc
    limit: 15
    display: timeline
    action: invoice_detail
    empty: "No invoices yet"

  # WI D: chart family — invoice status mix next to lines
  invoice_status_mix:
    source: Invoice
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices to chart"

# Tenth product desk (WI D): 7 lists floor dens ~0.44 with 9 full desks — need 10.
workspace disputed_ops "Disputes":
  purpose: "Dispute resolution desk — open disputes, payment attempts, and settlement trail"
  access: persona(finance, finance_admin, auditor)

  dispute_pulse:
    source: Invoice
    display: metrics
    aggregate:
      disputed: count(Invoice where status = disputed)
      approved: count(Invoice where status = approved)
      paid: count(Invoice where status = paid)
      attempts: count(PaymentAttempt)
    tones:
      disputed: destructive
      paid: positive
      approved: accent

  # WI D: queue family — disputed invoices first
  disputed_queue:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 20
    display: queue
    action: invoice_detail
    empty: "No open disputes"

  # WI D: kanban family — dispute / settle pipeline
  dispute_board:
    source: Invoice
    filter: status = disputed or status = approved or status = paid
    display: kanban
    group_by: status
    sort: amount desc
    action: invoice_detail
    empty: "No invoices in dispute pipeline"

  # WI D: context family — payment attempt trail
  attempt_trail:
    source: PaymentAttempt
    sort: created_at desc
    limit: 15
    display: timeline
    empty: "No payment attempts yet"

  # WI D: chart family — dispute vs paid mix
  status_mix:
    source: Invoice
    filter: status = disputed or status = paid or status = rejected
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices to chart"

# Eleventh product desk (WI D): 7 lists floor dens ~0.41 with 10 full desks — need 11.
workspace bank_ops "Bank Accounts":
  purpose: "Supplier bank-ref desk — payment rails without warehouse CRUD"
  access: persona(finance, finance_admin, tenant_admin)

  bank_pulse:
    source: SupplierBankAccount
    display: metrics
    aggregate:
      bank_accounts: count(SupplierBankAccount)
      suppliers: count(Supplier)
      ready_to_pay: count(Invoice where status = approved)
    tones:
      bank_accounts: accent
      ready_to_pay: positive

  # WI D: grid family for bank-ref cards
  bank_cards:
    source: SupplierBankAccount
    display: grid
    limit: 25
    empty: "No bank accounts on file"

  # WI D: queue family — approved invoices ready for rails
  ready_to_pay:
    source: Invoice
    filter: status = approved
    sort: amount desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "Nothing ready to pay"

  # WI D: context family — supplier trail
  supplier_trail:
    source: Supplier
    sort: name asc
    limit: 15
    display: timeline
    action: supplier_detail
    empty: "No suppliers yet"

  # WI D: chart family — open invoice status mix
  invoice_status_mix:
    source: Invoice
    filter: status = approved or status = paid or status = disputed
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices to chart"
