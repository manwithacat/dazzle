# Agent domain: HR Records — Product Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

> **Document Status**: First-draft specification ready for DSL generation > **Complexity Level**: Intermediate (RBAC + temporal data) > **DSL Features Exercised**: state-machine-free entity lifecycle, effective-dated rows, current-row resolution, hierarchical traversal (department tree + manager chain), RBAC scope rules differentiating tenant-wide vs team-only vs self-only

**Source:** `/Volumes/SSD/Dazzle/examples/hr_records/SPEC.md`
**Fingerprint:** `22463473afd9375d`

## Personas (jobs)

- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — role word in founder brief
- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Finance** (`finance`, stable≈`finance`, grounded) — desk `finance_desk` — role word in founder brief
- **Employee** (`employee`, stable≈`employee`, grounded) — desk `employee_desk` — role word in founder brief
- **Engineer** (`engineer`, stable≈`engineer`, grounded) — desk `engineer_desk` — role word in founder brief
- **Staff** (`staff`, stable≈`staff`, grounded) — desk `staff_desk` — Internal team member
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user
- **Member** (`member`, stable≈`member`, grounded) — desk `member_desk` — Registered community member

## Nouns (domain types)

- **ManagerLink** (grounded) owner≈`person` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Phase** (grounded) owner≈`person` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Frontend** (grounded) owner≈`person` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Pattern** (grounded) owner≈`person` lifecycle: — — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Audit`, `Average`, `Backend`, `Benefit`, `Bonuse`, `Channel`, `Create`, `Dazzle`, `Engineer`, `Equity`, `Exercised`, `Filtered`, `Goal`, `Group`, `Invariant`, `Leave`, `Level`, `Multi`, `Non`, `Partner`, `Prediction`, `Python`, `Recent`, `Sale`, `Senior`, `Target`, `Think`, `Total`, `Two`, `bare`, `bespoke`, `candidate`, `canonical`, `career`, `catalogue`, `close`, `compare`, `current`, `date`, `department`, `desired`, `direct`, `directory`, `effective`, `firm`, `four`, `framework`, `hand`, `historical`, `identity`, `inverse`, `org`, `page`, `past`, `payroll`, `performance`, `person`, `personal`, `personnel`, `picker`, `promotion`, `report`, `role`, `runtime`, `salary`, `scope`, `starter`, `temporal`, `tree`, `unit`, `view`, `whole`

## Desks

- **admin_desk** for `admin` (hypothesis) owner≈`person` — Job desk for Admin
- **manager_desk** for `manager` (hypothesis) owner≈`person` — Job desk for Manager
- **finance_desk** for `finance` (hypothesis) owner≈`person` — Job desk for Finance
- **employee_desk** for `employee` (hypothesis) owner≈`person` — Job desk for Employee
- **engineer_desk** for `engineer` (hypothesis) owner≈`person` — Job desk for Engineer
- **staff_desk** for `staff` (hypothesis) owner≈`person` — Job desk for Staff
- **user_desk** for `user` (hypothesis) owner≈`person` — Job desk for User
- **member_desk** for `member` (hypothesis) owner≈`person` — Job desk for Member

## Demo spine (seed stories)

- `admin`: Admin has seeded ManagerLink rows for their desk (min_rows=1, entity≈ManagerLink)
- `manager`: Manager has seeded ManagerLink rows for their desk (min_rows=1, entity≈ManagerLink)
- `finance`: Finance has seeded ManagerLink rows for their desk (min_rows=1, entity≈ManagerLink)
- `employee`: Employee has seeded ManagerLink rows for their desk (min_rows=1, entity≈ManagerLink)
- `engineer`: Engineer has seeded ManagerLink rows for their desk (min_rows=1, entity≈ManagerLink)
- `staff`: Staff has seeded ManagerLink rows for their desk (min_rows=1, entity≈ManagerLink)
- `user`: User has seeded ManagerLink rows for their desk (min_rows=1, entity≈ManagerLink)
- `member`: Member has seeded ManagerLink rows for their desk (min_rows=1, entity≈ManagerLink)

## Open questions

- `q1`: Can a sale have multiple channels, or just one?
- `q2`: Can a org have multiple managers, or just one?
- `q5`: Can both parties leave reviews, or just one side?

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.

## Machine twin

```json
{
  "version": 1,
  "title": "HR Records \u2014 Product Specification",
  "summary": "> **Document Status**: First-draft specification ready for DSL generation > **Complexity Level**: Intermediate (RBAC + temporal data) > **DSL Features Exercised**: state-machine-free entity lifecycle, effective-dated rows, current-row resolution, hierarchical traversal (department tree + manager chain), RBAC scope rules differentiating tenant-wide vs team-only vs self-only",
  "source_path": "/Volumes/SSD/Dazzle/examples/hr_records/SPEC.md",
  "source_sha256": "22463473afd9375d",
  "personas": [
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
    },
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
      "name": "ManagerLink",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "person"
    },
    {
      "name": "Phase",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "person"
    },
    {
      "name": "Frontend",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "person"
    },
    {
      "name": "Pattern",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "person"
    }
  ],
  "desks": [
    {
      "persona": "admin",
      "name": "admin_desk",
      "purpose": "Job desk for Admin",
      "owner_field_hint": "person",
      "status": "hypothesis"
    },
    {
      "persona": "manager",
      "name": "manager_desk",
      "purpose": "Job desk for Manager",
      "owner_field_hint": "person",
      "status": "hypothesis"
    },
    {
      "persona": "finance",
      "name": "finance_desk",
      "purpose": "Job desk for Finance",
      "owner_field_hint": "person",
      "status": "hypothesis"
    },
    {
      "persona": "employee",
      "name": "employee_desk",
      "purpose": "Job desk for Employee",
      "owner_field_hint": "person",
      "status": "hypothesis"
    },
    {
      "persona": "engineer",
      "name": "engineer_desk",
      "purpose": "Job desk for Engineer",
      "owner_field_hint": "person",
      "status": "hypothesis"
    },
    {
      "persona": "staff",
      "name": "staff_desk",
      "purpose": "Job desk for Staff",
      "owner_field_hint": "person",
      "status": "hypothesis"
    },
    {
      "persona": "user",
      "name": "user_desk",
      "purpose": "Job desk for User",
      "owner_field_hint": "person",
      "status": "hypothesis"
    },
    {
      "persona": "member",
      "name": "member_desk",
      "purpose": "Job desk for Member",
      "owner_field_hint": "person",
      "status": "hypothesis"
    }
  ],
  "demo_spine": [
    {
      "persona": "admin",
      "story": "Admin has seeded ManagerLink rows for their desk",
      "min_rows": 1,
      "entity_hint": "ManagerLink"
    },
    {
      "persona": "manager",
      "story": "Manager has seeded ManagerLink rows for their desk",
      "min_rows": 1,
      "entity_hint": "ManagerLink"
    },
    {
      "persona": "finance",
      "story": "Finance has seeded ManagerLink rows for their desk",
      "min_rows": 1,
      "entity_hint": "ManagerLink"
    },
    {
      "persona": "employee",
      "story": "Employee has seeded ManagerLink rows for their desk",
      "min_rows": 1,
      "entity_hint": "ManagerLink"
    },
    {
      "persona": "engineer",
      "story": "Engineer has seeded ManagerLink rows for their desk",
      "min_rows": 1,
      "entity_hint": "ManagerLink"
    },
    {
      "persona": "staff",
      "story": "Staff has seeded ManagerLink rows for their desk",
      "min_rows": 1,
      "entity_hint": "ManagerLink"
    },
    {
      "persona": "user",
      "story": "User has seeded ManagerLink rows for their desk",
      "min_rows": 1,
      "entity_hint": "ManagerLink"
    },
    {
      "persona": "member",
      "story": "Member has seeded ManagerLink rows for their desk",
      "min_rows": 1,
      "entity_hint": "ManagerLink"
    }
  ],
  "open_questions": [
    {
      "id": "q1",
      "text": "Can a sale have multiple channels, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q2",
      "text": "Can a org have multiple managers, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q5",
      "text": "Can both parties leave reviews, or just one side?",
      "blocks_promote": false
    }
  ],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL."
  ],
  "rejected_chrome": [
    "Audit",
    "Average",
    "Backend",
    "Benefit",
    "Bonuse",
    "Channel",
    "Create",
    "Dazzle",
    "Engineer",
    "Equity",
    "Exercised",
    "Filtered",
    "Goal",
    "Group",
    "Invariant",
    "Leave",
    "Level",
    "Multi",
    "Non",
    "Partner",
    "Prediction",
    "Python",
    "Recent",
    "Sale",
    "Senior",
    "Target",
    "Think",
    "Total",
    "Two",
    "bare",
    "bespoke",
    "candidate",
    "canonical",
    "career",
    "catalogue",
    "close",
    "compare",
    "current",
    "date",
    "department",
    "desired",
    "direct",
    "directory",
    "effective",
    "firm",
    "four",
    "framework",
    "hand",
    "historical",
    "identity",
    "inverse",
    "org",
    "page",
    "past",
    "payroll",
    "performance",
    "person",
    "personal",
    "personnel",
    "picker",
    "promotion",
    "report",
    "role",
    "runtime",
    "salary",
    "scope",
    "starter",
    "temporal",
    "tree",
    "unit",
    "view",
    "whole"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
