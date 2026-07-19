# Support Ticket Classifier — System Specification

*Generated from the application model. Every guarantee cited below can be
independently verified with the command shown beside it.*

## Executive summary

The Support Ticket Classifier is a support-operations system that pairs a human
support team with declared, AI-assisted analysis. It manages support tickets,
the AI-produced classification attached to each ticket, and priority assessment
results — so agents handle the work while supervisors watch both the ticket
flow and how well the AI is performing.

What sets it apart is how the AI is wired in: every AI-assisted step — ticket
classification, priority assessment, sentiment analysis, response suggestion —
is declared in the application model itself, each with an explicit trigger,
prompt contract, and timeout, rather than as ad-hoc calls buried in code. What
the AI is allowed to touch is reviewable in one place, and a skeptic can check
it directly: `dazzle validate` confirms the declared model.

## What it does

**Support tickets.** A Support Ticket is the unit of incoming customer work —
the record agents view, manage, and update.

**Ticket classifications.** A Ticket Classification is always tied to the
specific Support Ticket it describes, so every AI judgement about a ticket
stays attached to that ticket and can be reviewed against it.

**Priority assessments.** A Priority Assessment Result records the outcome of
assessing a ticket's priority, giving the team a standing record of how urgency
was judged.

Tickets can be browsed and inspected in detail, and classifications can be
browsed alongside them, through three dedicated screens.

## Who uses it

- **Administrator** — the administrative role for the system.
- **Support Agent** — handles support tickets and views AI classifications.
  Their stated aims are to view and manage tickets, review AI classifications,
  and update ticket status; they land on **Ticket Management**.
- **Support Supervisor** — monitors ticket flow and AI classification accuracy.
  Their stated aims are to monitor ticket classifications, review AI accuracy,
  and manage team workload; they land on the **Support Dashboard**.

## Where work happens

**Support Dashboard** — supervisor home: classification metrics (open, classified,
in progress), an open-ticket review queue, and a list of recent AI
classifications so quality sits beside the work it describes.

**Ticket Management** — agent home: a queue of non-closed tickets for day-to-day
handling, plus the full ticket list for history.

## How work flows through it

Six authored scenarios pin the agent-facing flows (bound to concrete screens,
not free prose):

- When a **Support Agent** works the open ticket queue, they see tickets sorted
  by age with a status filter, and opening a row hops to the ticket hub.
- When a **Support Agent** opens a ticket hub, they see the summary, a lifecycle
  strip for status, and the related AI classifications for that ticket.
- When a **Support Supervisor** reviews the classification trail, opening a
  classification row hops back to the parent ticket hub so AI labels never
  float free of the work item.
- When a **Support Agent** captures a new ticket, it starts life open and is
  eligible for the declared auto-classify AI step on create.
- When a **Support Agent** transitions ticket lifecycle, status is editable on
  the lifecycle strip until the ticket is closed.
- When an agent inspects a single classification run, they see triage labels,
  a confidence strip, the suggested response, and the LLM job id for audit.

## Automation & controls

Four AI-assisted steps are declared in the model and run as part of the
system's operation:

- **Classify Support Ticket** — AI-assisted classification of an incoming
  ticket.
- **Assess Ticket Priority** — AI-assisted assessment of a ticket's priority.
- **Analyze Customer Sentiment** — AI-assisted reading of the customer's
  sentiment.
- **Suggest Response** — AI-assisted drafting of a suggested response.

Because each step is declared rather than hand-coded, the full inventory of
what the AI does in this system is exactly the four items above — reviewable in
one place, with nothing hidden in application code.

## The technical foundation

**Security.** Access-controlled records are filtered to what each user is
permitted to see. The rule is declared once in the model and applied
automatically to every query the framework runs, instead of being
re-implemented — and re-checked — on each screen.
(Verify: `dazzle rbac report`.) Beyond filtering, every role's permissions, for every entity and
operation, are declared as machine-readable policy. They compile on demand into
an auditable access matrix — so permission review is something you run and
diff, not something you eyeball — and the row-visibility rules can additionally
be submitted to an SMT solver for formal verification. (Verify:
`dazzle rbac prove`.)

**Data & reliability.** All data is stored in PostgreSQL — a mature,
widely-trusted relational database. There is no bespoke or experimental
datastore to operate, secure, or reason about. (Verify: `dazzle db status`.) In
production, every change to the data model is applied through versioned,
reversible migrations. The live schema is never edited by hand, so upgrades are
repeatable and fully auditable. (Verify: `dazzle db status`.)

**Architecture.** The interface is rendered on the server and progressively
enhanced. There is no heavy single-page JavaScript application to maintain,
which keeps the product fast, accessible, and simple to operate. (Verify:
`dazzle validate`.) And the AI itself is governed: AI-assisted steps are
declared in the model — each with an explicit trigger, prompt contract, and
timeout — rather than ad-hoc calls buried in code, so what the AI is allowed to
touch is reviewable in one place. (Verify: `dazzle validate`.)

<!-- dazzle-spec-brief: sha256:b01664b0bbd1c04785e7d3b8d96c312b0821398c8ce443a946644d56777a8f41 -->
