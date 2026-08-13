# Invoice Ops — System Specification

*Generated from the application model. Every guarantee cited below can be
independently verified with the command shown beside it.*

## Executive summary

Invoice Ops is a multi-tenant supplier-invoice processing system. Each customer
company operates as its own tenant, managing its suppliers, the invoices those
suppliers send, the line items on each invoice, and the attempts made to pay
them. Invoices move through a declared approval-and-payment lifecycle — from
draft, through submission and approval, to settlement — with maker/checker
separation built into the roles themselves: the person who raises an invoice is
never the person who approves it.

Two guarantees stand out. First, tenant isolation is not an application
convention: because customers share the same storage, the per-tenant boundary
is enforced inside PostgreSQL itself through row-level security policies, so
the data layer refuses to return another tenant's records even if application
code has a bug (verifiable with `dazzle db verify`). Second, sign-off is part
of the model, not an informal habit — invoice changes require explicit
approval, and high-value invoices require two approvers, declared as rules the
system enforces.

## What it does

**Tenants and their people.** A Tenant is the root of the system — a customer
company processing supplier invoices. Every User belongs to exactly one
tenant, and everything a user touches is resolved against that membership.

**Suppliers.** A Supplier is a business that bills a tenant. A supplier's
banking details are held separately as a Supplier Bank Account — deliberately
isolated from the general supplier record so that stricter access control can
apply to payment-sensitive information: only finance staff and tenant
administrators can view or change them.

**Invoices and their settlement.** An Invoice is a supplier's bill moving
through an approval and payment lifecycle; it belongs to a tenant, names its
supplier, records a due date for SLA pressure, and records who submitted it.
Each invoice is itemised into Line Items — description, quantity, unit amount,
tax code, and PO match status that controllers scan when reviewing composition.
Settlement is tracked through Payment Attempts — each one a discrete
attempt to settle an approved invoice via the payment provider, so the payment
history of an invoice is a first-class record rather than a status flag.

## Who uses it

- **Requester** — the maker: raises supplier invoices, itemises them, and
  submits them for approval. Requesters own the line items on their invoices.
- **Approver** — the checker: reviews submitted invoices and approves or
  rejects them. Approvers can see invoices, line items, suppliers, and payment
  attempts, but cannot create invoices — the maker/checker split is structural.
- **Finance Operator** — settles approved invoices and handles disputes;
  manages suppliers and their bank accounts, and records payment attempts.
- **Auditor** — a read-only reviewer with audit-export access: sees the users,
  suppliers, invoices, line items, and payment attempts of their tenant, and
  changes none of them.
- **Tenant Administrator** — manages the users, suppliers, and per-tenant
  configuration of one tenant, including approval thresholds; the only role
  that can delete invoices or payment records.
- **Finance Administrator** — cross-cutting finance oversight, an override
  role above finance: can override blocked payments and audit financial
  records.

Every one of these roles sees only their own tenant's records — each
visibility rule reads, in effect, "its tenant is the signed-in user's tenant".

## Where work happens

Work is organised into **role-shaped desks**, not one shared invoice warehouse:

- **My Invoices** — requester home: line-item composition (document body),
  draft and in-flight queues, status kanban, supplier grid, and pipeline metrics
  (no status bar-chart or twin invoice timeline under the fold).
- **Approval Desk** — approver home: a **goods receipt** three-way match watch
  (cycle 1967 peer-pack), a **tax certificate watch** of reverse-charge
  certs (cycle 1959 peer-pack), a **PO packet watch** of signed PO covers
  (cycle 1965 peer-pack), awaiting-approval queue, **named AP packets**
  (remittance / credit memo / PO / tax / payment confirmation / goods receipt /
  dispute packet) as document composition, live AP discussion as Message/Bubble
  conversation chrome, approval board, and supplier context grid (no decision-timeline dump).
- **Pay Desk** — finance home (multi-panel settlement): metrics, a **draft packet
  release gate** of unpublished remittance/credit packets (cycle 1957 peer-pack —
  publish before the settle batch), a **compliance draft gate** of vendor
  onboarding packets still draft (W-9 / COI / tax / lien / ACH — cycle 2000 peer-pack;
  not form_w9-only or all-draft re-stack), a **remittance advice watch** of SEPA/ACH covers
  (cycle 1974 peer-pack), a **credit memo watch** of VAT/short-ship credits
  (cycle 1971 peer-pack), a **payment confirmation trail** of batch
  ACKs (cycle 1961 peer-pack), capped ready-to-pay and past-due attention
  panels, named remittance/payment-confirmation packets, live AP notes as
  Message/Bubble conversation chrome, then settle board (no payment-health chart
  or twin dispute trail under the fold).
- **Audit Review** — auditor home: evidence packet covers and named AP document
  composition first (remittance / PO / tax), then disputed work and payment-attempt
  trail (cycle 1942 document peer-pack) — not chart-only or trail-only thrash.
- **Finance Operations** — shared ops overview: **packet cover wall** first
  (InvoiceDocument.preview_url remittance / PO / tax / goods-receipt thumbs — peer Bill.com /
  Melio / Tipalti money grain, not teammate headshot shelves), document pulse
  with draft count, a **draft packet release gate** (status=draft packets — cycle 1957), a **goods receipt watch**
  (doc_kind=goods_receipt three-way match slips — cycle 1967), a **credit memo watch**
  (doc_kind=credit_memo VAT/short-ship credits — cycle 1971), a **debit memo watch**
  (doc_kind=debit_memo vendor additional charges opposite credit_memo — cycle 1981), a **vendor statement watch**
  (doc_kind=vendor_statement period-end AP reconcile covers — cycle 1983), a **packing slip watch**
  (doc_kind=packing_slip carrier packing slips for three-way match — cycle 1985), an **ACH authorization watch**
  (doc_kind=ach_authorization signed ACH/SEPA mandate before first settle — cycle 1987), a **wire instructions watch**
  (doc_kind=wire_instructions bank wire details before first high-value wire — cycle 1989), a **lien waiver watch**
  (doc_kind=lien_waiver conditional/final lien waivers before construction or facility pay release — cycle 1991), an **insurance certificate watch**
  (doc_kind=insurance_certificate COI on file before contractor/facility pay release — cycle 1993), a **Form W-9 watch**
  (doc_kind=form_w9 IRS W-9 / vendor TIN on file before first US settle — cycle 1995), a **compliance draft gate**
  (status=draft and onboarding kinds W-9/COI/tax/lien/ACH — cycle 2000; not form_w9-only or all-draft re-stack), a **remittance advice watch**
  (doc_kind=remittance SEPA/ACH covers — cycle 1974), a **dispute packet watch**
  (doc_kind=dispute_packet exception evidence — cycle 1978), a **tax certificate watch**
  (doc_kind=tax_certificate reverse-charge certs — cycle 1959), a **PO packet watch**
  (doc_kind=po_packet signed PO covers — cycle 1965), then dual attention (awaiting + ready), **named
  AP packets** (InvoiceDocument composition queue) and line-item body, live
  discussion trail as Message/Bubble conversation chrome, metrics, and ops
  kanban (no lifecycle funnel, payment bar chart, or paid timeline voids).
- **Suppliers** — vendor **org-structure** desk: after the vendor pulse it
  shows a **region kanban** (EMEA / AMER / APAC) and a **multi-invoice supplier
  load** board over open AP, then a flat roster, bank refs, and recent invoices
  — without status bar-chart or twin invoice-timeline theater.
- **Team** — AP **org-structure** desk: after the people pulse it shows a
  **job-title kanban** (Requester / Approver / Finance Operator / Auditor) and a
  **department** queue (Accounts Payable / Treasury / Controllership / Audit)
  before the flat roster and open invoice load — without tenant bar-chart or
  invoice-timeline theater under the fold.
- **Payments** — payment-attempt trail with settle board and attempt health
  chart.
- **Line Items** — composition desk: metrics with matched/unmatched counts, a
  **PO match kanban**, tax-coded line body queue, and open invoice docs (not bare
  spreadsheet export theater).
- **Disputes** — finance/auditor/admin dispute desk (`dispute_desk`): dispute
  metrics (open + with-reason counts), document pulse with **dispute packet**
  count, a **dispute packet watch** of GRN/tax/closed-PO evidence covers
  (doc_kind=dispute_packet — cycle 1978 peer-pack), **reason-bearing disputed queue**
  (`Invoice.dispute_reason` via fitness.repr_fields + list/hub fields — peer
  Bill.com / Melio / Tipalti exception grain), settle pipeline kanban, payment
  attempt trail, and status mix chart.
- **Bank Accounts** — supplier bank-ref desk: bank metrics, bank cards, ready-to-pay
  queue, supplier trail, and invoice status chart.

Each queue row opens the invoice hub, so triage and action stay on the job
surface rather than a flat entity list.

## How work flows through it

An Invoice carries seven declared lifecycle states: *draft*, *submitted*,
*approved*, *partially paid*, *rejected*, *disputed*, and *paid*. A requester
raises an invoice as a draft and submits it; an approver approves or rejects
it; finance settles approved invoices — recording payment attempts as it goes,
with an invoice standing at partially paid until settlement completes — and
handles anything that becomes disputed. The lifecycle ends at paid.

The state of every invoice, and the trail of who moved it, is inspectable at
each step: the auditor role exists precisely to review that trail and export
audit evidence.

## Automation & controls

**Tenant lifecycle.** Tenant roots move active ↔ suspended (tenant_admin only).

**Payment attempt lifecycle.** Payment attempts move pending → succeeded|failed; failed may return to pending for retry.

**What runs without a human.** The *Settle Approved Invoice* process runs
automatically when an invoice changes, carrying out settlement work in the
background rather than relying on someone to remember it.

**Declared controls.** Two approval rules are part of the model itself, not an
informal process:

- *Standard Invoice Approval* — changes on an invoice require one approval
  from an approver.
- *High-Value Invoice Approval* — changes on an invoice require two approvals
  from approvers.

## The technical foundation

**Security.** Access-controlled records are filtered to what each user is
permitted to see; the rule is declared once in the model and applied
automatically to every query the framework runs, instead of being
re-implemented — and re-checked — on each screen. (Verify:
`dazzle rbac report`.) The system is multi-tenant: each customer's data is
isolated from every other customer's at the data layer, so one organisation
cannot see another organisation's records. (Verify: `dazzle tenant list`.) And
because customers share storage, that per-tenant boundary is enforced inside
PostgreSQL itself through row-level security policies — the data layer refuses
to return another tenant's records even if the application code has a bug,
because the rule lives in the data layer, not the app. (Verify:
`dazzle db verify`.) Every role's permissions, for every record type and
operation, are declared as machine-readable policy that compiles on demand
into an auditable access matrix — permission review is something you run and
diff, not something you eyeball — and the row-visibility rules can
additionally be submitted to an SMT solver for formal verification. (Verify:
`dazzle rbac prove`.) Finally, sensitive changes require explicit sign-off:
approval rules with named approver roles and quorums are part of the model
itself, not an informal process that depends on people remembering to ask.
(Verify: `dazzle validate`.)

**Data & reliability.** All data is stored in PostgreSQL — a mature,
widely-trusted relational database, with no bespoke or experimental datastore
to operate, secure, or reason about. (Verify: `dazzle db status`.) In
production, every change to the data model is applied through versioned,
reversible migrations; the live schema is never edited by hand, so upgrades
are repeatable and fully auditable. (Verify: `dazzle db status`.)

**Architecture.** The interface is rendered on the server and progressively
enhanced — no heavy single-page JavaScript application to maintain, which
keeps the product fast, accessible, and simple to operate. (Verify:
`dazzle validate`.) Significant business moments are modelled as first-class
events with formally-defined semantics, giving the system a precise, auditable
record of what happened and when. (Verify: `dazzle specs asyncapi`.)
Long-running and scheduled work — such as invoice settlement — is executed by
a built-in background engine coordinated through the database itself: there is
no separate queue infrastructure to deploy or operate, and an interrupted run
is picked up rather than lost. (Verify: `dazzle process list`.)

<!-- dazzle-spec-brief: sha256:4769cb34c2db3fef95749cf70d668df50108904371bdf58c893846a5ab63fa1d -->
