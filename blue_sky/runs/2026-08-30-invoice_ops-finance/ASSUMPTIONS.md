# Assumptions

Facts the brief did not state. Invented so the sitting would be true.

## The house

- The operator works for **Harrow & Co.**, a millwork shop on Black River. The product is **Till**: the desk where money leaves the house.
- The only person in this slice is **Mara Chen, Finance Operator**. Intake, purchasing, and the shop floor live elsewhere.
- The sitting is **30 August 2026**, afternoon. Time does not advance; stamps use 14:22.

## What belongs on the desk

- Finance does not see **draft** or **submitted** invoices. Those sit with accounts payable until someone approves them.
- **Ready to remit** is approved invoices with a remainder, including **partially_paid**.
- **Open disputes** is status `disputed`.
- **Stamped this sitting** is `paid` or `rejected`. It is a memory of the sitting, not a ledger of the year.
- Rejected means **stood down** — Harrow will not pay. It is not a supplier rejection of a draft.

## Invoice truth

- Amounts are stored in cents. The original amount never changes. Remainder = original − succeeded remittances − credits.
- **Helion Glass INV-8841** $18,440.00 is due today. First paper on the blotter.
- **Northwind Timber INV-8902** $4,217.50, due 4 Sep.
- **Calder Freight INV-8910** $2,080.00, due 12 Sep.
- **Vale Packaging INV-8766** $11,900.00 original, $4,000 remitted 22 Aug by ACH, remainder $7,900, overdue. Status `partially_paid` on seed.
- **Meridian Steel INV-8712** $42,600.00, disputed 22 Aug by Elena Voss on the shop floor: heat-treat premium $6,400 billed against as-rolled mill certs.
- **Osprey Inks INV-8690** $1,155.00, disputed 16 Aug by Mara herself as a duplicate of INV-8520 (already paid 12 Aug, not on this desk).
- **Bramble Hardware INV-8820** $640.00, paid this morning. Seeded so the cleared tray is not a lie at first sit.

## Payment attempts

- Till does not talk to a bank. Mara records what happened on the rail.
- Rails on file: ACH, wire, check. Default follows the supplier’s bank-on-file line.
- A remittance creates a **pending** attempt, then **succeeded** or **failed**. Failed reasons are canned from the rail (account not found, beneficiary mismatch, check stopped).
- A failed attempt does not change invoice status. The paper stays ready. Retry is the same pad.
- A succeeded attempt that leaves a remainder moves status to `partially_paid`. A remainder of zero moves to `paid`.
- You cannot remit more than the remainder, or zero.

## Disputes

- A dispute is a pinned claim on the paper: who opened it, when, how much is in contention, and the sentence that stopped payment.
- Three honest endings:
  1. **Unfounded** — claim dropped, dispute cleared, status returns to `approved` (or `partially_paid` if money already went out), invoice goes to the ready tray so it can be remitted.
  2. **Credit accepted** — a credit memo, not a payment attempt. Remainder falls. If anything is still due, status is `approved` or `partially_paid` and the invoice returns to ready. If the credit closes it, status is `paid`.
  3. **Stood down** — status `rejected`. Will not pay. Paper moves to stamped.
- Leaving a dispute open is just leaving the paper. No extra status.

## Lifecycle the prototype must not lie about

```
draft → submitted → approved → paid
                      ↓     ↘ partially_paid → paid
                   disputed → approved (unfounded / credit)
                            → rejected (stood down)
                            → paid (credit covers all)
```

Draft and submitted exist in the company and not on this desk.

## What is out

- No live rails, no identity vendors, no ERP, no multi-entity, no approvals (already happened), no supplier login, no attachments beyond the claim text.
