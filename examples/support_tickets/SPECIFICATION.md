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
escalate complex issues to managers. They land on the **Ticket Queue** — a
**media shelf** of agent headshots with clean **name / role / department**
chips (not Photo Url / Email / Is Active schema labels — cycle 1933) first,
then open pressure metrics, a review
queue of open tickets, and a lifecycle kanban — with full visibility of tickets
and conversations, plus the Agent Console for per-agent inspection.

**Support Managers** are team leads monitoring performance and handling
escalations — watching team metrics, spotting bottlenecks in ticket flow, and
ensuring quality and customer satisfaction. They land on **Manager Ops**: a
multi-panel command home with an agent **media shelf** (headshot thumbs) first,
then team counts (including unassigned, **at-risk / breached SLA** pressure, and
document volume), an SLA readiness strip, a live **breach risk** queue of
tickets whose first-response SLA is at risk or breached, dual attention queues
(critical + unassigned, fold-capped), a **composition** queue of named SLA
waiver documents, and a capped live conversation trail — not conversation-only
above the fold, not a status-funnel / secondary ticket-trail thrash pair under
the fold, and not an empty personal assigned kanban. From the same Lead nav
they open **People**: staff by role and department (Support, Escalations,
Billing) before unassigned load — so reassignment is org-shaped, not a flat
warehouse roster. The team Ticket Queue and Agent Console remain available.
Managers alone can delete tickets or comments.

**Administrators** oversee the operation from the Agent Console.

## Where work happens

Six workspaces organise the work. The **Ticket Queue** is the agent home for
incoming tickets — agent **media shelf** headshots first, then summary metrics
(including conversation, **needs reply**, **awaiting customer**, **hot speech**,
**frustrated speech**, **urgent speech**, **thankful recovery**, channel paths, **internal notes**, and document volume), a **needs reply** conversation region
of customer notes whose **ball is in the agent court** (Front / Intercom "waiting
on you" grain), an **awaiting customer** conversation region of outbound notes
whose **ball is in the customer court** (cycle 1955 peer-pack; park these — do not
re-thrash as open agent work), a **hot speech** conversation region of
frustrated/urgent tone or raised escalation (cycle 1940 peer-pack; not ball-only),
a **frustrated speech** conversation region of pure `customer_tone=frustrated` notes
(cycle 1977 peer-pack; CSAT-risk lean-in — not the hot_speech OR umbrella, not channel/escalation re-stack),
an **urgent speech** conversation region of pure `customer_tone=urgent` notes
(cycle 1979 peer-pack; SLA time-pressure lean-in — not the hot_speech OR umbrella, not frustrated/channel/escalation re-stack),
a **critical escalations** conversation region of `escalation=critical` P1 speech
(cycle 1969 peer-pack; non-channel ARR-risk grain), a **raised escalations** conversation region of `escalation=raised` L2 handoffs
(cycle 1972 peer-pack; non-channel tier-2 grain), a **thankful recovery** conversation region of warm closeout speech after a fix
(cycle 1958 peer-pack; not heat re-stack), a **live chat** conversation region of channel=chat notes (cycle 1960 peer-pack), a **phone path** conversation region of channel=phone notes (cycle 1963), an **email path** conversation region of channel=email notes (cycle 1982 peer-pack; async email grain — not chat/phone/tone re-stack), an **email needs reply** conversation region of channel=email notes whose **ball is in the agent court** (cycle 1986 peer-pack; Front/Intercom "email waiting on you" — not full email_live or ball-only needs_reply re-stack), a **portal path** conversation region of channel=portal notes (cycle 1984 peer-pack; self-serve portal grain — not email/chat/phone/tone re-stack), an **internal collab** conversation region of `is_internal` agent/manager notes (cycle 1966 peer-pack; non-channel handoff grain), a **live conversation** trail of newest
notes, a **composition** queue of open SLA waivers (named breach titles), a review
queue, a kanban board of open statuses, and a recent-comment **timeline** (dated
stream, not a flat list).
**Manager Ops** is the manager home for multi-panel support ops — agent
**media shelf** first, then metrics (critical, unassigned, at-risk, breached,
conversation, needs reply, critical escalations, raised escalations, frustrated speech, urgent speech, internal notes, documents), SLA readiness, a **breach risk** queue
(at_risk / breached tickets, limit 4), dual attention queues (critical +
unassigned, limit 4 each), open **SLA waiver composition** (limit 4), a capped
**needs reply** ball (limit 4), an **email needs reply** trail of email notes waiting on agents
(limit 4) **before** a capped live conversation trail
(limit 4) — no status funnel or secondary ticket timeline (empty_region honesty;
avoids pilot scroll resource storms). Ticket rows carry an **SLA** state
(`on_track` / `at_risk` / `breached`) so queue grain matches peer Zendesk /
Front / Intercom first-response pressure. Comment rows carry **ball in court**
(`agent` / `customer` / `none`) so the trail shows who must speak next.
**People** is the org-structure desk for managers and agents: active staff
metrics, a role kanban, a department-sorted queue, a secondary roster, then
unassigned open tickets and plate-by-person load — hierarchy before dump.
Lifecycle kanban for claimed work lives on the **Agent Dashboard** (not a
second open-board on Manager Ops).
The **Agent Dashboard** is a personal dashboard for claimed work — a status
kanban of assigned open tickets, a **needs reply** ball of customer notes
waiting on agents, an **urgent speech** trail of pure urgent tone
(cycle 1979), a **frustrated speech** trail of pure frustrated tone
(cycle 1977), a **raised escalations** trail of L2 handoffs (cycle 1972),
an **awaiting customer** trail of outbound notes parked for
the customer (cycle 1955), a **thankful recovery** trail of warm closeout speech
(cycle 1958), a **my conversation** notes queue, a resolved close-out queue, and
**one** recent-comment timeline (no funnel/progress chart theater or triple
activity dumps — empty_region honesty).
**My Tickets** is the customer's home: open/WIP counts, open and in-progress
queues, one case-history timeline, and how-it-works guidance (no bar-chart
theater or duplicate open/timeline dumps).
The **Agent Console** — shared by administrators, managers, and agents — lets
you pick an agent and see their tickets, comments, comparison charts, lifecycle
progress, comment activity feed, status funnel, priority queue, comment trail,
and open ticket cards (framework display coverage under context_selector —
funnel/progress/feed live here, not on Manager Ops / Agent Dashboard heroes).

## How work flows through it

A Support Ticket moves through a declared lifecycle: **open → in progress →
resolved → closed**, and can be reopened from in progress back to open.
Opening a ticket hub shows a **Discussion** trail as Message/Bubble
conversation chrome (content + author; internal notes orient outbound) —
not an is_internal meta queue. Eighteen authored scenarios pin the flows
down; representative ones:

- When a Customer creates a support ticket, it is recorded as theirs and
  starts life as open.
- When a Support Agent picks up a ticket, it is assigned to them and moves to
  in progress.
- When a Support Agent adds an internal note, the comment is visible only to
  agents and managers.
- When a Support Agent resolves a ticket, its status becomes resolved and the
  customer is notified.
- When a Support Manager reviews team performance on Manager Ops, they see
  agent headshots first, then open, in-progress, critical, at-risk, breached,
  resolved, and conversation counts plus the breach-risk queue, critical/
  unassigned queues, and live note trail.
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
Long-running multi-persona work — such as manager review when a ticket enters
in-progress — is declared as a durable process rather than an informal handoff
(verify: `dazzle process list`).

## Compliance posture

Signed waiver documents are served through an entity-scoped, audited
byte-access boundary: bytes are released only when the same rule that governs
the associated ticket allows it, and each access is recorded. A static proof
holds every byte-serving route to that boundary, so no new route can stream
document bytes outside it without being explicitly listed (verify:
`dazzle rbac byte-routes --strict`).

<!-- dazzle-spec-brief: sha256:f702748a638c74e4bff42de32b263c9ce315f68ca60e3942e068c40a73cd6b36 -->
