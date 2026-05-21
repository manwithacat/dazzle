module invoice_ops.personas

persona requester "Requester":
  description: "Maker — creates and submits supplier invoices"
  goals: "Raise invoices", "Submit for approval"
  proficiency: intermediate

persona approver "Approver":
  description: "Checker — approves or rejects submitted invoices"
  goals: "Review submitted invoices", "Approve or reject"
  proficiency: expert

persona finance "Finance Operator":
  description: "Records payment, handles disputes"
  goals: "Settle approved invoices", "Resolve disputes"
  proficiency: expert

persona auditor "Auditor":
  description: "Read-only reviewer with audit-export access"
  goals: "Review the invoice trail", "Export audit evidence"
  proficiency: intermediate

persona tenant_admin "Tenant Administrator":
  description: "Manages users, suppliers and per-tenant config within one tenant"
  goals: "Manage tenant users and suppliers", "Set approval thresholds"
  proficiency: expert
