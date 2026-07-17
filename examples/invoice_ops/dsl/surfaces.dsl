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
  section main:
    field name "Name"
    field region "Region"
    field status "Status"

# =============================================================================
# USER SURFACES
# =============================================================================

surface user_list "Users":
  uses entity User
  mode: list
  section main:
    field email "Email"
    field name "Name"
    field tenant_id "Tenant"

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
  section main:
    field supplier "Supplier"
    field bank_account_ref "Bank Ref"
    field account_name "Account Name"

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
