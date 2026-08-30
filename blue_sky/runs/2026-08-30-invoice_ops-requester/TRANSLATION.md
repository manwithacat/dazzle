# Translation — invoice_ops / requester 2026-08-30

| ID | Keep as question | What invoice_ops does instead | Portability | Non-goal |
|----|------------------|-------------------------------|-------------|----------|
| BS-IO-R01 | What if home was only work that still needs the maker? | List of invoices she may see. | steal the idea (workspace filter / copy) | Do not hide submitted-in-flight from the maker |
| BS-IO-R02 | Create lands on the object, not a toast? | Typical create → list. | steal the idea | Do not change every example create |
| BS-IO-R03 | Can unmatched block submit? | Status transition, no PO gate. | steal the idea (guard + message) | Same class as approver exception note |
| BS-IO-R04 | Who settles — attest receipt or remit? | Finance pays; requester is out after submit. | theory | Do not give requester a pay button |
| BS-IO-R05 | Can a rejected line split across POs? | One line, one PO match enum. | translate — needs a line-split story in DSL, maybe a framework pattern for “split this row” | Do not add SplitLine widget from taste |
| BS-IO-R06 | Are lines a notepad on the invoice? | Related list surface. | steal the idea | Do not delete line_items_desk |

**Failed firewall?** No.

**Sharpest:** The maker’s pile is **unfinished slips**, and submit is blocked by unmatched lines — not by missing list permission.
