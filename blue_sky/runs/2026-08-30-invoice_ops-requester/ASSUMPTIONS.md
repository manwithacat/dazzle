# Assumptions

Facts the brief did not state, invented so a requester can finish today's work.

## The press

- The organization is **Kestrel Press**, a small publisher in Portland.
- The requester is **Mara Ellison**, production coordinator. She is the only person in this slice. She has list permission on her own invoices and may open any of them as a record.
- "The books" is what Mara calls finance / accounts payable. She does not approve invoices herself.

## The desk, not a catalog

- Mara's home is a **daybook blotter**: work in front of her today, not an all-time invoice browser.
- A slip **needs her** when it is a draft, rejected, disputed, or approved but not yet settled.
- Submitted, approved-and-settled, and partially paid slips are **already moving**. Paid slips are **closed**.
- Raising a slip creates a draft invoice and opens its record immediately.

## Invoice

- `invoice_number` is the **supplier's** number (what is printed on their bill).
- `supplier` is chosen from known Kestrel vendors, or typed in as someone new.
- `amount` is always the sum of line extensions (quantity × unit amount). Mara does not type a header total.
- Status follows the brief: `draft`, `submitted`, `approved`, `partially_paid`, `rejected`, `disputed`, `paid`.
- Mara may edit lines only in `draft`, `rejected`, or `disputed`.
- Sending to the books moves a draft or rejected slip to `submitted`. There is no live approver in this prototype; other statuses are seeded so she can review the record in each lifecycle.

## Line items and purchase orders

- Each line has description, quantity, unit amount, and a `po_match` of `matched`, `partial`, `unmatched`, or `not_applicable`.
- **Unmatched** lines block submit. Mara must link an open purchase order or mark the line as having none (rush fees, one-offs, some licenses).
- **Partial** matches are allowed through. The books will see the gap.
- **Matched** means quantity and unit sit inside an open unit-priced PO, or the line draws down a budget/retainer PO without overrunning it.
- Open POs are local to the supplier. They do not decrement in this prototype (no inventory engine).
- "Split across open orders" is a requester shortcut: when a line overruns the remaining quantity on its PO, leftover quantity is placed on the next same-rate PO for that supplier.

## Settle approved invoice

- After finance stamps **approved**, Mara still has work: she **attests receipt**. That is this slice's reading of *Settle Approved Invoice*.
- Settlement does not invent a new status. The slip stays `approved`, gains `settledAt` / `settledBy`, and leaves the "needs you" pile. Treasury can pay from there.
- `partially_paid` and `paid` are later treasury states. Mara can open those records; she cannot key a payment.
- She must check every line received before the attestation will take.

## Disputes and rejections

- A **rejected** slip comes back with a reason from the books. Mara fixes lines (or splits them) and sends it again.
- A **disputed** slip is an argument about rate or quantity. Mara may **stand by** the slip (resubmit with a note) or **withdraw** it to draft.

## What is fake

- Auth is a button.
- All records live in memory and reset on reload.
- No live payments, identity vendors, or ERP.
