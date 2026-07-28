# Agent domain: Support Ticket Classifier — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* The Support Ticket Classifier is a support-operations system that pairs a human support team with declared, AI-assisted analysis. It manages support tickets,

**Source:** `/Volumes/SSD/Dazzle/examples/llm_ticket_classifier/SPECIFICATION.md`
**Fingerprint:** `3b8fb00022056a7f`

## Personas (jobs)

- **Agent** (`agent`, stable≈`agent`, grounded) — desk `agent_desk` — role word in founder brief
- **Customer** (`customer`, stable≈`customer`, grounded) — desk `customer_desk` — role word in founder brief
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user

## Nouns (domain types)

- **SupportTicket** (grounded) owner≈`assigned_to` lifecycle: — — definitional sentence in founder brief (A X is …)
- **TicketClassification** (grounded) owner≈`—` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Ticket** (grounded) owner≈`assigned_to` lifecycle: open → in_progress → resolved → closed → reopened — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Agent`, `Beyond`, `Dashboard`, `Data`, `Four`, `JavaScript`, `Readines`, `Result`, `Supervisor`, `Support`, `Their`, `administrative`, `auditable`, `classification`, `command`, `confidence`, `declared`, `explicit`, `framework`, `human`, `inventory`, `lifecycle`, `live`, `mature`, `model`, `parent`, `priority`, `product`, `record`, `related`, `response`, `specific`, `suggested`, `team`, `technical`, `work`

## Desks

- **agent_desk** for `agent` (hypothesis) owner≈`assigned_to` — Job desk for Agent
- **customer_desk** for `customer` (hypothesis) owner≈`assigned_to` — Job desk for Customer
- **user_desk** for `user` (hypothesis) owner≈`assigned_to` — Job desk for User

## Demo spine (seed stories)

- `agent`: Agent has seeded SupportTicket rows for their desk (min_rows=1, entity≈SupportTicket)
- `customer`: Customer has seeded SupportTicket rows for their desk (min_rows=1, entity≈SupportTicket)
- `user`: User has seeded SupportTicket rows for their desk (min_rows=1, entity≈SupportTicket)

## Open questions

_None blocking._

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.

## Machine twin

```json
{
  "version": 1,
  "title": "Support Ticket Classifier \u2014 System Specification",
  "summary": "*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* The Support Ticket Classifier is a support-operations system that pairs a human support team with declared, AI-assisted analysis. It manages support tickets,",
  "source_path": "/Volumes/SSD/Dazzle/examples/llm_ticket_classifier/SPECIFICATION.md",
  "source_sha256": "3b8fb00022056a7f",
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
      "name": "TicketClassification",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": null
    },
    {
      "name": "Ticket",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [
        "open",
        "in_progress",
        "resolved",
        "closed",
        "reopened"
      ],
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
  "open_questions": [],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL."
  ],
  "rejected_chrome": [
    "Agent",
    "Beyond",
    "Dashboard",
    "Data",
    "Four",
    "JavaScript",
    "Readines",
    "Result",
    "Supervisor",
    "Support",
    "Their",
    "administrative",
    "auditable",
    "classification",
    "command",
    "confidence",
    "declared",
    "explicit",
    "framework",
    "human",
    "inventory",
    "lifecycle",
    "live",
    "mature",
    "model",
    "parent",
    "priority",
    "product",
    "record",
    "related",
    "response",
    "specific",
    "suggested",
    "team",
    "technical",
    "work"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
