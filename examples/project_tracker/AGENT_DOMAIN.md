# Agent domain: Project Tracker — Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

Project Tracker is a team project-management product. It organises work as Projects owned by a team member, broken into Milestones and Tasks, with Comments carrying the conversation, Project Documents (briefs, specs, proposals, status reports, decisions) as named composition buyers scan above the notes trail, and Attachments as binary file evidence on tasks. Everyone on the team shares two working

**Source:** `/Volumes/SSD/Dazzle/examples/project_tracker/SPECIFICATION.md`
**Fingerprint:** `424f133fc3468d7f`

## Personas (jobs)

- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — role word in founder brief
- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Member** (`member`, stable≈`member`, grounded) — desk `member_desk` — role word in founder brief

## Nouns (domain types)

- **Attachment** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Comment** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Milestone** (grounded) owner≈`owner` lifecycle: planning → active → completed — definitional sentence in founder brief (A X is …)
- **Project** (grounded) owner≈`owner` lifecycle: backlog → todo → in_progress → review → done → cancelled — definitional sentence in founder brief (A X is …)
- **Task** (grounded) owner≈`assigned_to` lifecycle: progress → review → done — definitional sentence in founder brief (A X is …)
- **TeamMember** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Discussion** (grounded) owner≈`owner` lifecycle: — — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Board`, `Dashboard`, `Data`, `JavaScript`, `Message`, `Mockup`, `People`, `Plan`, `Proposal`, `Review`, `Tasks`, `assignee`, `auditable`, `author`, `built`, `byte`, `chart`, `command`, `conversation`, `dazzle`, `decision`, `declared`, `document`, `five`, `informal`, `kanban`, `larger`, `live`, `mature`, `parent`, `product`, `queue`, `signed`, `spec`, `static`, `team`, `technical`

## Desks

- **admin_desk** for `admin` (hypothesis) owner≈`owner` — Job desk for Admin
- **manager_desk** for `manager` (hypothesis) owner≈`owner` — Job desk for Manager
- **member_desk** for `member` (hypothesis) owner≈`owner` — Job desk for Member

## Demo spine (seed stories)

- `admin`: Admin has seeded Project rows for their desk (min_rows=1, entity≈Project)
- `manager`: Manager has seeded Project rows for their desk (min_rows=1, entity≈Project)
- `member`: Member has seeded Project rows for their desk (min_rows=1, entity≈Project)

## Open questions

- `q1`: Can a milestone have multiple tasks, or just one?
- `q2`: Can a project have multiple tasks, or just one?
- `q3`: Can a milestone have multiple comments, or just one?
- `q4`: Can a project have multiple milestones, or just one?
- `q5`: Can a task have multiple attachments, or just one?
- `q6`: Should users receive email/push notifications for key events?

## Process candidates (hypothesis)

- **escalation** (hypothesis) entity≈`Task` personas=[member, manager] — Task: worker escalates to manager when blocked or SLA risk
- **assignment** (hypothesis) entity≈`Task` personas=[manager, member] — Task: auto or manager assignment to a worker

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.
- process_candidates are hypotheses — author `process` blocks when multi-persona handoffs are real; do not invent decorative processes.
- 3 noun(s) carry lifecycle_hint — emit transitions: (and lifecycle: evidence when product requires ADR-0020).

## Machine twin

```json
{
  "version": 1,
  "title": "Project Tracker \u2014 Specification",
  "summary": "Project Tracker is a team project-management product. It organises work as Projects owned by a team member, broken into Milestones and Tasks, with Comments carrying the conversation, Project Documents (briefs, specs, proposals, status reports, decisions) as named composition buyers scan above the notes trail, and Attachments as binary file evidence on tasks. Everyone on the team shares two working",
  "source_path": "/Volumes/SSD/Dazzle/examples/project_tracker/SPECIFICATION.md",
  "source_sha256": "424f133fc3468d7f",
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
    }
  ],
  "nouns": [
    {
      "name": "Attachment",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "Comment",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "Milestone",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [
        "planning",
        "active",
        "completed"
      ],
      "owner_field_hint": "owner"
    },
    {
      "name": "Project",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [
        "backlog",
        "todo",
        "in_progress",
        "review",
        "done",
        "cancelled"
      ],
      "owner_field_hint": "owner"
    },
    {
      "name": "Task",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [
        "progress",
        "review",
        "done"
      ],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "TeamMember",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "Discussion",
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
    }
  ],
  "demo_spine": [
    {
      "persona": "admin",
      "story": "Admin has seeded Project rows for their desk",
      "min_rows": 1,
      "entity_hint": "Project"
    },
    {
      "persona": "manager",
      "story": "Manager has seeded Project rows for their desk",
      "min_rows": 1,
      "entity_hint": "Project"
    },
    {
      "persona": "member",
      "story": "Member has seeded Project rows for their desk",
      "min_rows": 1,
      "entity_hint": "Project"
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
      "text": "Can a project have multiple tasks, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q3",
      "text": "Can a milestone have multiple comments, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q4",
      "text": "Can a project have multiple milestones, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q5",
      "text": "Can a task have multiple attachments, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q6",
      "text": "Should users receive email/push notifications for key events?",
      "blocks_promote": false
    }
  ],
  "process_candidates": [
    {
      "id_hint": "escalation",
      "summary": "Task: worker escalates to manager when blocked or SLA risk",
      "personas": [
        "member",
        "manager"
      ],
      "entity_hint": "Task",
      "status": "hypothesis"
    },
    {
      "id_hint": "assignment",
      "summary": "Task: auto or manager assignment to a worker",
      "personas": [
        "manager",
        "member"
      ],
      "entity_hint": "Task",
      "status": "hypothesis"
    }
  ],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.",
    "process_candidates are hypotheses \u2014 author `process` blocks when multi-persona handoffs are real; do not invent decorative processes.",
    "3 noun(s) carry lifecycle_hint \u2014 emit transitions: (and lifecycle: evidence when product requires ADR-0020)."
  ],
  "rejected_chrome": [
    "Board",
    "Dashboard",
    "Data",
    "JavaScript",
    "Message",
    "Mockup",
    "People",
    "Plan",
    "Proposal",
    "Review",
    "Tasks",
    "assignee",
    "auditable",
    "author",
    "built",
    "byte",
    "chart",
    "command",
    "conversation",
    "dazzle",
    "decision",
    "declared",
    "document",
    "five",
    "informal",
    "kanban",
    "larger",
    "live",
    "mature",
    "parent",
    "product",
    "queue",
    "signed",
    "spec",
    "static",
    "team",
    "technical"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
