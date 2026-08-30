# Critique — Blue Sky invoice_ops / auditor 2026-08-30

**Prototype:** Carbon Desk (`blue_sky/runs/2026-08-30-invoice_ops-auditor/`)
**Walked:** enter as auditor → today’s settlement ribbon → PA-8841 (NSF) → trail attempt → invoice (still approved) → tenant books → yesterday’s PA-8820 on the invoice, not the desk → cut folio.
**Compared to:** invoice_ops `audit_review` + `payment_attempt_list` triple-open to Invoice and Tenant.

Do not clone this React.

| ID | Lens | Finding | Tag |
|----|------|---------|-----|
| BS-IO-A01 | Elegance | The object is **today’s attempt**, not a payment-attempt warehouse. Yesterday’s try lives on the invoice. invoice_ops lists attempts as the job. | steal |
| BS-IO-A02 | Affordances | **Carbon order**: attempt, then invoice, then tenant — one folio. invoice_ops stories already ask for triple-open; the generated UI is three hubs, not one trail. | steal |
| BS-IO-A03 | Domain | Failed retryable NSF keeps the invoice **approved** (settlement still live). Non-retryable decline becomes **disputed** the same day. | theory |
| BS-IO-A04 | Affordances | **Cut folio for the file** is the only write: an export packet. Auditor cannot modify. invoice_ops has audit-export access as a goal; the list does not compose a packet. | steal |
| BS-IO-A05 | Framework | Triple-open is specified in stories as three targets. The prototype made it **one reading order**. Dazzle can open three records; it cannot say “this is a carbon trail”. | translate |
| BS-IO-A06 | Styling | Carbon paper, frozen day. Discard kit. | discard |

## Vs invoice_ops

| Job | Prototype | invoice_ops |
|-----|-----------|-------------|
| Trace a payment | One slip on today’s ribbon → folio | Payment attempt list → triple-open three details |
| Witness settle | Procedure as recorded on the invoice sheet | Related payment attempts on the invoice hub |
| Export | Cut folio | Export as a goal, not a composed packet |

## What not to do

- Do not add CarbonTrail as an entity.
- Do not treat triple-open as already solved because the story names three targets.
