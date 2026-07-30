# Agent domain: Team Task Manager — Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

Team Task Manager is a task-tracking system for teams: work is captured as Tasks, assigned to Team Members, discussed in threaded comments, and moved through an explicit lifecycle from *todo* to *done*. Three roles use it — Administrators, Team Managers, and Team Members — each seeing exactly the work

**Source:** `/Volumes/SSD/Dazzle/examples/simple_task/SPECIFICATION.md`
**Fingerprint:** `8833b74e73c2c00e`

## Personas (jobs)

- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Member** (`member`, stable≈`member`, grounded) — desk `member_desk` — role word in founder brief

## Nouns (domain types)

- **Task** (grounded) owner≈`assigned_to` lifecycle: pending → assigned → in_progress → completed → blocked — definitional sentence in founder brief (A X is …)
- **TeamMember** (grounded) owner≈`assigned_to` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Comment** (grounded) owner≈`assigned_to` lifecycle: — — appears in founder brief (source=article_noun)

## Rejected chrome (not domain)

`Administrator`, `Dashboard`, `Data`, `Discussion`, `JavaScript`, `Metric`, `Tasks`, `Team`, `approval`, `auditable`, `board`, `built`, `creator`, `database`, `declared`, `effort`, `explicit`, `flat`, `framework`, `human`, `interrupted`, `live`, `mature`, `model`, `organisation`, `overdue`, `precise`, `priority`, `product`, `review`, `rhythm`, `technical`, `visibility`, `whole`, `work`

## Desks

- **manager_desk** for `manager` (hypothesis) owner≈`assigned_to` — Job desk for Manager
- **member_desk** for `member` (hypothesis) owner≈`assigned_to` — Job desk for Member

## Demo spine (seed stories)

- `manager`: Manager has seeded Task rows for their desk (min_rows=1, entity≈Task)
- `member`: Member has seeded Task rows for their desk (min_rows=1, entity≈Task)

## Open questions

- `q1`: Can a task have multiple users, or just one?
- `q2`: Should users receive email/push notifications for key events?

## Process candidates (hypothesis)

- **escalation** (hypothesis) entity≈`Task` personas=[member, manager] — Task: worker escalates to manager when blocked or SLA risk
- **assignment** (hypothesis) entity≈`Task` personas=[manager, member] — Task: auto or manager assignment to a worker

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
  "title": "Team Task Manager \u2014 Specification",
  "summary": "Team Task Manager is a task-tracking system for teams: work is captured as Tasks, assigned to Team Members, discussed in threaded comments, and moved through an explicit lifecycle from *todo* to *done*. Three roles use it \u2014 Administrators, Team Managers, and Team Members \u2014 each seeing exactly the work",
  "source_path": "/Volumes/SSD/Dazzle/examples/simple_task/SPECIFICATION.md",
  "source_sha256": "8833b74e73c2c00e",
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
    "1 noun(s) carry lifecycle_hint \u2014 emit transitions: (and lifecycle: evidence when product requires ADR-0020)."
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
