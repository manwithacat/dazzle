# Agent domain: Support Tickets — Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

Support Tickets is a customer-support system that tracks customer issues from first report to resolution, with response-time awareness built in. Customers submit and follow their own tickets; Support Agents work a shared queue; Support Managers watch team performance and handle escalations; an

**Source:** `/Volumes/SSD/Dazzle/examples/support_tickets/SPECIFICATION.md`
**Fingerprint:** `38ccf96f0e658adc`

## Personas (jobs)

- **Agent** (`agent`, stable≈`agent`, grounded) — desk `agent_desk` — role word in founder brief
- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Customer** (`customer`, stable≈`customer`, grounded) — desk `customer_desk` — role word in founder brief
- **Staff** (`staff`, stable≈`staff`, grounded) — desk `staff_desk` — Internal team member

## Nouns (domain types)

- **SLAWaiver** (grounded) owner≈`assigned_to` lifecycle: — — definitional sentence in founder brief (A X is …)
- **SupportTicket** (grounded) owner≈`assigned_to` lifecycle: open → in_progress → waiting_on_customer → escalated → resolved → closed — definitional sentence in founder brief (A X is …)
- **Intercom** (grounded) owner≈`assigned_to` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Email** (grounded) owner≈`assigned_to` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Cloud** (grounded) owner≈`assigned_to` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Zendesk** (grounded) owner≈`assigned_to` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Front** (grounded) owner≈`assigned_to` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Comment** (grounded) owner≈`assigned_to` lifecycle: — — appears in founder brief (source=comma_list)

## Rejected chrome (not domain)

`Administrator`, `Approval`, `Avoid`, `Console`, `Dashboard`, `JavaScript`, `Lead`, `Message`, `Need`, `Op`, `Photo`, `Support`, `Tickets`, `Url`, `Waiver`, `agent`, `associated`, `auditable`, `authenticated`, `breach`, `byte`, `capped`, `change`, `chosen`, `close`, `critical`, `data`, `datastore`, `declared`, `department`, `document`, `durable`, `escalation`, `flat`, `fold`, `framework`, `informal`, `kanban`, `lifecycle`, `live`, `mature`, `model`, `multi`, `operation`, `operational`, `personal`, `product`, `queue`, `recent`, `resolved`, `response`, `review`, `role`, `shared`, `signed`, `solo`, `static`, `team`, `technical`, `ticket`, `trail`, `visibility`, `whole`, `work`

## Desks

- **agent_desk** for `agent` (hypothesis) owner≈`assigned_to` — Job desk for Agent
- **manager_desk** for `manager` (hypothesis) owner≈`assigned_to` — Job desk for Manager
- **customer_desk** for `customer` (hypothesis) owner≈`assigned_to` — Job desk for Customer
- **staff_desk** for `staff` (hypothesis) owner≈`assigned_to` — Job desk for Staff

## Demo spine (seed stories)

- `agent`: Agent has seeded SupportTicket rows for their desk (min_rows=1, entity≈SupportTicket)
- `manager`: Manager has seeded SupportTicket rows for their desk (min_rows=1, entity≈SupportTicket)
- `customer`: Customer has seeded SupportTicket rows for their desk (min_rows=1, entity≈SupportTicket)
- `staff`: Staff has seeded SupportTicket rows for their desk (min_rows=1, entity≈SupportTicket)

## Open questions

- `q1`: Can a ticket have multiple comments, or just one?

## Process candidates (hypothesis)

- **approval_flow** (hypothesis) entity≈`SupportTicket` personas=[requester, approver] — SupportTicket: requester submits, approver decides (approve/reject)
- **escalation** (hypothesis) entity≈`SupportTicket` personas=[agent, manager] — SupportTicket: worker escalates to manager when blocked or SLA risk
- **assignment** (hypothesis) entity≈`SupportTicket` personas=[manager, agent] — SupportTicket: auto or manager assignment to a worker
- **triage** (hypothesis) entity≈`SupportTicket` personas=[agent, manager] — SupportTicket: intake triage before deep work

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.
- process_candidates are hypotheses — author `process` blocks when multi-persona handoffs are real; do not invent decorative processes.
- 1 noun(s) carry lifecycle_hint — emit transitions: (and lifecycle: evidence when product requires ADR-0020).

## Machine twin

```json
{
  "version": 1,
  "title": "Support Tickets \u2014 Specification",
  "summary": "Support Tickets is a customer-support system that tracks customer issues from first report to resolution, with response-time awareness built in. Customers submit and follow their own tickets; Support Agents work a shared queue; Support Managers watch team performance and handle escalations; an",
  "source_path": "/Volumes/SSD/Dazzle/examples/support_tickets/SPECIFICATION.md",
  "source_sha256": "38ccf96f0e658adc",
  "personas": [
    {
      "id_hint": "agent",
      "label": "Agent",
      "job": "",
      "desk": "agent_desk",
      "stable_id_candidate": "agent",
      "status": "grounded",
      "evidence": "role word in founder brief"
    },
    {
      "id_hint": "manager",
      "label": "Manager",
      "job": "",
      "desk": "manager_desk",
      "stable_id_candidate": "manager",
      "status": "grounded",
      "evidence": "role word in founder brief"
    },
    {
      "id_hint": "customer",
      "label": "Customer",
      "job": "",
      "desk": "customer_desk",
      "stable_id_candidate": "customer",
      "status": "grounded",
      "evidence": "role word in founder brief"
    },
    {
      "id_hint": "staff",
      "label": "Staff",
      "job": "Internal team member",
      "desk": "staff_desk",
      "stable_id_candidate": "staff",
      "status": "grounded",
      "evidence": "extract_personas + brief"
    }
  ],
  "nouns": [
    {
      "name": "SLAWaiver",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "SupportTicket",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [
        "open",
        "in_progress",
        "waiting_on_customer",
        "escalated",
        "resolved",
        "closed"
      ],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "Intercom",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "Email",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "Cloud",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "Zendesk",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "Front",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "Comment",
      "status": "grounded",
      "evidence": "appears in founder brief (source=comma_list)",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    }
  ],
  "desks": [
    {
      "persona": "agent",
      "name": "agent_desk",
      "purpose": "Job desk for Agent",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    },
    {
      "persona": "manager",
      "name": "manager_desk",
      "purpose": "Job desk for Manager",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    },
    {
      "persona": "customer",
      "name": "customer_desk",
      "purpose": "Job desk for Customer",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    },
    {
      "persona": "staff",
      "name": "staff_desk",
      "purpose": "Job desk for Staff",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    }
  ],
  "demo_spine": [
    {
      "persona": "agent",
      "story": "Agent has seeded SupportTicket rows for their desk",
      "min_rows": 1,
      "entity_hint": "SupportTicket"
    },
    {
      "persona": "manager",
      "story": "Manager has seeded SupportTicket rows for their desk",
      "min_rows": 1,
      "entity_hint": "SupportTicket"
    },
    {
      "persona": "customer",
      "story": "Customer has seeded SupportTicket rows for their desk",
      "min_rows": 1,
      "entity_hint": "SupportTicket"
    },
    {
      "persona": "staff",
      "story": "Staff has seeded SupportTicket rows for their desk",
      "min_rows": 1,
      "entity_hint": "SupportTicket"
    }
  ],
  "open_questions": [
    {
      "id": "q1",
      "text": "Can a ticket have multiple comments, or just one?",
      "blocks_promote": false
    }
  ],
  "process_candidates": [
    {
      "id_hint": "approval_flow",
      "summary": "SupportTicket: requester submits, approver decides (approve/reject)",
      "personas": [
        "requester",
        "approver"
      ],
      "entity_hint": "SupportTicket",
      "status": "hypothesis"
    },
    {
      "id_hint": "escalation",
      "summary": "SupportTicket: worker escalates to manager when blocked or SLA risk",
      "personas": [
        "agent",
        "manager"
      ],
      "entity_hint": "SupportTicket",
      "status": "hypothesis"
    },
    {
      "id_hint": "assignment",
      "summary": "SupportTicket: auto or manager assignment to a worker",
      "personas": [
        "manager",
        "agent"
      ],
      "entity_hint": "SupportTicket",
      "status": "hypothesis"
    },
    {
      "id_hint": "triage",
      "summary": "SupportTicket: intake triage before deep work",
      "personas": [
        "agent",
        "manager"
      ],
      "entity_hint": "SupportTicket",
      "status": "hypothesis"
    }
  ],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.",
    "process_candidates are hypotheses \u2014 author `process` blocks when multi-persona handoffs are real; do not invent decorative processes.",
    "1 noun(s) carry lifecycle_hint \u2014 emit transitions: (and lifecycle: evidence when product requires ADR-0020)."
  ],
  "rejected_chrome": [
    "Administrator",
    "Approval",
    "Avoid",
    "Console",
    "Dashboard",
    "JavaScript",
    "Lead",
    "Message",
    "Need",
    "Op",
    "Photo",
    "Support",
    "Tickets",
    "Url",
    "Waiver",
    "agent",
    "associated",
    "auditable",
    "authenticated",
    "breach",
    "byte",
    "capped",
    "change",
    "chosen",
    "close",
    "critical",
    "data",
    "datastore",
    "declared",
    "department",
    "document",
    "durable",
    "escalation",
    "flat",
    "fold",
    "framework",
    "informal",
    "kanban",
    "lifecycle",
    "live",
    "mature",
    "model",
    "multi",
    "operation",
    "operational",
    "personal",
    "product",
    "queue",
    "recent",
    "resolved",
    "response",
    "review",
    "role",
    "shared",
    "signed",
    "solo",
    "static",
    "team",
    "technical",
    "ticket",
    "trail",
    "visibility",
    "whole",
    "work"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
