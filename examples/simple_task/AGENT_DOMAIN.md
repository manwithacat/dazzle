# Agent domain: Team Task Manager — Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

Team Task Manager is a task-tracking system for teams: work is captured as Tasks, assigned to Team Members, discussed in threaded comments, and moved through an explicit lifecycle from *todo* to *done*. Three roles use it — Administrators, Team Managers, and Team Members — each seeing exactly the work

**Source:** `examples/simple_task/SPECIFICATION.md`
**Fingerprint:** `a2cdc96dd942fc9d`

## Personas (jobs)

- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Member** (`member`, stable≈`member`, grounded) — desk `member_desk` — role word in founder brief
- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — role word in founder brief
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user

## Nouns (domain types)

- **Task** (grounded) owner≈`assigned_to` lifecycle: pending → assigned → in_progress → completed → blocked — definitional sentence in founder brief (A X is …)
- **TeamMember** (grounded) owner≈`assigned_to` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Comment** (grounded) owner≈`assigned_to` lifecycle: — — appears in founder brief (source=article_noun)

## Rejected chrome (not domain)

`Administrator`, `Dashboard`, `Data`, `Discussion`, `JavaScript`, `Metric`, `Tasks`, `Team`, `approval`, `auditable`, `board`, `built`, `creator`, `database`, `declared`, `effort`, `explicit`, `flat`, `framework`, `human`, `interrupted`, `live`, `mature`, `model`, `organisation`, `overdue`, `precise`, `priority`, `product`, `review`, `rhythm`, `technical`, `visibility`, `whole`, `work`

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

- `q1`: Can a task have multiple users, or just one?
- `q2`: Should users receive email/push notifications for key events?

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.

## Machine twin

```json
{
  "version": 1,
  "title": "Team Task Manager \u2014 Specification",
  "summary": "Team Task Manager is a task-tracking system for teams: work is captured as Tasks, assigned to Team Members, discussed in threaded comments, and moved through an explicit lifecycle from *todo* to *done*. Three roles use it \u2014 Administrators, Team Managers, and Team Members \u2014 each seeing exactly the work",
  "source_path": "examples/simple_task/SPECIFICATION.md",
  "source_sha256": "a2cdc96dd942fc9d",
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
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
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
      "name": "TeamMember",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "Comment",
      "status": "grounded",
      "evidence": "appears in founder brief (source=article_noun)",
      "lifecycle_hint": [],
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
      "text": "Can a task have multiple users, or just one?",
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
    "Administrator",
    "Dashboard",
    "Data",
    "Discussion",
    "JavaScript",
    "Metric",
    "Tasks",
    "Team",
    "approval",
    "auditable",
    "board",
    "built",
    "creator",
    "database",
    "declared",
    "effort",
    "explicit",
    "flat",
    "framework",
    "human",
    "interrupted",
    "live",
    "mature",
    "model",
    "organisation",
    "overdue",
    "precise",
    "priority",
    "product",
    "review",
    "rhythm",
    "technical",
    "visibility",
    "whole",
    "work"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
