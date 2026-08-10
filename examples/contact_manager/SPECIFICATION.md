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
work — browsing, searching, and maintaining contacts — landing on **Home**
for overview, then **Contacts** for dual-pane browse.

## Where work happens

**Home** is the multi-panel CRM overview (Goal B media + command density +
empty-region honesty): a **media shelf** of favourite headshot thumbs first,
then directory metrics and engagement-document pulse, then dual attention —
**favourites to call** and a **composition** queue of named open letters (draft
and sent) — then a **live relationship-notes** trail rendered as Message/Bubble
conversation chrome (not a meta queue of note rows), an always-filled practice
context strip, and search — without company bar-chart voids or twin company dumps.
**Contacts** is the dual-pane browse surface: a **media shelf** of contact
headshot thumbs first (Goal B media — faces before name theater), then a
favourites queue strip, the full contact list, and a detail panel for the
selected contact (no favourite kanban theater under the list).
**Companies** is the CRM **org-structure** desk: after the directory pulse it
shows a **job-title kanban** (Account Manager / Sales Director / Engineering /
…) and a **company placement** queue over multi-person accounts, then a flat
recents timeline and context strip — without empty group-by bar-chart theater.
Engagement letter rows dual-open the letter hub or the parent Contact hub.

## How work flows through it

Six authored scenarios pin the day-to-day flows down. When a User creates a
new contact, it is saved and confirmed on screen. Browsing shows every
contact sorted alphabetically by name, and a case-insensitive search narrows
the list to contacts whose name, email, or company matches. Opening a contact
shows its full details — identity, employment strip, notes, and related
engagement letters — with a breadcrumb back to the list. A User can mark a
contact as a favourite so it appears in the Home and Contacts favourites
queues; edits to an existing contact are saved with the time of the change
recorded.

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

## Automation & controls

**Engagement letter lifecycle.** Engagement letters move draft → sent → signed; administrators may void a letter from draft, sent, or signed.

<!-- dazzle-spec-brief: sha256:b489ef620ec3c78fc3303d2aeafce6af9b91aeffba27d927294e23544602dbd7 -->
