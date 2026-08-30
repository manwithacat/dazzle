# Translation — invoice_ops / finance 2026-08-30

| ID | Keep as question | What invoice_ops does instead | Portability | Non-goal |
|----|------------------|-------------------------------|-------------|----------|
| BS-IO-F01 | Can ready-to-pay and dispute be one sitting? | Two workspaces. | steal the idea (nav / default desk) | Do not delete dispute_desk from taste |
| BS-IO-F02 | Next remainder in hand after remittance? | Back to the list. | steal the idea | Same as approver — not a new region type |
| BS-IO-F03 | Does a failed attempt leave the invoice approved? | Possible; the UI does not say it. | steal the idea (copy) | Do not hide failed attempts |
| BS-IO-F04 | Is a dispute a credit or a stand-down? | approved/rejected from disputed. | theory | Do not invent CreditNote from one prototype |
| BS-IO-F05 | Is the number in hand remainder, or original amount? | `amount` on Invoice. | translate — computed remainder is framework-hard without derived fields | Do not store remainder as a writeable column |

**Failed firewall?** No.

**Sharpest:** Finance’s object is **today’s outlay on the blotter**, and remainder is the number, not the original bill.
