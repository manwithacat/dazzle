# Critique — Blue Sky invoice_ops / finance 2026-08-30

**Prototype:** Till (`blue_sky/runs/2026-08-30-invoice_ops-finance/`)
**Walked:** sit as operator → Helion remittance on the blotter → next paper (Northwind) → Open disputes → Meridian credit then remit remainder → stand Osprey down as duplicate.
**Compared to:** invoice_ops `pay_desk` + `dispute_desk` as Dazzle generates them (approved list, disputed list, payment attempts as related rows).

Do not clone this React.

| ID | Lens | Finding | Tag |
|----|------|---------|-----|
| BS-IO-F01 | Elegance | **One blotter, two trays.** Ready and disputed are not two workspaces. invoice_ops splits `pay_desk` and `dispute_desk`. | steal |
| BS-IO-F02 | Affordances | After remittance the **next remainder comes forward**. invoice_ops returns to the list. Same as approver BS-IO-01. | steal |
| BS-IO-F03 | Domain | A failed rail **does not change invoice status**; retry is the same pad. DSL: PaymentAttempt failed vs Invoice status are easy to desync in a list UI. | steal |
| BS-IO-F04 | Domain | Dispute outcomes are **accept credit (return to ready)** vs **stand down**. invoice_ops disputed → approved/rejected. Credit-as-remainder is invented and more true for AP. | theory |
| BS-IO-F05 | Elegance | Original amount never changes; remainder = original − remittances − credits. Dazzle shows `amount` as a field; the sitting needs remainder as the number in hand. | translate |
| BS-IO-F06 | Styling | Till, millwork, carmine PAID stamp. Do not port. | discard |

## Vs invoice_ops

| Job | Prototype | invoice_ops |
|-----|-----------|-------------|
| Ready to pay | Paper already on the blotter | `ready_to_pay` list |
| Dispute | Second tray, same sitting | Separate `dispute_desk` |
| Pay | Record remittance; remainder speaks | Create PaymentAttempt; status via events |

## What not to do

- Do not merge pay and dispute desks in DSL just to copy two trays.
- Do not add a Remainder entity.
