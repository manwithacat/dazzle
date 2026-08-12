module invoice_ops.entities

# =============================================================================
# TENANT — tenant root. Not tenant-scoped; row visibility is the caller's own.
# =============================================================================

entity Tenant "Tenant":
  archetype: tenant
  intent: "Tenant root — a customer company processing supplier invoices"

  display_field: name
  id: uuid pk
  name: str(120) required
  slug: str(60) unique required
  region: enum[emea,amer,apac]=emea
  status: enum[active,suspended]=active
  created_at: datetime auto_add

  # Tenant operational status (domain residual status∄transitions).
  # Only tenant_admin may suspend/reactivate the customer company root.
  transitions:
    active -> suspended: role(tenant_admin)
    suspended -> active: role(tenant_admin)

  permit:
    create: role(tenant_admin)
    read: role(requester) or role(approver) or role(finance) or role(auditor) or role(tenant_admin)
    update: role(tenant_admin)
    delete: role(tenant_admin)
    list: role(requester) or role(approver) or role(finance) or role(auditor) or role(tenant_admin)

  scope:
    create: all
      as: tenant_admin
    read: id = current_user.tenant_id
      as: requester, approver, finance, auditor, tenant_admin
    update: id = current_user.tenant_id
      as: tenant_admin
    delete: id = current_user.tenant_id
      as: tenant_admin
    list: id = current_user.tenant_id
      as: requester, approver, finance, auditor, tenant_admin

  audit: all

# =============================================================================
# USER — domain user. Carries tenant_id so `current_user.tenant_id` resolves
# (the runtime matches the authenticated email to this row — see acme_billing).
# =============================================================================

entity User "User":
  intent: "Domain user — carries tenant_id for current_user.tenant_id resolution"

  display_field: name
  id: uuid pk
  email: email required pii(category=contact)
  name: str(120) required pii(category=identity)
  tenant_id: ref Tenant required
  # Goal B org_structure (cycle 1863): department + job title so Team desk shows
  # AP / Treasury / Controllership / Audit shape — not a flat persona-only roster.
  department: str(50)
  job_title: str(80)
  # Goal B media (cycle 1885): peer AP tools (Bill.com / Tipalti / Coupa) put
  # teammate headshot thumbs on the finance ops home — not name-only theater.
  photo_url: url
  created_at: datetime auto_add

  permit:
    create: role(tenant_admin)
    # List/read open to AP roles so media_shelf + Team desk can show faces on
    # shared finance_ops (create/update/delete stay tenant_admin-only).
    read: role(requester) or role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)
    update: role(tenant_admin)
    delete: role(tenant_admin)
    list: role(requester) or role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)

  scope:
    create: tenant_id = current_user.tenant_id
      as: tenant_admin
    read: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin, auditor, tenant_admin
    update: tenant_id = current_user.tenant_id
      as: tenant_admin
    delete: tenant_id = current_user.tenant_id
      as: tenant_admin
    list: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin, auditor, tenant_admin

  audit: all

# =============================================================================
# SUPPLIER — a supplier billing a tenant. Sensitive bank details live in SupplierBankAccount.
# =============================================================================

entity Supplier "Supplier":
  intent: "A supplier that bills a tenant"

  display_field: name
  id: uuid pk
  tenant_id: ref Tenant required
  name: str(160) required
  contact_email: email required pii(category=contact)
  region: enum[emea,amer,apac]=emea
  created_at: datetime auto_add
  updated_at: datetime auto_update

  permit:
    create: role(finance) or role(tenant_admin)
    read: role(requester) or role(approver) or role(finance) or role(auditor) or role(tenant_admin)
    update: role(finance) or role(tenant_admin)
    delete: role(tenant_admin)
    list: role(requester) or role(approver) or role(finance) or role(auditor) or role(tenant_admin)

  scope:
    create: tenant_id = current_user.tenant_id
      as: finance, tenant_admin
    read: tenant_id = current_user.tenant_id
      as: requester, approver, finance, auditor, tenant_admin
    update: tenant_id = current_user.tenant_id
      as: finance, tenant_admin
    delete: tenant_id = current_user.tenant_id
      as: tenant_admin
    list: tenant_id = current_user.tenant_id
      as: requester, approver, finance, auditor, tenant_admin

  audit: all

# =============================================================================
# SUPPLIER BANK ACCOUNT — bank details extracted from Supplier for stricter RBAC.
# =============================================================================

entity SupplierBankAccount "Supplier Bank Account":
  intent: "Banking details for a supplier — isolated for stricter access control"

  id: uuid pk
  tenant_id: ref Tenant required
  supplier: ref Supplier required
  bank_account_ref: str(64) required
  account_name: str(160) required
  iban: str(34) optional
  created_at: datetime auto_add
  updated_at: datetime auto_update

  permit:
    create: role(finance) or role(tenant_admin)
    read: role(finance) or role(tenant_admin)
    update: role(finance) or role(tenant_admin)
    delete: role(tenant_admin)
    list: role(finance) or role(tenant_admin)

  scope:
    create: tenant_id = current_user.tenant_id
      as: finance, tenant_admin
    read: tenant_id = current_user.tenant_id
      as: finance, tenant_admin
    update: tenant_id = current_user.tenant_id
      as: finance, tenant_admin
    delete: tenant_id = current_user.tenant_id
      as: tenant_admin
    list: tenant_id = current_user.tenant_id
      as: finance, tenant_admin

  audit: all

# =============================================================================
# INVOICE — the lifecycle entity. State machine + event publishing live here.
# =============================================================================

entity Invoice "Invoice":
  intent: "Supplier invoice moving through an approval + payment lifecycle"
  # #1626 re-eval: queue cards need AP density — number + amount as primary line
  display_field: invoice_number

  id: uuid pk
  tenant_id: ref Tenant required
  invoice_number: str(40) required
  supplier: ref Supplier required
  amount: decimal(15,2) required
  currency: str(3)="GBP"
  po_number: str(40) optional
  # Goal B document peer-pack (cycle 1909): Bill.com / Melio / Tipalti put
  # amount + due date + vendor on open work rows — not status-only KPI theater.
  due_date: date optional
  status: enum[draft,submitted,approved,partially_paid,rejected,disputed,paid]=draft
  submitted_by: ref User optional
  rejection_reason: text optional
  dispute_reason: text optional
  created_at: datetime auto_add
  updated_at: datetime auto_update

  permit:
    create: role(requester)
    read: role(requester) or role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)
    update: role(requester) or role(approver) or role(finance) or role(finance_admin)
    delete: role(tenant_admin)
    list: role(requester) or role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)

  scope:
    create: tenant_id = current_user.tenant_id
      as: requester
    read: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin, auditor, tenant_admin
    update: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin
    delete: tenant_id = current_user.tenant_id
      as: tenant_admin
    list: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin, auditor, tenant_admin

  transitions:
    draft -> submitted: role(requester)
    submitted -> approved: role(approver)
    submitted -> rejected: role(approver) requires rejection_reason
    approved -> paid: role(finance)
    approved -> partially_paid: role(finance)
    partially_paid -> paid: role(finance)
    approved -> disputed: role(finance) requires dispute_reason
    paid -> disputed: role(finance) requires dispute_reason
    disputed -> approved: role(finance)
    disputed -> rejected: role(approver) requires rejection_reason

  publish InvoiceSubmitted when status changed
  publish InvoicePaid when status changed

  # Goal B document peer-pack (cycle 1921): Bill.com / Melio / Tipalti put
  # dispute reason prose on disputed work rows — not status-only queue meta.
  fitness:
    repr_fields: [invoice_number, supplier, amount, due_date, status, dispute_reason]

  audit: all

# =============================================================================
# LINE ITEM — a line on an invoice.
# =============================================================================

entity LineItem "Line Item":
  intent: "A single line on an invoice document — description + qty × unit amount, tax code, and PO match grain controllers scan"
  # Goal B document depth: queue title is the line description, not a UUID shell.
  # Peer Bill.com / Melio / Tipalti put tax line + PO match on composition rows
  # (cycle 1900) — not description-only spreadsheet export theater.
  display_field: description

  id: uuid pk
  tenant_id: ref Tenant required
  invoice: ref Invoice required
  description: str(200) required
  quantity: int=1
  unit_amount: decimal(15,2) required
  # Controller-true document grain (peer AP match review).
  tax_code: str(20) optional
  po_match: enum[matched, partial, unmatched, not_applicable]=not_applicable
  created_at: datetime auto_add

  permit:
    create: role(requester)
    # finance_admin: cross-cutting oversight (finance_ops composition spine) —
    # must list/read lines or hero stills show empty document theater.
    read: role(requester) or role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)
    update: role(requester)
    delete: role(requester)
    list: role(requester) or role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)

  scope:
    create: tenant_id = current_user.tenant_id
      as: requester
    read: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin, auditor, tenant_admin
    update: tenant_id = current_user.tenant_id
      as: requester
    delete: tenant_id = current_user.tenant_id
      as: requester
    list: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin, auditor, tenant_admin

  audit: all

# =============================================================================
# INVOICE NOTE — Goal B conversation on the AP trail (approver ↔ finance).
# =============================================================================

entity InvoiceNote "Invoice Note":
  # Goal B conversation: peer AP tools (Bill.com / Tipalti / Coupa) show
  # approval discussion copy on work desks — not status queues alone.
  # author is a display string (ops_dashboard IncidentNote pattern) so seed
  # bootstrap does not require composite User FK before persona mirror.
  intent: "Operator discussion on an Invoice — the conversation that drives approve, dispute, and pay"
  domain: accounts_payable
  patterns: messaging, audit_trail
  display_field: body
  id: uuid pk
  tenant_id: ref Tenant required
  invoice: ref Invoice required
  author: str(120) required
  body: text required
  created_at: datetime auto_add

  permit:
    create: role(requester) or role(approver) or role(finance) or role(finance_admin)
    read: role(requester) or role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)
    update: role(approver) or role(finance) or role(finance_admin)
    delete: role(tenant_admin)
    list: role(requester) or role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)

  scope:
    create: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin
    read: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin, auditor, tenant_admin
    update: tenant_id = current_user.tenant_id
      as: approver, finance, finance_admin
    delete: tenant_id = current_user.tenant_id
      as: tenant_admin
    list: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin, auditor, tenant_admin

  fitness:
    repr_fields: [invoice, author, body]

  audit: all

# =============================================================================
# INVOICE DOCUMENT — named AP packet on an Invoice (Goal B document depth)
# =============================================================================
# Peer Bill.com / Tipalti / Coupa put remittance advice, credit memos, PO
# packets, tax certificates, and goods receipts on the AP home above the
# discussion trail — not line composition alone as the only "document" surface.

entity InvoiceDocument "Invoice Document":
  intent: "A named AP document on an Invoice — remittance advice, credit memo, PO packet, tax certificate, payment confirmation, or goods receipt buyers scan above the discussion trail"
  domain: accounts_payable
  patterns: documentation, audit_trail
  display_field: headline
  id: uuid pk
  tenant_id: ref Tenant required
  invoice: ref Invoice required
  headline: str(200) required
  doc_kind: enum[remittance, credit_memo, po_packet, tax_certificate, payment_confirmation, goods_receipt]=remittance
  body: text
  status: enum[draft, published, archived]=draft
  author: str(120)
  # Goal B document peer-pack (cycle 1892): packet cover preview — remittance /
  # PO / tax certificate thumbs on finance_ops (Bill.com / Melio / Tipalti put
  # packet visuals on the money desk, not teammate headshot shelves).
  preview_url: url
  created_at: datetime auto_add

  # Domain residual status∄transitions: AP packets publish then archive.
  transitions:
    draft -> published: role(approver) or role(finance) or role(finance_admin)
    published -> archived: role(approver) or role(finance) or role(finance_admin)
    draft -> archived: role(approver) or role(finance) or role(finance_admin)
    published -> draft: role(approver) or role(finance) or role(finance_admin)

  permit:
    create: role(requester) or role(approver) or role(finance) or role(finance_admin)
    read: role(requester) or role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)
    update: role(approver) or role(finance) or role(finance_admin)
    delete: role(tenant_admin)
    list: role(requester) or role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)

  scope:
    create: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin
    read: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin, auditor, tenant_admin
    update: tenant_id = current_user.tenant_id
      as: approver, finance, finance_admin
    delete: tenant_id = current_user.tenant_id
      as: tenant_admin
    list: tenant_id = current_user.tenant_id
      as: requester, approver, finance, finance_admin, auditor, tenant_admin

  fitness:
    repr_fields: [invoice, headline, doc_kind, status, author, preview_url]

  audit: all

# =============================================================================
# PAYMENT ATTEMPT — one attempt to settle an approved invoice.
# =============================================================================

entity PaymentAttempt "Payment Attempt":
  intent: "One attempt to settle an approved invoice via the payment provider"

  id: uuid pk
  tenant_id: ref Tenant required
  invoice: ref Invoice required
  attempt_number: int=1
  status: enum[pending,succeeded,failed]=pending
  provider_reference: str(80) optional
  failure_reason: text optional
  created_at: datetime auto_add

  # Settlement attempt SM (domain residual status∄transitions).
  # Provider outcomes are terminal; finance may re-open failed for retry.
  transitions:
    pending -> succeeded: role(finance) or role(finance_admin)
    pending -> failed: role(finance) or role(finance_admin)
    failed -> pending: role(finance) or role(finance_admin)

  permit:
    create: role(finance) or role(finance_admin)
    read: role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)
    update: role(finance) or role(finance_admin)
    delete: role(tenant_admin)
    list: role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)

  scope:
    create: tenant_id = current_user.tenant_id
      as: finance, finance_admin
    read: tenant_id = current_user.tenant_id
      as: approver, finance, finance_admin, auditor, tenant_admin
    update: tenant_id = current_user.tenant_id
      as: finance, finance_admin
    delete: tenant_id = current_user.tenant_id
      as: tenant_admin
    list: tenant_id = current_user.tenant_id
      as: approver, finance, finance_admin, auditor, tenant_admin

  audit: all
