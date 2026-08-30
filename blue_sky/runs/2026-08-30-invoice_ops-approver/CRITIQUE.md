# Critique — Blue Sky invoice_ops / approver 2026-08-30

**Prototype:** On the Desk (`blue_sky/runs/2026-08-30-invoice_ops-approver/`)
**Walked:** sit down → stack (largest first) → pick up Helios (unmatched) → reject with PO reason → next sheet in hand → Northglass approve → Kite partial refused without exception note → quiet desk.
**Compared to:** `examples/invoice_ops` as Dazzle actually generates it — `approval_desk` list of submitted invoices, invoice detail with related line items, role-guarded approve/reject.

Do not clone this React. Tag is the unit of work.

| ID | Lens | Finding | Tag |
|----|------|---------|-----|
| BS-IO-01 | Elegance | The object is **today’s stack**, not a warehouse of Invoice rows. After a stamp the next sheet is already in hand. invoice_ops returns you to the list. | steal |
| BS-IO-02 | Affordances | **No stamp on the stack.** You must pick up the record. Dazzle list actions can fire transitions from the row. | steal |
| BS-IO-03 | Affordances | Approve of unmatched/partial PO **requires an exception sentence**. invoice_ops can approve on role alone; `po_match` is visible but not a spoken gate. | steal |
| BS-IO-04 | Domain | **Released for settlement** is a handoff, not a payment screen. The brief’s “Settle Approved Invoice” procedure is someone else’s job. invoice_ops keeps finance on a second desk; the copy does not say that out loud on approve. | steal |
| BS-IO-05 | Elegance | Empty is **quiet**, not an empty table with column headers. | steal |
| BS-IO-06 | Framework | Dazzle has no primitive for “work queue as a stack with next-after-decision”. Workspaces are still filtered lists. `stems/story-driven-jobs` already prefers jobs over CRUD; the prototype goes further — the job *is* the sheet in hand. | translate |
| BS-IO-07 | Framework | “Must inspect before transition” is a process, but the generated UI does not enforce it. A list-row action is the default attractor. | translate |
| BS-IO-08 | Domain | `not_applicable` PO match (standing retainer) is a different sentence from unmatched. DSL has the enum; the desk treats it as a kind, not a miss. | theory |
| BS-IO-09 | Styling | Paper, grain, “sit down / stand up”. Do not port the CSS kit. | discard |
| BS-IO-10 | Domain | Named Mara Chen, four invented suppliers, afternoon desk. Disposable. | discard |

## Vs invoice_ops (same jobs)

| Job | Prototype | invoice_ops (Dazzle) |
|-----|-----------|----------------------|
| What is waiting | One stack, largest amount on top, exposure tally | `approval_desk` list region of submitted invoices |
| Inspect | Pick up sheet; status strip + lines + PO match | Open invoice detail; related line items as a list |
| Decide | Stamp on the record; next sheet arrives | Approve/reject control; back to the list |
| Done | Quiet desk + today’s stamps | Empty list / remaining rows |

## What not to do

- Do not add a `Stack` entity to pass density.
- Do not rebuild On the Desk CSS in an example `custom.css`.
- Do not file a framework issue that is only “make lists prettier”.
