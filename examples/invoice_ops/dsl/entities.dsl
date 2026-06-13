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
  email: email required
  name: str(120) required
  tenant_id: ref Tenant required
  created_at: datetime auto_add

  permit:
    create: role(tenant_admin)
    read: role(auditor) or role(tenant_admin)
    update: role(tenant_admin)
    delete: role(tenant_admin)
    list: role(auditor) or role(tenant_admin)

  scope:
    create: tenant_id = current_user.tenant_id
      as: tenant_admin
    read: tenant_id = current_user.tenant_id
      as: auditor, tenant_admin
    update: tenant_id = current_user.tenant_id
      as: tenant_admin
    delete: tenant_id = current_user.tenant_id
      as: tenant_admin
    list: tenant_id = current_user.tenant_id
      as: auditor, tenant_admin

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
  contact_email: email required
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

  id: uuid pk
  tenant_id: ref Tenant required
  invoice_number: str(40) required
  supplier: ref Supplier required
  amount: decimal(15,2) required
  currency: str(3)="GBP"
  po_number: str(40) optional
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

  audit: all

# =============================================================================
# LINE ITEM — a line on an invoice.
# =============================================================================

entity LineItem "Line Item":
  intent: "A single line on an invoice"

  id: uuid pk
  tenant_id: ref Tenant required
  invoice: ref Invoice required
  description: str(200) required
  quantity: int=1
  unit_amount: decimal(15,2) required
  created_at: datetime auto_add

  permit:
    create: role(requester)
    read: role(requester) or role(approver) or role(finance) or role(auditor) or role(tenant_admin)
    update: role(requester)
    delete: role(requester)
    list: role(requester) or role(approver) or role(finance) or role(auditor) or role(tenant_admin)

  scope:
    create: tenant_id = current_user.tenant_id
      as: requester
    read: tenant_id = current_user.tenant_id
      as: requester, approver, finance, auditor, tenant_admin
    update: tenant_id = current_user.tenant_id
      as: requester
    delete: tenant_id = current_user.tenant_id
      as: requester
    list: tenant_id = current_user.tenant_id
      as: requester, approver, finance, auditor, tenant_admin

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
