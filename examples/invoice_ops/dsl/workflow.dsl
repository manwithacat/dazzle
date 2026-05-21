module invoice_ops.workflow

use invoice_ops.entities

# Standard maker-checker: one approver clears an invoice at or below the
# tenant's configured threshold.
approval StandardApproval "Standard Invoice Approval":
  entity: Invoice
  trigger: status -> approved
  approver_role: approver
  quorum: 1
  threshold: amount <= approval_threshold
  outcomes:
    approved -> approved
    rejected -> rejected

# High-value gate: invoices above the tenant threshold need a second approver.
approval HighValueApproval "High-Value Invoice Approval":
  entity: Invoice
  trigger: status -> approved
  approver_role: approver
  quorum: 2
  threshold: amount > approval_threshold
  outcomes:
    approved -> approved
    rejected -> rejected
