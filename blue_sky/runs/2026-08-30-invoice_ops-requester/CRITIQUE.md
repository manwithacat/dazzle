# Critique — Blue Sky invoice_ops / requester 2026-08-30

**Prototype:** Daybook (`blue_sky/runs/2026-08-30-invoice_ops-requester/`)
**Walked:** sit as Mara → raise a slip → lines + PO match → send to the books → Helios finish draft → Northline split rejected line → Calder attest receipt.
**Compared to:** invoice_ops `my_invoices` list + invoice detail + line-item related list.

Do not clone this React.

| ID | Lens | Finding | Tag |
|----|------|---------|-----|
| BS-IO-R01 | Elegance | Home is a **daybook of what needs her**, not all invoices she may list. Submitted/paid are moving or closed. invoice_ops list is permission-shaped, not “needs you”. | steal |
| BS-IO-R02 | Affordances | Raise a slip **opens the record immediately**. Dazzle create → list or detail; the job is the paper, not a success toast. | steal |
| BS-IO-R03 | Domain | **Unmatched lines block submit.** Partial may go through. invoice_ops submit is role + status; `po_match` does not gate. | steal |
| BS-IO-R04 | Domain | After finance approves, requester **attests receipt** — that is their reading of Settle. Finance Till reads settle as remittance. Both are true; the word is overloaded. | theory |
| BS-IO-R05 | Affordances | **Split a rejected line** across open POs. DSL has no split; rejection is a status with reason. | translate |
| BS-IO-R06 | Elegance | Notepad = line work on this slip. Not a second LineItem list surface. | steal |
| BS-IO-R07 | Styling | Kestrel Press, paper slip. Discard kit. | discard |

## Vs invoice_ops

| Job | Prototype | invoice_ops |
|-----|-----------|-------------|
| What needs me | Blotter: draft, rejected, disputed, approved-unsettled | `my_invoices` of everything she can list |
| Create | Raise a slip → same record | create form → saved |
| Lines | Notepad on the slip | related line-item list |

## What not to do

- Do not add NeedsYou as an entity.
- Do not make the requester pay.
