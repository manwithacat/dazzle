# Agent domain: Support Tickets — Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

Support Tickets is a customer-support system that tracks customer issues from first report to resolution, with response-time awareness built in. Customers submit and follow their own tickets; Support Agents work a shared queue; Support Managers watch team performance and handle escalations; an

**Source:** `examples/support_tickets/SPECIFICATION.md`
**Fingerprint:** `b6a4daae03f88387`

## Personas (jobs)

- **Agent** (`agent`, stable≈`agent`, grounded) — desk `agent_desk` — role word in founder brief
- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Customer** (`customer`, stable≈`customer`, grounded) — desk `customer_desk` — role word in founder brief
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user

## Nouns (domain types)

- **SupportTicket** (grounded) owner≈`assigned_to` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Comment** (grounded) owner≈`assigned_to` lifecycle: — — appears in founder brief (source=comma_list)

## Rejected chrome (not domain)

`Administrator`, `Agent`, `Approval`, `Close`, `Console`, `Dashboard`, `JavaScript`, `Op`, `Support`, `Tickets`, `Waiver`, `associated`, `auditable`, `authenticated`, `breach`, `byte`, `change`, `chosen`, `critical`, `data`, `datastore`, `declared`, `framework`, `informal`, `kanban`, `lifecycle`, `live`, `mature`, `model`, `operation`, `operational`, `personal`, `product`, `queue`, `response`, `review`, `shared`, `signed`, `solo`, `static`, `team`, `technical`, `ticket`, `visibility`, `whole`, `work`

## Desks

- **agent_desk** for `agent` (hypothesis) owner≈`assigned_to` — Job desk for Agent
- **manager_desk** for `manager` (hypothesis) owner≈`assigned_to` — Job desk for Manager
- **customer_desk** for `customer` (hypothesis) owner≈`assigned_to` — Job desk for Customer
- **user_desk** for `user` (hypothesis) owner≈`assigned_to` — Job desk for User

## Demo spine (seed stories)

- `agent`: Agent has seeded SupportTicket rows for their desk (min_rows=1, entity≈SupportTicket)
- `manager`: Manager has seeded SupportTicket rows for their desk (min_rows=1, entity≈SupportTicket)
- `customer`: Customer has seeded SupportTicket rows for their desk (min_rows=1, entity≈SupportTicket)
- `user`: User has seeded SupportTicket rows for their desk (min_rows=1, entity≈SupportTicket)

## Open questions

- `q1`: Can a ticket have multiple comments, or just one?

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.

## Machine twin

```json
{
  "version": 1,
  "title": "Support Tickets \u2014 Specification",
  "summary": "Support Tickets is a customer-support system that tracks customer issues from first report to resolution, with response-time awareness built in. Customers submit and follow their own tickets; Support Agents work a shared queue; Support Managers watch team performance and handle escalations; an",
  "source_path": "examples/support_tickets/SPECIFICATION.md",
  "source_sha256": "b6a4daae03f88387",
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
      "id_hint": "user",
      "label": "User",
      "job": "Generic system user",
      "desk": "user_desk",
      "stable_id_candidate": "user",
      "status": "grounded",
      "evidence": "extract_personas + brief"
    }
  ],
  "nouns": [
    {
      "name": "SupportTicket",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
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
      "persona": "user",
      "name": "user_desk",
      "purpose": "Job desk for User",
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
      "persona": "user",
      "story": "User has seeded SupportTicket rows for their desk",
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
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL."
  ],
  "rejected_chrome": [
    "Administrator",
    "Agent",
    "Approval",
    "Close",
    "Console",
    "Dashboard",
    "JavaScript",
    "Op",
    "Support",
    "Tickets",
    "Waiver",
    "associated",
    "auditable",
    "authenticated",
    "breach",
    "byte",
    "change",
    "chosen",
    "critical",
    "data",
    "datastore",
    "declared",
    "framework",
    "informal",
    "kanban",
    "lifecycle",
    "live",
    "mature",
    "model",
    "operation",
    "operational",
    "personal",
    "product",
    "queue",
    "response",
    "review",
    "shared",
    "signed",
    "solo",
    "static",
    "team",
    "technical",
    "ticket",
    "visibility",
    "whole",
    "work"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
