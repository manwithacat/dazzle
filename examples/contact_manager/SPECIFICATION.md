# Contact Manager — Specification

## Executive summary

Contact Manager stores professional and personal contact information for
relationship management, with signed engagement letters attached to the
contacts they cover. It serves two roles — Administrators and everyday Users
— who browse, search, and maintain the firm's contact book from a single
Contacts workspace.

Although the app itself is simple, its guarantees are not: it is multi-tenant
— each customer organisation's data is isolated from every other's at the
data layer — and that per-tenant boundary is enforced inside PostgreSQL
itself, so the datastore refuses to return another organisation's records
even if application code has a bug.

## What it does

The system manages two kinds of things. A **Contact** holds professional and
personal contact information for relationship management. An **Engagement
Letter** is a signed engagement letter or NDA between the firm and a contact
— every engagement letter is tied to the Contact it covers.

## Who uses it

**Administrators** have oversight of the system. **Users** do the everyday
work — browsing, searching, and maintaining contacts — from the Contacts
workspace.

## Where work happens

Everything happens in one place: the **Contacts** workspace, built for
browsing contacts and viewing details. It combines a contact search box, the
contact list, and a detail panel for the selected contact.

## How work flows through it

Six authored scenarios pin the day-to-day flows down. When a User creates a
new contact, it is saved and confirmed on screen. Browsing shows every
contact sorted alphabetically by name, and a case-insensitive search narrows
the list to contacts whose name, email, or company matches. Opening a contact
shows its full details, with a breadcrumb back to the list. A User can mark a
contact as a favourite, which sorts it to the top of the list; edits to an
existing contact are saved with the time of the change recorded.

## The technical foundation

**Security.** The system is multi-tenant: each customer organisation's data
is isolated from every other's, so one organisation cannot see another's
records (verify: `dazzle tenant list`). That boundary is enforced inside
PostgreSQL itself — the datastore refuses to return another tenant's data
even if the application code has a bug, because the rule lives in the data
layer, not the app (verify: `dazzle db verify`). Access-controlled records
are filtered to what each user is permitted to see, with the rule declared
once in the model and applied automatically to every query (verify:
`dazzle rbac report`). And every role's permissions, for every kind of record
and operation, compile on demand into an auditable access matrix whose
visibility rules can be submitted to an SMT solver for formal verification
(verify: `dazzle rbac prove`).

**Data & reliability.** All data lives in PostgreSQL — a mature,
widely-trusted relational database, with no bespoke or experimental datastore
to operate, secure, or reason about (verify: `dazzle db status`). In
production, every change to the data model is applied through versioned,
reversible migrations — the live structure is never edited by hand, so
upgrades are repeatable and fully auditable (verify: `dazzle db status`).

**Architecture.** The interface is rendered on the server and progressively
enhanced — no heavy single-page JavaScript application to maintain, which
keeps the product fast, accessible, and simple to operate (verify:
`dazzle validate`).

## Compliance posture

Attached documents — such as signed engagement letters — are served through an
entity-scoped, audited byte-access boundary: bytes are released only when the
same rule that governs the record allows it, and each access is recorded. A
static proof holds every byte-serving route to that boundary, so no new route
can stream document bytes outside it without being explicitly listed (verify:
`dazzle rbac byte-routes --strict`).

<!-- dazzle-spec-brief: sha256:e41f10dabeefb9098c2cf00d8615fecb17ee5aa14189bd4e94f0d80244778307 -->
