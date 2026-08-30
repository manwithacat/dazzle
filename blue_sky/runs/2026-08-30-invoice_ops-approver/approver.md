# Review submitted invoices

This is a **domain brief**, not a software-framework spec. Implement a
small, beautiful prototype that makes the jobs below feel inevitable.
Invent navigation, language, and visual system. Do **not** clone an
existing product.

**The question this prototype must answer:** How does an approver get through the work in front of them today?

## People

- **Approver** — Checker — approves or rejects submitted invoices

## Jobs (what success feels like)

- **Approver works the awaiting-approval queue**
- **Approver opens invoice record before approve or reject**

## Artifacts

Things in the world. You may group, rename, or hide them — but the
prototype must tell the truth about each lifecycle.

### Invoice
Required facts: invoice_number, supplier, amount
- **status**: draft, submitted, approved, partially_paid, rejected, disputed, paid

### Line Item
Required facts: invoice, description, unit_amount
- **po_match**: matched, partial, unmatched, not_applicable

## Procedures (human work, not screens)

**Settle Approved Invoice**

## Moments that must exist

- Approver works the awaiting-approval queue
  - Approver is at their desk
  - Invoices exist with status submitted
  - Approver sees submitted invoices in the awaiting approval queue sorted by amount
- Approver opens invoice record before approve or reject
  - Invoice.status is submitted
  - Invoice record shows status strip, supplier, amount, and related line items as a related work
  - Approver can transition to approved or rejected with reason

## Constraints (domain, not stack)

- Fake auth is fine (a button per person in the brief). In-memory seed is fine.
- Prefer one object the person works *through* over five browsers of rows.
- If a concept is missing, invent it and write it in ASSUMPTIONS.md.

## Out of this slice

- Live payments, live identity vendors, multi-product ERPs.
- Extra slices you were not given.
