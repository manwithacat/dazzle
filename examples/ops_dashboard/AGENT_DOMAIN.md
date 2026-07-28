# Agent domain: Operations Dashboard — Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

Operations Dashboard is a real-time monitoring and incident-response product. It tracks the operational health of backend services — each monitored System moves through healthy, degraded, critical, and offline states — and records every time-bound incident as an Alert against the System it occurred on, until an engineer acknowledges it. A PagerDuty integration connects the product to the team's ex

**Source:** `examples/ops_dashboard/SPECIFICATION.md`
**Fingerprint:** `1bf315204ea846ce`

## Personas (jobs)

- **Engineer** (`engineer`, stable≈`engineer`, grounded) — desk `engineer_desk` — role word in founder brief
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user

## Nouns (domain types)

- **Alert** (grounded) owner≈`acknowledged_by` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Integration** (grounded) owner≈`acknowledged_by` lifecycle: — — definitional sentence in founder brief (A X is …)

## Rejected chrome (not domain)

`Administrator`, `Center`, `Command`, `Data`, `Dazzle`, `JavaScript`, `Operations`, `PagerDuty`, `System`, `auditable`, `backend`, `cohort`, `comparison`, `confirm`, `create`, `cross`, `degraded`, `detail`, `engineer`, `glance`, `guided`, `healthy`, `heatmap`, `incident`, `insight`, `journey`, `kanban`, `live`, `mature`, `monitored`, `operation`, `operational`, `product`, `real`, `representative`, `responder`, `response`, `review`, `rich`, `rule`, `step`, `team`, `technical`

## Desks

- **engineer_desk** for `engineer` (hypothesis) owner≈`acknowledged_by` — Job desk for Engineer
- **user_desk** for `user` (hypothesis) owner≈`acknowledged_by` — Job desk for User

## Demo spine (seed stories)

- `engineer`: Engineer has seeded Alert rows for their desk (min_rows=1, entity≈Alert)
- `user`: User has seeded Alert rows for their desk (min_rows=1, entity≈Alert)

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
  "title": "Operations Dashboard \u2014 Specification",
  "summary": "Operations Dashboard is a real-time monitoring and incident-response product. It tracks the operational health of backend services \u2014 each monitored System moves through healthy, degraded, critical, and offline states \u2014 and records every time-bound incident as an Alert against the System it occurred on, until an engineer acknowledges it. A PagerDuty integration connects the product to the team's ex",
  "source_path": "examples/ops_dashboard/SPECIFICATION.md",
  "source_sha256": "1bf315204ea846ce",
  "personas": [
    {
      "id_hint": "engineer",
      "label": "Engineer",
      "job": "",
      "desk": "engineer_desk",
      "stable_id_candidate": "engineer",
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
      "name": "Alert",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "acknowledged_by"
    },
    {
      "name": "Integration",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "acknowledged_by"
    }
  ],
  "desks": [
    {
      "persona": "engineer",
      "name": "engineer_desk",
      "purpose": "Job desk for Engineer",
      "owner_field_hint": "acknowledged_by",
      "status": "hypothesis"
    },
    {
      "persona": "user",
      "name": "user_desk",
      "purpose": "Job desk for User",
      "owner_field_hint": "acknowledged_by",
      "status": "hypothesis"
    }
  ],
  "demo_spine": [
    {
      "persona": "engineer",
      "story": "Engineer has seeded Alert rows for their desk",
      "min_rows": 1,
      "entity_hint": "Alert"
    },
    {
      "persona": "user",
      "story": "User has seeded Alert rows for their desk",
      "min_rows": 1,
      "entity_hint": "Alert"
    }
  ],
  "open_questions": [],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL."
  ],
  "rejected_chrome": [
    "Administrator",
    "Center",
    "Command",
    "Data",
    "Dazzle",
    "JavaScript",
    "Operations",
    "PagerDuty",
    "System",
    "auditable",
    "backend",
    "cohort",
    "comparison",
    "confirm",
    "create",
    "cross",
    "degraded",
    "detail",
    "engineer",
    "glance",
    "guided",
    "healthy",
    "heatmap",
    "incident",
    "insight",
    "journey",
    "kanban",
    "live",
    "mature",
    "monitored",
    "operation",
    "operational",
    "product",
    "real",
    "representative",
    "responder",
    "response",
    "review",
    "rich",
    "rule",
    "step",
    "team",
    "technical"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
