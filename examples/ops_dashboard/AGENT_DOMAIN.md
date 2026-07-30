# Agent domain: Operations Dashboard — Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

Operations Dashboard is a real-time monitoring and incident-response product. It tracks the operational health of backend services — each monitored System moves through healthy, degraded, critical, and offline states — and records every time-bound incident as an Alert against the System it occurred on, until an engineer acknowledges it. A PagerDuty integration connects the product to the team's ex

**Source:** `/Volumes/SSD/Dazzle/examples/ops_dashboard/SPECIFICATION.md`
**Fingerprint:** `8a77505fed77df08`

## Personas (jobs)

- **Engineer** (`engineer`, stable≈`engineer`, grounded) — desk `engineer_desk` — role word in founder brief

## Nouns (domain types)

- **Alert** (grounded) owner≈`acknowledged_by` lifecycle: active → acknowledged → resolved — definitional sentence in founder brief (A X is …)
- **Integration** (grounded) owner≈`acknowledged_by` lifecycle: off → pending → live → revoked — definitional sentence in founder brief (A X is …)

## Rejected chrome (not domain)

`Administrator`, `Center`, `Command`, `Data`, `Dazzle`, `JavaScript`, `Operations`, `PagerDuty`, `System`, `auditable`, `backend`, `cohort`, `comparison`, `confirm`, `create`, `cross`, `degraded`, `detail`, `engineer`, `glance`, `guided`, `healthy`, `heatmap`, `incident`, `insight`, `journey`, `kanban`, `live`, `mature`, `monitored`, `operation`, `operational`, `product`, `real`, `representative`, `responder`, `response`, `review`, `rich`, `rule`, `severity`, `step`, `team`, `technical`

## Desks

- **engineer_desk** for `engineer` (hypothesis) owner≈`acknowledged_by` — Job desk for Engineer

## Demo spine (seed stories)

- `engineer`: Engineer has seeded Alert rows for their desk (min_rows=1, entity≈Alert)

## Open questions

_None blocking._

## Process candidates (hypothesis)

- **escalation** (hypothesis) entity≈`Alert` personas=[member, manager] — Alert: worker escalates to manager when blocked or SLA risk
- **assignment** (hypothesis) entity≈`Alert` personas=[manager, member] — Alert: auto or manager assignment to a worker
- **triage** (hypothesis) entity≈`Alert` personas=[agent, engineer] — Alert: intake triage before deep work

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.
- process_candidates are hypotheses — author `process` blocks when multi-persona handoffs are real; do not invent decorative processes.
- 2 noun(s) carry lifecycle_hint — emit transitions: (and lifecycle: evidence when product requires ADR-0020).

## Machine twin

```json
{
  "version": 1,
  "title": "Operations Dashboard \u2014 Specification",
  "summary": "Operations Dashboard is a real-time monitoring and incident-response product. It tracks the operational health of backend services \u2014 each monitored System moves through healthy, degraded, critical, and offline states \u2014 and records every time-bound incident as an Alert against the System it occurred on, until an engineer acknowledges it. A PagerDuty integration connects the product to the team's ex",
  "source_path": "/Volumes/SSD/Dazzle/examples/ops_dashboard/SPECIFICATION.md",
  "source_sha256": "8a77505fed77df08",
  "personas": [
    {
      "id_hint": "engineer",
      "label": "Engineer",
      "job": "",
      "desk": "engineer_desk",
      "stable_id_candidate": "engineer",
      "status": "grounded",
      "evidence": "role word in founder brief"
    }
  ],
  "nouns": [
    {
      "name": "Alert",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [
        "active",
        "acknowledged",
        "resolved"
      ],
      "owner_field_hint": "acknowledged_by"
    },
    {
      "name": "Integration",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [
        "off",
        "pending",
        "live",
        "revoked"
      ],
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
    }
  ],
  "demo_spine": [
    {
      "persona": "engineer",
      "story": "Engineer has seeded Alert rows for their desk",
      "min_rows": 1,
      "entity_hint": "Alert"
    }
  ],
  "open_questions": [],
  "process_candidates": [
    {
      "id_hint": "escalation",
      "summary": "Alert: worker escalates to manager when blocked or SLA risk",
      "personas": [
        "member",
        "manager"
      ],
      "entity_hint": "Alert",
      "status": "hypothesis"
    },
    {
      "id_hint": "assignment",
      "summary": "Alert: auto or manager assignment to a worker",
      "personas": [
        "manager",
        "member"
      ],
      "entity_hint": "Alert",
      "status": "hypothesis"
    },
    {
      "id_hint": "triage",
      "summary": "Alert: intake triage before deep work",
      "personas": [
        "agent",
        "engineer"
      ],
      "entity_hint": "Alert",
      "status": "hypothesis"
    }
  ],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.",
    "process_candidates are hypotheses \u2014 author `process` blocks when multi-persona handoffs are real; do not invent decorative processes.",
    "2 noun(s) carry lifecycle_hint \u2014 emit transitions: (and lifecycle: evidence when product requires ADR-0020)."
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
    "severity",
    "step",
    "team",
    "technical"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
