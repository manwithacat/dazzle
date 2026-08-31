# Stem: AP money theory (settle, credit, NSF, not_applicable)

## Claim

invoice_ops money words are **role-specific judgements**, not one status
vocabulary. Blue Sky 2026-08-30 (requester/finance/auditor/approver) named
four that the DSL already has the enums for. Write the theory here; do not
invent entities or rails from the prototypes.

## Reconstruct

1. **Settle is finance remittance.** `process settle_invoice` fires when
   Invoice becomes `approved` and charges the payment provider. Requester
   **attests / submits** and is out. Daybook “settle = goods receipt” is a
   true reading of AP; this app gives the word to the till. Do not give the
   requester a pay button to paper over the overload (#1669 / BS-IO-R04).

2. **Dispute outcome is approved | rejected.** Credit-as-remainder (accept
   a credit, return to ready; remainder speaks) is more true for AP than
   stand-down-as-duplicate. The DSL keeps `disputed -> approved | rejected`.
   Do not add a CreditNote entity from the finance prototype (BS-IO-F04).

3. **Retryable fail does not move Invoice.** NSF / rail failure: Invoice
   stays **approved** (settlement still live); PaymentAttempt is `failed`.
   Non-retryable decline (or an explicit dispute) may move Invoice to
   `disputed` the same day. Status enums do not encode that rule; copy and
   process must not treat `PaymentAttemptFailed` as an invoice status change
   (BS-IO-F03, BS-IO-A03).

4. **`po_match: not_applicable` is a kind.** Standing retainer / no PO
   expected. It lives on **LineItem**, not Invoice. Unmatched ≠
   not_applicable ≠ partial. Desks that treat every enum as a “miss” badge
   lie. Do not add a fifth PO status (BS-IO-08).

## Not this

- Requester pay / “I settle my own invoice.”
- CreditNote, Remainder, NeedsYou, or a named rail (Northrail Pay) from
  one prototype.
- Changing Invoice / PaymentAttempt enums “because the prototype had nicer
  names.”
- Encoding retryable-vs-dispute as a new Invoice status.
- Treating `not_applicable` as unmatched in approve/submit gates (#1668
  steal must honour this).
- Framework primitives. Split-line widget stays parked on #1662 until a
  stem of its own.

## Expressions

- Evidence: `blue_sky/runs/2026-08-30-invoice_ops-*/TRANSLATION.md`
  (BS-IO-R04, F03/F04, A03, 08)
- DSL already: `process settle_invoice`; LineItem `po_match`; Invoice
  `disputed -> approved | rejected`; PaymentAttempt `pending|succeeded|failed`
- Sibling steal (copy/guards, not theory): #1668
- Job-object stem stays separate: `story-driven-jobs.md`
