# Assumptions

Domain facts the brief did not state. Invented so the desk can tell the truth.

## Place

- **Meridian Group** is a holding company. Operating companies are **tenants** with their own books.
- The auditor sits at **Carbon Desk**, named for the carbon-copy order of a trail: original attempt, invoice copy, tenant copy.
- Tenants in this slice:
  - **T-ORCH** Orchard & Co. (Delaware) — seasonal cash, NSF retries in late August.
  - **T-HALC** Halcyon Labs (Massachusetts) — card under $5k; non-retryable declines go to dispute the same day.
  - **T-KITE** Kite Harbor Logistics (Singapore ops, Delaware holdco books) — fuel invoices split on purpose.

## People

- **A. Okada**, Auditor. Only role in this slice. No AP, no controller login.
- AP names appear only as stamps on the record: Mara Chen (Orchard), R. Voss (Halcyon), Priya Nair (Kite).

## Payment Attempt

- Statuses used as specified: `pending`, `succeeded`, `failed`.
- An attempt always belongs to one invoice and one tenant. Tenant is denormalized onto the attempt so a row can triple-open without another lookup screen.
- Attempts are the mechanical tries inside **Settle Approved Invoice**.
- Processor is **Northrail Pay** (invented). Not a live rail.
- Methods used: ACH, wire, card.
- Retryable vs not is a processor fact. NSF is retryable. `ACCOUNT_CLOSED` is not.
- Yesterday’s attempts can exist on an invoice without appearing on today’s desk. **PA-8820** is that case.

## Invoice

- Required facts used: `invoice_number`, `supplier`, `amount`.
- Statuses used as specified: `draft`, `submitted`, `approved`, `partially_paid`, `rejected`, `disputed`, `paid`.
- Supplier is the vendor being paid. Tenant is whose books the bill sits on.
- Draft, submitted, and rejected invoices have no payment attempts. They appear only on the tenant’s invoice-book snapshot so the lifecycle is visible without an invoice list.
- `partially_paid` means at least one succeeded attempt for less than the invoice amount, with remainder still open.
- `disputed` here means settlement was abandoned after a non-retryable failure (Halcyon / Nightshift Couriers).
- `approved` after failed retryable attempts means settlement is still live (Orchard / Barrow Cold Storage).

## Tenant

- Not specified in the brief. Invented as the operating-company books an invoice lives on, because the required moment says a row opens **Tenant via tenant id**.
- The auditor has no tenant list. Tenant is the third sheet of a payment-attempt trail.

## Procedure: Settle Approved Invoice

- Performed by AP and a night/afternoon queue, not by the auditor.
- Canonical steps: draft → submit → approve (or reject, which never settles) → payment attempts → mark paid / partially paid / dispute.
- The auditor’s job is to see where that procedure is sitting on the invoice the attempt traces to.

## Permissions and export

- Fake auth: one button.
- List permission on Payment Attempt is why the desk is a ribbon of attempts, not a warehouse of invoices.
- “Cut folio for the file” is the audit export. It stamps the slip locally and composes attempt + invoice + tenant + procedure. No server, no real custody store. Packet id format `CD-YYYYMMDD-PAnnnn-OKADA` is invented.

## Time

- The blotter is frozen on **30 August 2026**. Counts and “today” mean that date.
- Amounts are USD.
