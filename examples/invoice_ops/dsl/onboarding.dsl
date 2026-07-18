module invoice_ops.guides

use invoice_ops.core

# Per-persona onboarding for Invoice Ops, following the invoice
# lifecycle: requester raises -> approver decides -> finance settles
# -> auditor reviews. Job desks (my_invoices, approval_desk, pay_desk,
# audit_review) are default workspaces; guides still root on *surfaces*
# (guide targets cannot be workspaces). Concordance is enforced at
# `dazzle validate`.

# ─── Requester (maker) journey ────────────────────────────────────

guide requester_onboarding "Raise an invoice":
  audience: persona = requester

  step new_invoice:
    kind: empty_state
    target: surface.invoice_list
    title: "Raise your first invoice"
    body: "Create an invoice, pick the supplier, and add the amount and PO number before you submit it."
    cta_label: "New Invoice"
    cta_target: surface.invoice_create
    complete_on: event entity.Invoice.created

  step add_lines:
    kind: inline_card
    target: surface.invoice_detail
    title: "Break it into line items"
    body: "Add a line for each charge so approvers can see exactly what they're signing off on."
    complete_on: dismiss

  step submit_it:
    kind: banner
    target: surface.invoice_list
    title: "Submit for approval"
    body: "Once the invoice looks right, submit it — an approver picks it up from here."
    complete_on: dismiss

  step_order: [new_invoice, add_lines, submit_it]

  on_complete:
    redirect: surface.invoice_list

# ─── Approver (checker) journey ───────────────────────────────────

guide approver_onboarding "Approve invoices":
  audience: persona = approver

  step waiting_on_you:
    kind: spotlight
    target: surface.invoice_list
    title: "Invoices waiting on you"
    body: "Your Approval Desk opens with the awaiting-approval queue. From here, open a submitted invoice to review the detail and decide."
    placement: center
    complete_on: dismiss

  step decide:
    kind: popover
    target: surface.invoice_edit
    title: "Approve or send it back"
    body: "Approve invoices that check out, or reject with a reason so the requester can fix and resubmit."
    placement: bottom
    complete_on: dismiss

  step_order: [waiting_on_you, decide]

  on_complete:
    redirect: surface.invoice_list

# ─── Finance (operator) journey ───────────────────────────────────

guide finance_onboarding "Settle approved invoices":
  audience: persona = finance

  step ready_to_pay:
    kind: spotlight
    target: surface.invoice_list
    title: "Approved and ready to pay"
    body: "Your Pay Desk lists approved invoices ready to settle. Open one to record payment or flag a dispute."
    placement: center
    complete_on: dismiss

  step record_payment:
    kind: popover
    target: surface.invoice_edit
    title: "Record the payment"
    body: "Mark an invoice paid once funds are sent, or flag a dispute if something doesn't add up."
    placement: bottom
    complete_on: dismiss

  step keep_suppliers:
    kind: inline_card
    target: surface.supplier_list
    title: "Keep supplier details current"
    body: "Bank details and contacts live with each supplier — keep them accurate so payments land first time."
    complete_on: dismiss

  step_order: [ready_to_pay, record_payment, keep_suppliers]

  on_complete:
    redirect: surface.invoice_list

# ─── Auditor journey ──────────────────────────────────────────────

guide auditor_onboarding "Review the audit trail":
  audience: persona = auditor

  step trail:
    kind: spotlight
    target: surface.invoice_list
    title: "Every invoice, with its trail"
    body: "Audit Review opens with payment attempts and settled invoices. Each invoice carries its full status history — your starting point for any review."
    placement: center
    complete_on: dismiss

  step drill_in:
    kind: inline_card
    target: surface.invoice_detail
    title: "Drill into any invoice"
    body: "Open an invoice to see who approved it, when, and any rejection or dispute reasons on the record."
    complete_on: dismiss

  step_order: [trail, drill_in]

  on_complete:
    redirect: surface.invoice_list
