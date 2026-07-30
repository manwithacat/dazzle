# Agent domain: HR Records — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* HR Records is a personnel record system built around a simple idea: the facts about a person's career change over time, and the system should remember every

**Source:** `/Volumes/SSD/Dazzle/examples/hr_records/SPECIFICATION.md`
**Fingerprint:** `d75851f836ec5327`

## Personas (jobs)

- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Finance** (`finance`, stable≈`finance`, grounded) — desk `finance_desk` — role word in founder brief
- **Employee** (`employee`, stable≈`employee`, grounded) — desk `employee_desk` — role word in founder brief

## Nouns (domain types)

- **Department** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Person** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Role** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)

## Rejected chrome (not domain)

`Beyond`, `Card`, `JavaScript`, `Link`, `Machine`, `ManagerLink`, `Metric`, `Team`, `Think`, `auditable`, `career`, `catalogued`, `clear`, `command`, `compensation`, `current`, `currently`, `data`, `detail`, `directory`, `effective`, `facts`, `formal`, `framework`, `idea`, `identity`, `line`, `live`, `mature`, `organisation`, `organisational`, `parent`, `period`, `personnel`, `present`, `product`, `report`, `review`, `rules`, `starter`, `technical`, `time`, `tree`, `visual`, `work`

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

- **escalation** (hypothesis) entity≈`Department` personas=[member, manager] — Department: worker escalates to manager when blocked or SLA risk
- **assignment** (hypothesis) entity≈`Department` personas=[manager, member] — Department: auto or manager assignment to a worker

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.
- process_candidates are hypotheses — author `process` blocks when multi-persona handoffs are real; do not invent decorative processes.

## Machine twin

```json
{
  "version": 1,
  "title": "HR Records \u2014 System Specification",
  "summary": "*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* HR Records is a personnel record system built around a simple idea: the facts about a person's career change over time, and the system should remember every",
  "source_path": "/Volumes/SSD/Dazzle/examples/hr_records/SPECIFICATION.md",
  "source_sha256": "d75851f836ec5327",
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
      "summary": "Department: worker escalates to manager when blocked or SLA risk",
      "personas": [
        "member",
        "manager"
      ],
      "entity_hint": "Department",
      "status": "hypothesis"
    },
    {
      "id_hint": "assignment",
      "summary": "Department: auto or manager assignment to a worker",
      "personas": [
        "manager",
        "member"
      ],
      "entity_hint": "Department",
      "status": "hypothesis"
    }
  ],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.",
    "process_candidates are hypotheses \u2014 author `process` blocks when multi-persona handoffs are real; do not invent decorative processes."
  ],
  "rejected_chrome": [
    "Beyond",
    "Card",
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
    "detail",
    "directory",
    "effective",
    "facts",
    "formal",
    "framework",
    "idea",
    "identity",
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
    "report",
    "review",
    "rules",
    "starter",
    "technical",
    "time",
    "tree",
    "visual",
    "work"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
