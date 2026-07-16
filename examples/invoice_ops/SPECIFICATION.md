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
supplier, and records who submitted it. Each invoice is itemised into Line
Items. Settlement is tracked through Payment Attempts — each one a discrete
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

The **Finance Operations** workspace is the shared home for every persona —
requester, approver, finance, auditor, and admins. It opens with invoice
metrics (submitted, approved, disputed, paid), the lifecycle funnel, and real
review queues: awaiting approval, ready to pay, and open disputes, plus a
payment-attempt health chart. Each queue row opens the invoice itself, so
triage and action happen in one place rather than a flat invoice list.

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

<!-- dazzle-spec-brief: sha256:efcf52814e59aee4a0b9856e262efba41a64b7037f9a0e6f72fbe75877c85d2f -->
