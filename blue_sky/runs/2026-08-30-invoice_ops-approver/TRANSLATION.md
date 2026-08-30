# Translation — invoice_ops / approver 2026-08-30

Dazzle-aware. Enquiries, not tickets. Read `examples/invoice_ops/stems/` first.

| ID | Keep as question | What invoice_ops does instead | Portability | Non-goal |
|----|------------------|-------------------------------|-------------|----------|
| BS-IO-01 | What if the next decision was already in hand? | After approve/reject the user is back on the filtered list. | steal the idea (example UX / process next-step) | Do not clone auto-advance of a React stack |
| BS-IO-02 | What if the list could not stamp? | List/detail can expose the same transition. | steal the idea | Do not remove list actions globally |
| BS-IO-03 | What if unmatched/partial could not approve without a sentence? | `po_match` is a field; the transition is role-guarded only. | steal the idea (DSL guard + message) | Do not invent a new widget named ExceptionNote |
| BS-IO-04 | What if approve said “released for settlement” and stopped? | Finance has `pay_desk`; the approver’s success copy is implicit. | steal the idea (copy) | Do not hide finance’s job |
| BS-IO-05 | What if empty was quiet, not a headered table? | Empty list template. | steal the idea (example empty copy) | Do not delete empty-state tables everywhere |
| BS-IO-06 | What is the work object if it is not the entity list? | Workspaces + list regions. Stem already says jobs over CRUD. | translate — framework-bound; needs a stem amendment before an issue | Do not add `stack:` as a region display_mode from taste |
| BS-IO-07 | Can DSL say “inspect before transition” so the generated UI cannot skip it? | Processes exist; list row actions still exist. | translate — framework-bound | Do not ban row actions in every app |
| BS-IO-08 | Is `not_applicable` a miss or a kind? | Enum is there; UI treats all enums as badges. | theory — example stem | Do not add a fifth PO status |

**Failed firewall?** No. The builder did not produce an entity admin.

**Sharpest three**

1. The approver’s object is the sheet in hand, not Invoice.
2. Next-after-stamp is how you get through a day; list-return is how you browse a warehouse.
3. Dazzle can say jobs and queues; it still generates lists as the work surface.
