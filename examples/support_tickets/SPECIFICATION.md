# Support Tickets — Specification

## Executive summary

Support Tickets is a customer-support system that tracks customer issues from
first report to resolution, with response-time awareness built in. Customers
submit and follow their own tickets; Support Agents work a shared queue;
Support Managers watch team performance and handle escalations; an
Administrator oversees the whole operation. Conversation happens on the
ticket itself, with internal notes that customers never see.

Two guarantees stand out. First, visibility is declared in the model and
enforced automatically: a customer sees only the tickets they created and
only the customer-facing side of each conversation, while agents and managers
see everything. Second, the operational commitments are part of the model
itself — closing a critical ticket requires a manager's sign-off, and the
response-time commitment carries three escalation tiers — rather than
informal process that depends on people remembering.

## What it does

The system manages four kinds of things. A **User** is an authenticated
person whose access level determines what they may do with tickets. A
**Support Ticket** tracks a customer issue through resolution with awareness
of the response-time commitment; every ticket is tied to the User who created
it and, once picked up, to the User handling it. A **Comment** enables
threaded communication on a ticket — each tied to its ticket and its author —
including internal notes visible only to the support team. An **SLA Waiver**
is a signed acknowledgement of a response-time breach and its waiver terms,
tied to the ticket it concerns.

## Who uses it

**Customers** are end users submitting support requests and tracking their
status. They want to submit new tickets easily, follow status and updates,
and receive timely responses. They work from the My Tickets workspace, and
see only the tickets they themselves created — never another customer's — and
only comments that are not internal.

**Support Agents** are first-line support handling incoming tickets. They aim
to process tickets efficiently, keep within the response-time commitment, and
escalate complex issues to managers. They work from the Ticket Queue and the
Agent Console, with full visibility of tickets and conversations.

**Support Managers** are team leads monitoring performance and handling
escalations — watching team metrics, spotting bottlenecks in ticket flow, and
ensuring quality and customer satisfaction — from the Agent Dashboard and the
Agent Console. Managers alone can delete tickets or comments.

**Administrators** oversee the operation from the Agent Console.

## Where work happens

Four workspaces organise the work. The **Ticket Queue** is the agents' home
for managing incoming tickets: a summary, a kanban board of tickets, and the
ticket list. The **Agent Dashboard** is the personal dashboard for support
agents — ticket and comment timelines, work lists, an activity feed, a
resolution funnel, and progress tracking. **My Tickets** is the customer's
view of their own submitted tickets. The **Agent Console** — shared by
administrators, managers, and agents — lets you pick an agent and see the
tickets assigned to them, the comments on those tickets, and comparison
charts of both.

## How work flows through it

A Support Ticket moves through a declared lifecycle: **open → in progress →
resolved → closed**, and can be reopened from in progress back to open.
Eighteen authored scenarios pin the flows down; representative ones:

- When a Customer creates a support ticket, it is recorded as theirs and
  starts life as open.
- When a Support Agent picks up a ticket, it is assigned to them and moves to
  in progress.
- When a Support Agent adds an internal note, the comment is visible only to
  agents and managers.
- When a Support Agent resolves a ticket, its status becomes resolved and the
  customer is notified.
- When a Support Manager reassigns a ticket, the chosen agent takes it over
  and the previous assignee is notified.
- When the Administrator triages the full queue, they see every ticket
  regardless of customer, agent, or status, and can update many at once.

## Automation & controls

Two declared controls govern the operation. Closing a critical ticket is not
a solo act: the **Critical Ticket Close Approval** rule requires one approval
from a manager before the change takes effect. And the **Ticket Response
SLA** declares the response-time commitment on every ticket, with three
escalation tiers as a breach approaches.

## The technical foundation

**Security.** Access-controlled records are filtered to what each user is
permitted to see — the rule is declared once in the model and applied
automatically to every query the framework runs, instead of being
re-implemented on each screen (verify: `dazzle rbac report`). The system is
multi-tenant: each customer organisation's data is isolated from every
other's at the data layer (verify: `dazzle tenant list`), and that boundary
is enforced inside PostgreSQL itself — the datastore refuses to return
another tenant's data even if application code has a bug (verify:
`dazzle db verify`). Every role's permissions, for every kind of record and
operation, compile on demand into an auditable access matrix, and the
visibility rules can additionally be submitted to an SMT solver for formal
verification (verify: `dazzle rbac prove`). Sensitive changes require
explicit sign-off: approval rules with named approver roles and quorums are
part of the model itself, not an informal process (verify: `dazzle validate`).

**Data & reliability.** All data lives in PostgreSQL — a mature,
widely-trusted relational database, with no bespoke or experimental datastore
to operate, secure, or reason about (verify: `dazzle db status`). In
production, every change to the data model is applied through versioned,
reversible migrations — the live structure is never edited by hand, so
upgrades are repeatable and fully auditable (verify: `dazzle db status`).

**Architecture.** The interface is rendered on the server and progressively
enhanced — no heavy single-page JavaScript application to maintain, which
keeps the product fast, accessible, and simple to operate (verify:
`dazzle validate`). Response-time commitments are declared in the model per
record type, with escalation tiers — the commitment is explicit and
inspectable rather than a support-page promise (verify: `dazzle validate`).

## Compliance posture

Signed waiver documents are served through an entity-scoped, audited
byte-access boundary: bytes are released only when the same rule that governs
the associated ticket allows it, and each access is recorded. A static proof
holds every byte-serving route to that boundary, so no new route can stream
document bytes outside it without being explicitly listed (verify:
`dazzle rbac byte-routes --strict`).

<!-- dazzle-spec-brief: sha256:085292f77eaacdac1cbc7077d65d228aa43b21bcef5ecab90fca7b25957b4282 -->
