# Agent domain: HR Records — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* HR Records is a personnel record system built around a simple idea: the facts about a person's career change over time, and the system should remember every

**Source:** `/Volumes/SSD/Dazzle/examples/hr_records/SPECIFICATION.md`
**Fingerprint:** `048d177d288d7ef2`

## Personas (jobs)

- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — role word in founder brief
- **Finance** (`finance`, stable≈`finance`, grounded) — desk `finance_desk` — role word in founder brief
- **Employee** (`employee`, stable≈`employee`, grounded) — desk `employee_desk` — role word in founder brief
- **Owner** (`owner`, stable≈`owner`, grounded) — desk `owner_desk` — Person who owns/creates primary content
- **Staff** (`staff`, stable≈`staff`, grounded) — desk `staff_desk` — Internal team member
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user
- **Member** (`member`, stable≈`member`, grounded) — desk `member_desk` — Registered community member

## Nouns (domain types)

- **Department** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Person** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Role** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)

## Rejected chrome (not domain)

`Beyond`, `Card`, `JavaScript`, `Link`, `Machine`, `ManagerLink`, `Metric`, `Team`, `Think`, `auditable`, `career`, `catalogued`, `clear`, `command`, `compensation`, `current`, `currently`, `data`, `detail`, `directory`, `effective`, `facts`, `formal`, `framework`, `idea`, `identity`, `line`, `live`, `mature`, `organisation`, `organisational`, `parent`, `period`, `personnel`, `present`, `product`, `report`, `review`, `rules`, `starter`, `technical`, `time`, `tree`, `visual`, `work`

## Desks

- **manager_desk** for `manager` (hypothesis) owner≈`owner` — Job desk for Manager
- **admin_desk** for `admin` (hypothesis) owner≈`owner` — Job desk for Admin
- **finance_desk** for `finance` (hypothesis) owner≈`owner` — Job desk for Finance
- **employee_desk** for `employee` (hypothesis) owner≈`owner` — Job desk for Employee
- **owner_desk** for `owner` (hypothesis) owner≈`owner` — Job desk for Owner
- **staff_desk** for `staff` (hypothesis) owner≈`owner` — Job desk for Staff
- **user_desk** for `user` (hypothesis) owner≈`owner` — Job desk for User
- **member_desk** for `member` (hypothesis) owner≈`owner` — Job desk for Member

## Demo spine (seed stories)

- `manager`: Manager has seeded Department rows for their desk (min_rows=1, entity≈Department)
- `admin`: Admin has seeded Department rows for their desk (min_rows=1, entity≈Department)
- `finance`: Finance has seeded Department rows for their desk (min_rows=1, entity≈Department)
- `employee`: Employee has seeded Department rows for their desk (min_rows=1, entity≈Department)
- `owner`: Owner has seeded Department rows for their desk (min_rows=1, entity≈Department)
- `staff`: Staff has seeded Department rows for their desk (min_rows=1, entity≈Department)
- `user`: User has seeded Department rows for their desk (min_rows=1, entity≈Department)
- `member`: Member has seeded Department rows for their desk (min_rows=1, entity≈Department)

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
  "title": "HR Records \u2014 System Specification",
  "summary": "*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* HR Records is a personnel record system built around a simple idea: the facts about a person's career change over time, and the system should remember every",
  "source_path": "/Volumes/SSD/Dazzle/examples/hr_records/SPECIFICATION.md",
  "source_sha256": "048d177d288d7ef2",
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
      "id_hint": "admin",
      "label": "Admin",
      "job": "",
      "desk": "admin_desk",
      "stable_id_candidate": "admin",
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
    },
    {
      "id_hint": "owner",
      "label": "Owner",
      "job": "Person who owns/creates primary content",
      "desk": "owner_desk",
      "stable_id_candidate": "owner",
      "status": "grounded",
      "evidence": "extract_personas + brief"
    },
    {
      "id_hint": "staff",
      "label": "Staff",
      "job": "Internal team member",
      "desk": "staff_desk",
      "stable_id_candidate": "staff",
      "status": "grounded",
      "evidence": "extract_personas + brief"
    },
    {
      "id_hint": "user",
      "label": "User",
      "job": "Generic system user",
      "desk": "user_desk",
      "stable_id_candidate": "user",
      "status": "grounded",
      "evidence": "extract_personas + brief"
    },
    {
      "id_hint": "member",
      "label": "Member",
      "job": "Registered community member",
      "desk": "member_desk",
      "stable_id_candidate": "member",
      "status": "grounded",
      "evidence": "extract_personas + brief"
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
      "persona": "admin",
      "name": "admin_desk",
      "purpose": "Job desk for Admin",
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
    },
    {
      "persona": "owner",
      "name": "owner_desk",
      "purpose": "Job desk for Owner",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    },
    {
      "persona": "staff",
      "name": "staff_desk",
      "purpose": "Job desk for Staff",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    },
    {
      "persona": "user",
      "name": "user_desk",
      "purpose": "Job desk for User",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    },
    {
      "persona": "member",
      "name": "member_desk",
      "purpose": "Job desk for Member",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    }
  ],
  "demo_spine": [
    {
      "persona": "manager",
      "story": "Manager has seeded Department rows for their desk",
      "min_rows": 1,
      "entity_hint": "Department"
    },
    {
      "persona": "admin",
      "story": "Admin has seeded Department rows for their desk",
      "min_rows": 1,
      "entity_hint": "Department"
    },
    {
      "persona": "finance",
      "story": "Finance has seeded Department rows for their desk",
      "min_rows": 1,
      "entity_hint": "Department"
    },
    {
      "persona": "employee",
      "story": "Employee has seeded Department rows for their desk",
      "min_rows": 1,
      "entity_hint": "Department"
    },
    {
      "persona": "owner",
      "story": "Owner has seeded Department rows for their desk",
      "min_rows": 1,
      "entity_hint": "Department"
    },
    {
      "persona": "staff",
      "story": "Staff has seeded Department rows for their desk",
      "min_rows": 1,
      "entity_hint": "Department"
    },
    {
      "persona": "user",
      "story": "User has seeded Department rows for their desk",
      "min_rows": 1,
      "entity_hint": "Department"
    },
    {
      "persona": "member",
      "story": "Member has seeded Department rows for their desk",
      "min_rows": 1,
      "entity_hint": "Department"
    }
  ],
  "open_questions": [],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL."
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
