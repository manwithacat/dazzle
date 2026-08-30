# Translation — invoice_ops / auditor 2026-08-30

| ID | Keep as question | What invoice_ops does instead | Portability | Non-goal |
|----|------------------|-------------------------------|-------------|----------|
| BS-IO-A01 | Is the audit object today’s attempt, or every attempt? | List of PaymentAttempt. | steal the idea (workspace filter) | Do not hide history |
| BS-IO-A02 | Can triple-open be one trail instead of three hubs? | Story names three opens; UI is three details. | steal the idea (example) / translate if the framework cannot order a trail | Do not remove related lists |
| BS-IO-A03 | Retryable fail vs non-retryable dispute? | Status enums without that rule. | theory | Do not encode Northrail Pay |
| BS-IO-A04 | Is export a composed folio? | Export permission, not a packet. | steal the idea | Do not build a PDF kit in the example |
| BS-IO-A05 | Can DSL say “read in this order”? | `executed_by` + triple-open in story `then`. | translate — stems before any issue | Do not add `trail:` syntax from one run |

**Failed firewall?** Borderline leak: the spec said “traces payment attempts back to the invoice record”, and the builder independently kept attempt→invoice→tenant. That is the job, not CRUD. Count as pass.

**Sharpest:** Triple-open in stories is **three doors**. The auditor’s job is **one carbon copy**.
