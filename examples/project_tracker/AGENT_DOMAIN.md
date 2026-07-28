# Agent domain: Project Tracker — Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

Project Tracker is a team project-management product. It organises work as Projects owned by a team member, broken into Milestones and Tasks, with Comments and Attachments carrying the conversation and the evidence alongside each task. Everyone on the team shares two working surfaces — a Dashboard for the overview and a Project Board for day-to-day task and milestone management.

**Source:** `examples/project_tracker/SPECIFICATION.md`
**Fingerprint:** `336597f66186a6ca`

## Personas (jobs)

- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — role word in founder brief
- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Member** (`member`, stable≈`member`, grounded) — desk `member_desk` — role word in founder brief
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user

## Nouns (domain types)

- **Attachment** (grounded) owner≈`owner` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Project** (grounded) owner≈`owner` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Comment** (grounded) owner≈`owner` lifecycle: — — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Board`, `Dashboard`, `Data`, `Dazzle`, `JavaScript`, `Plan`, `Tasks`, `assignee`, `auditable`, `author`, `built`, `byte`, `command`, `declared`, `discussion`, `evidence`, `five`, `kanban`, `larger`, `live`, `mature`, `milestone`, `parent`, `people`, `product`, `signed`, `static`, `task`, `team`, `technical`

## Desks

- **admin_desk** for `admin` (hypothesis) owner≈`owner` — Job desk for Admin
- **manager_desk** for `manager` (hypothesis) owner≈`owner` — Job desk for Manager
- **member_desk** for `member` (hypothesis) owner≈`owner` — Job desk for Member
- **user_desk** for `user` (hypothesis) owner≈`owner` — Job desk for User

## Demo spine (seed stories)

- `admin`: Admin has seeded Attachment rows for their desk (min_rows=1, entity≈Attachment)
- `manager`: Manager has seeded Attachment rows for their desk (min_rows=1, entity≈Attachment)
- `member`: Member has seeded Attachment rows for their desk (min_rows=1, entity≈Attachment)
- `user`: User has seeded Attachment rows for their desk (min_rows=1, entity≈Attachment)

## Open questions

- `q1`: Can a milestone have multiple tasks, or just one?
- `q2`: Can a comment have multiple attachments, or just one?
- `q3`: Can a project have multiple tasks, or just one?
- `q4`: Can a milestone have multiple comments, or just one?
- `q5`: Can a project have multiple milestones, or just one?
- `q6`: Can a task have multiple attachments, or just one?

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.

## Machine twin

```json
{
  "version": 1,
  "title": "Project Tracker \u2014 Specification",
  "summary": "Project Tracker is a team project-management product. It organises work as Projects owned by a team member, broken into Milestones and Tasks, with Comments and Attachments carrying the conversation and the evidence alongside each task. Everyone on the team shares two working surfaces \u2014 a Dashboard for the overview and a Project Board for day-to-day task and milestone management.",
  "source_path": "examples/project_tracker/SPECIFICATION.md",
  "source_sha256": "336597f66186a6ca",
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
      "id_hint": "member",
      "label": "Member",
      "job": "",
      "desk": "member_desk",
      "stable_id_candidate": "member",
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
      "name": "Attachment",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "Project",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "Comment",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    }
  ],
  "desks": [
    {
      "persona": "admin",
      "name": "admin_desk",
      "purpose": "Job desk for Admin",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    },
    {
      "persona": "manager",
      "name": "manager_desk",
      "purpose": "Job desk for Manager",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    },
    {
      "persona": "member",
      "name": "member_desk",
      "purpose": "Job desk for Member",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    },
    {
      "persona": "user",
      "name": "user_desk",
      "purpose": "Job desk for User",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    }
  ],
  "demo_spine": [
    {
      "persona": "admin",
      "story": "Admin has seeded Attachment rows for their desk",
      "min_rows": 1,
      "entity_hint": "Attachment"
    },
    {
      "persona": "manager",
      "story": "Manager has seeded Attachment rows for their desk",
      "min_rows": 1,
      "entity_hint": "Attachment"
    },
    {
      "persona": "member",
      "story": "Member has seeded Attachment rows for their desk",
      "min_rows": 1,
      "entity_hint": "Attachment"
    },
    {
      "persona": "user",
      "story": "User has seeded Attachment rows for their desk",
      "min_rows": 1,
      "entity_hint": "Attachment"
    }
  ],
  "open_questions": [
    {
      "id": "q1",
      "text": "Can a milestone have multiple tasks, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q2",
      "text": "Can a comment have multiple attachments, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q3",
      "text": "Can a project have multiple tasks, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q4",
      "text": "Can a milestone have multiple comments, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q5",
      "text": "Can a project have multiple milestones, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q6",
      "text": "Can a task have multiple attachments, or just one?",
      "blocks_promote": false
    }
  ],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL."
  ],
  "rejected_chrome": [
    "Board",
    "Dashboard",
    "Data",
    "Dazzle",
    "JavaScript",
    "Plan",
    "Tasks",
    "assignee",
    "auditable",
    "author",
    "built",
    "byte",
    "command",
    "declared",
    "discussion",
    "evidence",
    "five",
    "kanban",
    "larger",
    "live",
    "mature",
    "milestone",
    "parent",
    "people",
    "product",
    "signed",
    "static",
    "task",
    "team",
    "technical"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
