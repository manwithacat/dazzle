module invoice_ops.stories

# Journey-bound stories — finance_ops queues + invoice hub, not warehouse CRUD.

story ST-001 "Approver works the awaiting-approval queue":
  status: accepted
  executed_by: surface.invoice_list
  persona: approver
  trigger: user_click
  entities: [Invoice]
  given:
    - "Approver is on the approval_desk workspace"
    - "Invoices exist with status submitted"
  then:
    - "Approver sees submitted invoices in the awaiting_approval queue sorted by amount"
    - "Row open hops to the Invoice detail hub"
    - "Approval load metrics show awaiting / approved / rejected counts"

story ST-002 "Approver opens invoice hub before approve or reject":
  status: accepted
  executed_by: surface.invoice_detail
  persona: approver
  trigger: user_click
  entities: [Invoice, LineItem]
  given:
    - "Invoice.status is submitted"
  then:
    - "Invoice hub shows status strip, supplier, amount, and related line items"
    - "Approver can transition to approved or rejected with reason"

story ST-003 "Finance settles invoices from the ready-to-pay queue":
  status: accepted
  executed_by: surface.invoice_list
  persona: finance
  trigger: user_click
  entities: [Invoice, PaymentAttempt]
  given:
    - "Finance Operator is on the pay_desk workspace"
    - "Invoices exist with status approved"
  then:
    - "Finance sees approved invoices in the ready_to_pay queue"
    - "Opening a row lands on the Invoice hub with payment attempts related"

story ST-004 "Finance works the open dispute queue":
  status: accepted
  executed_by: surface.invoice_detail
  persona: finance
  trigger: user_click
  entities: [Invoice]
  given:
    - "Finance Operator is on the pay_desk workspace"
    - "Invoices exist with status disputed"
  then:
    - "Disputed queue surfaces invoices needing resolution"
    - "Invoice hub shows dispute_reason and payment trail"

story ST-005 "Requester reviews own invoices and line items via hub":
  status: accepted
  executed_by: surface.invoice_detail
  persona: requester
  trigger: user_click
  entities: [Invoice, LineItem]
  given:
    - "Requester is on the my_invoices workspace"
    - "Requester has list permission on Invoice"
  then:
    - "Requester opens Invoice hub with related line items"
    - "Requester can add line items and submit draft invoices"

story ST-006 "Auditor traces payment attempts back to the invoice hub":
  status: accepted
  executed_by: surface.payment_attempt_list
  persona: auditor
  trigger: user_click
  entities: [PaymentAttempt, Invoice]
  given:
    - "Auditor is on the audit_review workspace"
    - "Auditor has list permission on PaymentAttempt"
  then:
    - "Payment attempt rows open the parent Invoice hub (not an orphan warehouse row)"
    - "Auditor cannot modify invoices or payments"
