# Support Ticket Classifier — System Specification

*Generated from the application model. Every guarantee cited below can be
independently verified with the command shown beside it.*

## Executive summary

The Support Ticket Classifier is a support-operations system that pairs a human
support team with declared, AI-assisted analysis. It manages support tickets,
the AI-produced classification attached to each ticket, priority assessment
results, named ticket documents (case briefs, macros, SLA notes, escalation
plans, resolution letters), and support staff org placement (department + job
title on the Team desk) — so agents handle the work while supervisors watch
ticket flow, document composition, staffing shape, and how well the AI is
performing.

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

**Support staff.** Support Staff rows carry department and job title so the Team
desk can show agents by title kanban and department placement (Frontline Support
/ Escalations / Billing Ops / AI Ops) before a flat roster or open-ticket load.
Staff status moves onboarding → active → offboarded under supervisor/admin
control (rehire and re-onboarding paths included).

**Ticket Document.** A named letter on a ticket — case brief, macro, SLA note,
escalation plan, or resolution letter — so the Support Dashboard and ticket hubs
surface composition before AI reply notes. Documents attach to a specific ticket
and move draft → published → archived under agent and supervisor control.

Tickets can be browsed and inspected in detail, and classifications and documents
can be browsed alongside them, through dedicated screens plus the Team org desk.

## Who uses it

- **Administrator** — the administrative role for the system.
- **Support Agent** — handles support tickets and views AI classifications.
  Their stated aims are to view and manage tickets, review AI classifications,
  and update ticket status; they land on **Ticket Management**.
- **Support Supervisor** — monitors ticket flow and AI classification accuracy.
  Their stated aims are to monitor ticket classifications, review AI accuracy,
  and manage team workload; they land on the **Support Dashboard**.

## Where work happens

**Support Dashboard** — supervisor home: classification metrics, dual
attention (high-severity + open), ticket document composition, live AI replies,
utility queues, and a readiness strip — no secondary open-board kanban or status
bar chart.

**Ticket Management** — agent home: pulse metrics, AI reply trail, one open
worklist, classification trail, and readiness — no twin open-only queue,
pipeline kanban, or priority bar chart.

**Classifications** — AI triage desk: classification metrics, latest queue,
open ticket grid, classification trail, and open status chart.

**Priorities** — severity desk: priority metrics, assessment queue, open work
grid, assessment trail, and priority distribution chart.

**Team** — org structure desk: staff metrics, title kanban, department queue,
flat roster, then open ticket load — hierarchy before work dump.

## How work flows through it

Six authored scenarios pin the agent-facing flows (bound to concrete screens,
not free prose):

- When a **Support Agent** works the open ticket queue, they see tickets sorted
  by age with a status filter, and opening a row hops to the ticket hub.
- When a **Support Agent** opens a ticket hub, they see the summary, a lifecycle
  strip for status, related ticket documents, and the related AI classifications
  for that ticket.
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

One durable process reinforces intake triage: when a **Ticket** enters **in_progress**, a supervisor review step is required so handoff is not an informal chat (verify: `dazzle process list`).

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

**Ticket Document lifecycle.** Ticket Documents move draft → published → archived under agent and supervisor control (supervisors may return published to draft).

<!-- dazzle-spec-brief: sha256:7b5e1e3f12da5cc20e6d7b49ed771cc6648fcaa90275487b7f9a81564c7b4f96 -->
