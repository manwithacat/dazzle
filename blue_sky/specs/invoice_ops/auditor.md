# Review the invoice trail

This is a **domain brief**, not a software-framework spec. Implement a
small, beautiful prototype that makes the jobs below feel inevitable.
Invent navigation, language, and visual system. Do **not** clone an
existing product.

**The question this prototype must answer:** How does an auditor get through the work in front of them today?

## People

- **Auditor** — Read-only reviewer with audit-export access

## Jobs (what success feels like)

- **Auditor traces payment attempts back to the invoice record**

## Artifacts

Things in the world. You may group, rename, or hide them — but the
prototype must tell the truth about each lifecycle.

### Payment Attempt
Required facts: invoice
- **status**: pending, succeeded, failed

### Invoice
Required facts: invoice_number, supplier, amount
- **status**: draft, submitted, approved, partially_paid, rejected, disputed, paid

## Procedures (human work, not screens)

**Settle Approved Invoice**

## Moments that must exist

- Auditor traces payment attempts back to the invoice record
  - Auditor is on the audit review desk
  - Auditor has list permission on PaymentAttempt
  - Payment attempt rows triple-open PaymentAttempt via id | Invoice via invoice | Tenant via tenant id (attempt record first, invoice then tenant)

## Constraints (domain, not stack)

- Fake auth is fine (a button per person in the brief). In-memory seed is fine.
- Prefer one object the person works *through* over five browsers of rows.
- If a concept is missing, invent it and write it in ASSUMPTIONS.md.

## Out of this slice

- Live payments, live identity vendors, multi-product ERPs.
- Extra slices you were not given.
