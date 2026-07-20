module invoice_ops.personas

persona requester "Requester":
  description: "Maker — creates and submits supplier invoices"
  goals: "Raise invoices", "Submit for approval"
  proficiency: intermediate
  default_workspace: my_invoices
  # WI N: job desks first — not auto entity-list soup
  uses nav requester_nav

persona approver "Approver":
  description: "Checker — approves or rejects submitted invoices"
  goals: "Review submitted invoices", "Approve or reject"
  proficiency: expert
  default_workspace: approval_desk
  uses nav approver_nav

persona finance "Finance Operator":
  description: "Records payment, handles disputes"
  goals: "Settle approved invoices", "Resolve disputes"
  proficiency: expert
  default_workspace: pay_desk
  uses nav finance_nav

persona auditor "Auditor":
  description: "Read-only reviewer with audit-export access"
  goals: "Review the invoice trail", "Export audit evidence"
  proficiency: intermediate
  default_workspace: audit_review
  uses nav auditor_nav

persona tenant_admin "Tenant Administrator":
  description: "Manages users, suppliers and per-tenant config within one tenant"
  goals: "Manage tenant users and suppliers", "Set approval thresholds"
  proficiency: expert
  default_workspace: finance_ops
  uses nav tenant_admin_nav

persona finance_admin "Finance Administrator":
  description: "Cross-cutting finance oversight — an override role above finance"
  goals: "Override blocked payments", "Audit financial records"
  proficiency: expert
  default_workspace: finance_ops
  uses nav finance_admin_nav

# Curated sidebars: workspace destinations only (WI N).
# Names must match workspace ids (not labels) — validate warns on orphans.
nav requester_nav:
  group "My work":
    my_invoices
    finance_ops
    line_items_desk
    draft_ops
    rejected_ops
    submitted_ops

nav approver_nav:
  group "Approvals":
    approval_desk
    finance_ops
    suppliers_desk
    draft_ops
    rejected_ops
    submitted_ops

nav finance_nav:
  group "Settle":
    pay_desk
    payments_trail
    disputed_ops
    bank_ops
    settlement_ops
    suppliers_desk
    finance_ops
    line_items_desk
    draft_ops
    rejected_ops
    partial_ops
    paid_ops
    approved_ops
    submitted_ops
    succeeded_ops

nav auditor_nav:
  group "Audit":
    audit_review
    finance_ops
    team_desk
    payments_trail
    disputed_ops
    settlement_ops
    line_items_desk
    rejected_ops
    partial_ops
    paid_ops
    approved_ops
    submitted_ops
    succeeded_ops

nav tenant_admin_nav:
  group "Admin":
    finance_ops
    team_desk
    suppliers_desk
    bank_ops
    settlement_ops
    audit_review
    draft_ops
    rejected_ops
    partial_ops
    paid_ops
    approved_ops
    submitted_ops
    succeeded_ops

nav finance_admin_nav:
  group "Oversight":
    finance_ops
    pay_desk
    approval_desk
    audit_review
    payments_trail
    disputed_ops
    bank_ops
    settlement_ops
    suppliers_desk
    team_desk
    line_items_desk
    draft_ops
    rejected_ops
    partial_ops
    paid_ops
    approved_ops
    submitted_ops
    succeeded_ops
