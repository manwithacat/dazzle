# Agent domain: HR Records — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* HR Records is a personnel record system built around a simple idea: the facts about a person's career change over time, and the system should remember every

**Source:** `/Volumes/SSD/Dazzle/examples/hr_records/SPECIFICATION.md`
**Fingerprint:** `013e5961f1553c90`

## Personas (jobs)

- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Finance** (`finance`, stable≈`finance`, grounded) — desk `finance_desk` — role word in founder brief
- **Employee** (`employee`, stable≈`employee`, grounded) — desk `employee_desk` — role word in founder brief

## Nouns (domain types)

- **Department** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Person** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Role** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **PersonNote** (grounded) owner≈`owner` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Employment** (grounded) owner≈`owner` lifecycle: active → on_leave → terminated — appears in founder brief (source=article_noun)

## Rejected chrome (not domain)

`Beyond`, `Desk`, `Directory`, `Email`, `JavaScript`, `Link`, `Machine`, `ManagerLink`, `Metric`, `Team`, `Think`, `auditable`, `career`, `catalogued`, `clear`, `command`, `compensation`, `current`, `currently`, `data`, `dept`, `document`, `effective`, `facts`, `formal`, `framework`, `idea`, `identity`, `informal`, `line`, `live`, `mature`, `organisation`, `organisational`, `parent`, `period`, `personnel`, `present`, `product`, `record`, `report`, `review`, `rules`, `starter`, `technical`, `time`, `tree`, `work`

## Desks

- **manager_desk** for `manager` (hypothesis) owner≈`owner` — Job desk for Manager
- **finance_desk** for `finance` (hypothesis) owner≈`owner` — Job desk for Finance
- **employee_desk** for `employee` (hypothesis) owner≈`owner` — Job desk for Employee

## Demo spine (seed stories)

- `manager`: Manager has seeded Person rows for their desk (min_rows=1, entity≈Person)
- `finance`: Finance has seeded Person rows for their desk (min_rows=1, entity≈Person)
- `employee`: Employee has seeded Person rows for their desk (min_rows=1, entity≈Person)

## Open questions

_None blocking._

## Process candidates (hypothesis)

- **escalation** (hypothesis) entity≈`Employment` personas=[member, manager] — Employment: worker escalates to manager when blocked or SLA risk
- **assignment** (hypothesis) entity≈`Employment` personas=[manager, member] — Employment: auto or manager assignment to a worker

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
  "title": "HR Records \u2014 System Specification",
  "summary": "*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* HR Records is a personnel record system built around a simple idea: the facts about a person's career change over time, and the system should remember every",
  "source_path": "/Volumes/SSD/Dazzle/examples/hr_records/SPECIFICATION.md",
  "source_sha256": "013e5961f1553c90",
  "personas": [
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
      "id_hint": "finance",
      "label": "Finance",
      "job": "",
      "desk": "finance_desk",
      "stable_id_candidate": "finance",
      "status": "grounded",
      "evidence": "role word in founder brief"
    },
    {
      "id_hint": "employee",
      "label": "Employee",
      "job": "",
      "desk": "employee_desk",
      "stable_id_candidate": "employee",
      "status": "grounded",
      "evidence": "role word in founder brief"
    }
  ],
  "nouns": [
    {
      "name": "Department",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "Person",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "Role",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "PersonNote",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "Employment",
      "status": "grounded",
      "evidence": "appears in founder brief (source=article_noun)",
      "lifecycle_hint": [
        "active",
        "on_leave",
        "terminated"
      ],
      "owner_field_hint": "owner"
    }
  ],
  "desks": [
    {
      "persona": "manager",
      "name": "manager_desk",
      "purpose": "Job desk for Manager",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    },
    {
      "persona": "finance",
      "name": "finance_desk",
      "purpose": "Job desk for Finance",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    },
    {
      "persona": "employee",
      "name": "employee_desk",
      "purpose": "Job desk for Employee",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    }
  ],
  "demo_spine": [
    {
      "persona": "manager",
      "story": "Manager has seeded Person rows for their desk",
      "min_rows": 1,
      "entity_hint": "Person"
    },
    {
      "persona": "finance",
      "story": "Finance has seeded Person rows for their desk",
      "min_rows": 1,
      "entity_hint": "Person"
    },
    {
      "persona": "employee",
      "story": "Employee has seeded Person rows for their desk",
      "min_rows": 1,
      "entity_hint": "Person"
    }
  ],
  "open_questions": [],
  "process_candidates": [
    {
      "id_hint": "escalation",
      "summary": "Employment: worker escalates to manager when blocked or SLA risk",
      "personas": [
        "member",
        "manager"
      ],
      "entity_hint": "Employment",
      "status": "hypothesis"
    },
    {
      "id_hint": "assignment",
      "summary": "Employment: auto or manager assignment to a worker",
      "personas": [
        "manager",
        "member"
      ],
      "entity_hint": "Employment",
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
    "Beyond",
    "Desk",
    "Directory",
    "Email",
    "JavaScript",
    "Link",
    "Machine",
    "ManagerLink",
    "Metric",
    "Team",
    "Think",
    "auditable",
    "career",
    "catalogued",
    "clear",
    "command",
    "compensation",
    "current",
    "currently",
    "data",
    "dept",
    "document",
    "effective",
    "facts",
    "formal",
    "framework",
    "idea",
    "identity",
    "informal",
    "line",
    "live",
    "mature",
    "organisation",
    "organisational",
    "parent",
    "period",
    "personnel",
    "present",
    "product",
    "record",
    "report",
    "review",
    "rules",
    "starter",
    "technical",
    "time",
    "tree",
    "work"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
