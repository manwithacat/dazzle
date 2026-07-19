# Agent domain: Team Task Manager - Product Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

> **Document Status**: Refined specification ready for DSL conversion > **Complexity Level**: Intermediate > **DSL Features Demonstrated**: Multi-entity relationships, personas, scenarios, access control, state machines A team task management tool that enables collaboration between administrators, managers, and team members. The app provides role-based dashboards, task assignment workflows, and pr

**Source:** `/Volumes/SSD/Dazzle/examples/simple_task/SPEC.md`
**Fingerprint:** `a08f9cf2587cb89c`

## Personas (jobs)

- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Member** (`member`, stable≈`member`, grounded) — desk `member_desk` — role word in founder brief
- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — role word in founder brief
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user

## Nouns (domain types)

- **Task** (grounded) owner≈`assigned_to` lifecycle: pending → assigned → in_progress → completed → blocked — appears in founder brief (source=capitalized_noun)
- **Taskcomment** (grounded) owner≈`assigned_to` lifecycle: pending → assigned → in_progress → completed → blocked — appears in founder brief (source=article_noun)

## Rejected chrome (not domain)

`Administrator`, `Completed`, `Control`, `Create`, `Declared`, `Demo`, `Development`, `Discrete`, `Implementation`, `Intention`, `Level`, `Lifecycle`, `List`, `Machine`, `Mix`, `Need`, `Organization`, `Pre`, `Progre`, `Require`, `Review`, `Right`, `Scenario`, `Several`, `Signal`, `Specific`, `State`, `Surface`, `Team`, `Test`, `Transition`, `Urgent`, `Variant`, `Variou`, `Work`, `Workload`

## Desks

- **manager_desk** for `manager` (hypothesis) owner≈`assigned_to` — Job desk for Manager
- **member_desk** for `member` (hypothesis) owner≈`assigned_to` — Job desk for Member
- **admin_desk** for `admin` (hypothesis) owner≈`assigned_to` — Job desk for Admin
- **user_desk** for `user` (hypothesis) owner≈`assigned_to` — Job desk for User

## Demo spine (seed stories)

- `manager`: Manager has seeded Task rows for their desk (min_rows=1, entity≈Task)
- `member`: Member has seeded Task rows for their desk (min_rows=1, entity≈Task)
- `admin`: Admin has seeded Task rows for their desk (min_rows=1, entity≈Task)
- `user`: User has seeded Task rows for their desk (min_rows=1, entity≈Task)

## Open questions

- `q1`: Can a task have multiple teams, or just one?
- `q2`: Can a task have multiple assignmentss, or just one?
- `q3`: Can a task have multiple tracks, or just one?
- `q4`: Can a member have multiple 7s, or just one?
- `q5`: Can a indicator have multiple overdues, or just one?
- `q6`: Can a progres have multiple workloads, or just one?

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.

## Machine twin

```json
{
  "version": 1,
  "title": "Team Task Manager - Product Specification",
  "summary": "> **Document Status**: Refined specification ready for DSL conversion > **Complexity Level**: Intermediate > **DSL Features Demonstrated**: Multi-entity relationships, personas, scenarios, access control, state machines A team task management tool that enables collaboration between administrators, managers, and team members. The app provides role-based dashboards, task assignment workflows, and pr",
  "source_path": "/Volumes/SSD/Dazzle/examples/simple_task/SPEC.md",
  "source_sha256": "a08f9cf2587cb89c",
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
      "id_hint": "member",
      "label": "Member",
      "job": "",
      "desk": "member_desk",
      "stable_id_candidate": "member",
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
      "name": "Task",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [
        "pending",
        "assigned",
        "in_progress",
        "completed",
        "blocked"
      ],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "Taskcomment",
      "status": "grounded",
      "evidence": "appears in founder brief (source=article_noun)",
      "lifecycle_hint": [
        "pending",
        "assigned",
        "in_progress",
        "completed",
        "blocked"
      ],
      "owner_field_hint": "assigned_to"
    }
  ],
  "desks": [
    {
      "persona": "manager",
      "name": "manager_desk",
      "purpose": "Job desk for Manager",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    },
    {
      "persona": "member",
      "name": "member_desk",
      "purpose": "Job desk for Member",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    },
    {
      "persona": "admin",
      "name": "admin_desk",
      "purpose": "Job desk for Admin",
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
      "persona": "manager",
      "story": "Manager has seeded Task rows for their desk",
      "min_rows": 1,
      "entity_hint": "Task"
    },
    {
      "persona": "member",
      "story": "Member has seeded Task rows for their desk",
      "min_rows": 1,
      "entity_hint": "Task"
    },
    {
      "persona": "admin",
      "story": "Admin has seeded Task rows for their desk",
      "min_rows": 1,
      "entity_hint": "Task"
    },
    {
      "persona": "user",
      "story": "User has seeded Task rows for their desk",
      "min_rows": 1,
      "entity_hint": "Task"
    }
  ],
  "open_questions": [
    {
      "id": "q1",
      "text": "Can a task have multiple teams, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q2",
      "text": "Can a task have multiple assignmentss, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q3",
      "text": "Can a task have multiple tracks, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q4",
      "text": "Can a member have multiple 7s, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q5",
      "text": "Can a indicator have multiple overdues, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q6",
      "text": "Can a progres have multiple workloads, or just one?",
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
    "Completed",
    "Control",
    "Create",
    "Declared",
    "Demo",
    "Development",
    "Discrete",
    "Implementation",
    "Intention",
    "Level",
    "Lifecycle",
    "List",
    "Machine",
    "Mix",
    "Need",
    "Organization",
    "Pre",
    "Progre",
    "Require",
    "Review",
    "Right",
    "Scenario",
    "Several",
    "Signal",
    "Specific",
    "State",
    "Surface",
    "Team",
    "Test",
    "Transition",
    "Urgent",
    "Variant",
    "Variou",
    "Work",
    "Workload"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
