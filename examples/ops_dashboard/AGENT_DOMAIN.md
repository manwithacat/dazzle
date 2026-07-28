# Agent domain: Operations Dashboard - Product Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

> **Document Status**: Refined specification ready for DSL conversion > **Complexity Level**: Intermediate+ > **DSL Features Demonstrated**: Personas, COMMAND_CENTER archetype, engine hints, aggregations A real-time operations monitoring dashboard for DevOps and SRE teams. The command center interface enables engineers to monitor system health, respond to alerts, and maintain situational awareness

**Source:** `/Volumes/SSD/Dazzle/examples/ops_dashboard/SPEC.md`
**Fingerprint:** `6c84f84c239ec519`

## Personas (jobs)

- **Engineer** (`engineer`, stable≈`engineer`, grounded) — desk `engineer_desk` — role word in founder brief
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user

## Nouns (domain types)

- **Criteria** (grounded) owner≈`acknowledged_by` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Style** (grounded) owner≈`acknowledged_by` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Quick** (grounded) owner≈`acknowledged_by` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Persona** (grounded) owner≈`acknowledged_by` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **WebSocket** (grounded) owner≈`acknowledged_by` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Acceptance** (grounded) owner≈`acknowledged_by` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Alert** (grounded) owner≈`acknowledged_by` lifecycle: — — appears in founder brief (source=article_noun)

## Rejected chrome (not domain)

`Aggregation`, `Auto`, `Average`, `Color`, `DevOp`, `Explicit`, `External`, `Flow`, `Hint`, `Level`, `Live`, `Mobile`, `Multi`, `Operation`, `Point`, `Related`, `Review`, `Runbook`, `Unacknowledged`, `archetype`, `bare`, `click`, `command`, `dense`, `glance`, `health`, `healthy`, `high`, `implementation`, `incident`, `keyboard`, `monitored`, `real`, `response`, `sorted`, `specific`, `system`, `total`

## Desks

- **engineer_desk** for `engineer` (hypothesis) owner≈`acknowledged_by` — Job desk for Engineer
- **user_desk** for `user` (hypothesis) owner≈`acknowledged_by` — Job desk for User

## Demo spine (seed stories)

- `engineer`: Engineer has seeded Criteria rows for their desk (min_rows=1, entity≈Criteria)
- `user`: User has seeded Criteria rows for their desk (min_rows=1, entity≈Criteria)

## Open questions

- `q1`: Can a system have multiple alerts, or just one?
- `q2`: Should users receive email/push notifications for key events?

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.

## Machine twin

```json
{
  "version": 1,
  "title": "Operations Dashboard - Product Specification",
  "summary": "> **Document Status**: Refined specification ready for DSL conversion > **Complexity Level**: Intermediate+ > **DSL Features Demonstrated**: Personas, COMMAND_CENTER archetype, engine hints, aggregations A real-time operations monitoring dashboard for DevOps and SRE teams. The command center interface enables engineers to monitor system health, respond to alerts, and maintain situational awareness",
  "source_path": "/Volumes/SSD/Dazzle/examples/ops_dashboard/SPEC.md",
  "source_sha256": "6c84f84c239ec519",
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
      "name": "Criteria",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "acknowledged_by"
    },
    {
      "name": "Style",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "acknowledged_by"
    },
    {
      "name": "Quick",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "acknowledged_by"
    },
    {
      "name": "Persona",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "acknowledged_by"
    },
    {
      "name": "WebSocket",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "acknowledged_by"
    },
    {
      "name": "Acceptance",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "acknowledged_by"
    },
    {
      "name": "Alert",
      "status": "grounded",
      "evidence": "appears in founder brief (source=article_noun)",
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
      "story": "Engineer has seeded Criteria rows for their desk",
      "min_rows": 1,
      "entity_hint": "Criteria"
    },
    {
      "persona": "user",
      "story": "User has seeded Criteria rows for their desk",
      "min_rows": 1,
      "entity_hint": "Criteria"
    }
  ],
  "open_questions": [
    {
      "id": "q1",
      "text": "Can a system have multiple alerts, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q2",
      "text": "Should users receive email/push notifications for key events?",
      "blocks_promote": false
    }
  ],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL."
  ],
  "rejected_chrome": [
    "Aggregation",
    "Auto",
    "Average",
    "Color",
    "DevOp",
    "Explicit",
    "External",
    "Flow",
    "Hint",
    "Level",
    "Live",
    "Mobile",
    "Multi",
    "Operation",
    "Point",
    "Related",
    "Review",
    "Runbook",
    "Unacknowledged",
    "archetype",
    "bare",
    "click",
    "command",
    "dense",
    "glance",
    "health",
    "healthy",
    "high",
    "implementation",
    "incident",
    "keyboard",
    "monitored",
    "real",
    "response",
    "sorted",
    "specific",
    "system",
    "total"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
