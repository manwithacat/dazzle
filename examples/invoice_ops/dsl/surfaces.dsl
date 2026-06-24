module invoice_ops.surfaces

use invoice_ops.entities

# =============================================================================
# INVOICE SURFACES
# =============================================================================

surface invoice_list "Invoices":
  uses entity Invoice
  mode: list
  section main:
    field invoice_number "Number"
    field amount "Amount" format: currency:GBP
    field currency "Currency"
    field status "Status"

surface invoice_detail "Invoice":
  uses entity Invoice
  mode: view
  section main:
    field invoice_number "Number"
    field supplier "Supplier"
    field amount "Amount"
    field status "Status"
    field rejection_reason "Rejection Reason"
    field dispute_reason "Dispute Reason"

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
  section main:
    field name "Name"
    field contact_email "Contact"
    field region "Region"

# =============================================================================
# PAYMENT ATTEMPT SURFACES
# =============================================================================

surface payment_attempt_list "Payment Attempts":
  uses entity PaymentAttempt
  mode: list
  section main:
    field invoice "Invoice"
    field attempt_number "Attempt"
    field status "Status"
    field failure_reason "Failure Reason"

# =============================================================================
# AUDIT EXPORT SURFACE
# =============================================================================

surface audit_export "Audit Export":
  uses entity Invoice
  mode: list
  section main:
    field invoice_number "Number"
    field status "Status"
    field updated_at "Last Change"

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
  section main:
    field invoice "Invoice"
    field description "Description"
    field quantity "Qty"
    field unit_amount "Unit Amount"

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
