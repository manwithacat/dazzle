module invoice_ops.personas

persona requester "Requester":
  description: "Maker — creates and submits supplier invoices"
  goals: "Raise invoices", "Submit for approval"
  proficiency: intermediate
  default_workspace: my_invoices

persona approver "Approver":
  description: "Checker — approves or rejects submitted invoices"
  goals: "Review submitted invoices", "Approve or reject"
  proficiency: expert
  default_workspace: approval_desk

persona finance "Finance Operator":
  description: "Records payment, handles disputes"
  goals: "Settle approved invoices", "Resolve disputes"
  proficiency: expert
  default_workspace: pay_desk

persona auditor "Auditor":
  description: "Read-only reviewer with audit-export access"
  goals: "Review the invoice trail", "Export audit evidence"
  proficiency: intermediate
  default_workspace: audit_review

persona tenant_admin "Tenant Administrator":
  description: "Manages users, suppliers and per-tenant config within one tenant"
  goals: "Manage tenant users and suppliers", "Set approval thresholds"
  proficiency: expert
  default_workspace: finance_ops

persona finance_admin "Finance Administrator":
  description: "Cross-cutting finance oversight — an override role above finance"
  goals: "Override blocked payments", "Audit financial records"
  proficiency: expert
  default_workspace: finance_ops
