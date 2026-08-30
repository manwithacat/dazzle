# Settle approved invoices

This is a **domain brief**, not a software-framework spec. Implement a
small, beautiful prototype that makes the jobs below feel inevitable.
Invent navigation, language, and visual system. Do **not** clone an
existing product.

**The question this prototype must answer:** How does a finance operator get through the work in front of them today?

## People

- **Finance Operator** — Records payment, handles disputes

## Jobs (what success feels like)

- **Finance settles invoices from the ready-to-pay queue**
- **Finance works the open dispute queue**

## Artifacts

Things in the world. You may group, rename, or hide them — but the
prototype must tell the truth about each lifecycle.

### Invoice
Required facts: invoice_number, supplier, amount
- **status**: draft, submitted, approved, partially_paid, rejected, disputed, paid

### Payment Attempt
Required facts: invoice
- **status**: pending, succeeded, failed

## Procedures (human work, not screens)

**Settle Approved Invoice**

## Moments that must exist

- Finance settles invoices from the ready-to-pay queue
  - Finance Operator is at their desk
  - Invoices exist with status approved
  - Finance sees approved invoices in the ready to pay queue
- Finance works the open dispute queue
  - Finance Operator is at their desk
  - Invoices exist with status disputed
  - Disputed queue surfaces invoices needing resolution

## Constraints (domain, not stack)

- Fake auth is fine (a button per person in the brief). In-memory seed is fine.
- Prefer one object the person works *through* over five browsers of rows.
- If a concept is missing, invent it and write it in ASSUMPTIONS.md.

## Out of this slice

- Live payments, live identity vendors, multi-product ERPs.
- Extra slices you were not given.
