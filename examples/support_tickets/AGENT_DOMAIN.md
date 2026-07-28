# Agent domain: Support Tickets System - Product Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

**Project Type**: Internal Support/Help Desk System **Target Users**: Small teams (5-20 people) handling customer support or IT tickets **Deployment**: Multi-user web application I need a support ticket system for my small team. We're getting overwhelmed with support requests coming through email, Slack, and random conversations. I want a central place where:

**Source:** `/Volumes/SSD/Dazzle/examples/support_tickets/SPEC.md`
**Fingerprint:** `bceadae509405b99`

## Personas (jobs)

- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Agent** (`agent`, stable≈`agent`, grounded) — desk `agent_desk` — role word in founder brief
- **Customer** (`customer`, stable≈`customer`, grounded) — desk `customer_desk` — role word in founder brief
- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — role word in founder brief
- **Requester** (`requester`, stable≈`requester`, grounded) — desk `requester_desk` — role word in founder brief
- **Owner** (`owner`, stable≈`owner`, grounded) — desk `owner_desk` — Person who owns/creates primary content
- **Staff** (`staff`, stable≈`staff`, grounded) — desk `staff_desk` — Internal team member
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user
- **Member** (`member`, stable≈`member`, grounded) — desk `member_desk` — Registered community member

## Nouns (domain types)

- **Move** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Everyone** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Priority** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Slack** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Timestamp** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Click** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Support** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **View** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Change** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Comment** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Back** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Reassign** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Edit** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Delete** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Created** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Advanced`, `Attach`, `Author`, `Basic`, `Breadcrumb`, `Brief`, `Bulk`, `Button`, `Canned`, `Check`, `Close`, `Confirm`, `Console`, `Create`, `Critical`, `Current`, `Data`, `Desk`, `Easy`, `Export`, `File`, `Fill`, `Fixe`, `Fixed`, `Focused`, `Full`, `Funnel`, `Heroku`, `High`, `Icon`, `Identify`, `Kanban`, `Knowledge`, `Low`, `Manage`, `Mark`, `Medium`, `Mobile`, `Normal`, `Op`, `Personal`, `Post`, `Progre`, `Quick`, `Railway`, `Read`, `Report`, `Review`, `Scenario`, `Search`, `Select`, `Top`, `Transparency`, `Trie`, `Update`, `Visual`, `Welcome`, `Worked`, `add`, `agent`, `are`, `assign`, `assigned`, `assignment`, `central`, `complex`, `confirmed`, `cracks`, `creator`, `detail`, `don`, `email`, `fast`, `flat`, `form`, `generated`, `integration`, `investigate`, `issue`, `know`, `left`, `long`, `need`, `open`, `picture`, `problem`, `resolved`, `someone`, `submit`, `team`, `ticket`, `work`

## Desks

- **manager_desk** for `manager` (hypothesis) owner≈`requester` — Job desk for Manager
- **agent_desk** for `agent` (hypothesis) owner≈`requester` — Job desk for Agent
- **customer_desk** for `customer` (hypothesis) owner≈`requester` — Job desk for Customer
- **admin_desk** for `admin` (hypothesis) owner≈`requester` — Job desk for Admin
- **requester_desk** for `requester` (hypothesis) owner≈`requester` — Job desk for Requester
- **owner_desk** for `owner` (hypothesis) owner≈`requester` — Job desk for Owner
- **staff_desk** for `staff` (hypothesis) owner≈`requester` — Job desk for Staff
- **user_desk** for `user` (hypothesis) owner≈`requester` — Job desk for User
- **member_desk** for `member` (hypothesis) owner≈`requester` — Job desk for Member

## Demo spine (seed stories)

- `manager`: Manager has seeded Move rows for their desk (min_rows=1, entity≈Move)
- `agent`: Agent has seeded Move rows for their desk (min_rows=1, entity≈Move)
- `customer`: Customer has seeded Move rows for their desk (min_rows=1, entity≈Move)
- `admin`: Admin has seeded Move rows for their desk (min_rows=1, entity≈Move)
- `requester`: Requester has seeded Move rows for their desk (min_rows=1, entity≈Move)
- `owner`: Owner has seeded Move rows for their desk (min_rows=1, entity≈Move)
- `staff`: Staff has seeded Move rows for their desk (min_rows=1, entity≈Move)
- `user`: User has seeded Move rows for their desk (min_rows=1, entity≈Move)
- `member`: Member has seeded Move rows for their desk (min_rows=1, entity≈Move)

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
  "title": "Support Tickets System - Product Specification",
  "summary": "**Project Type**: Internal Support/Help Desk System **Target Users**: Small teams (5-20 people) handling customer support or IT tickets **Deployment**: Multi-user web application I need a support ticket system for my small team. We're getting overwhelmed with support requests coming through email, Slack, and random conversations. I want a central place where:",
  "source_path": "/Volumes/SSD/Dazzle/examples/support_tickets/SPEC.md",
  "source_sha256": "bceadae509405b99",
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
      "id_hint": "agent",
      "label": "Agent",
      "job": "",
      "desk": "agent_desk",
      "stable_id_candidate": "agent",
      "status": "grounded",
      "evidence": "role word in founder brief"
    },
    {
      "id_hint": "customer",
      "label": "Customer",
      "job": "",
      "desk": "customer_desk",
      "stable_id_candidate": "customer",
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
      "id_hint": "requester",
      "label": "Requester",
      "job": "",
      "desk": "requester_desk",
      "stable_id_candidate": "requester",
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
      "name": "Move",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Everyone",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Priority",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Slack",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Timestamp",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Click",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Support",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "View",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Change",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Comment",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Back",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Reassign",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Edit",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Delete",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Created",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    }
  ],
  "desks": [
    {
      "persona": "manager",
      "name": "manager_desk",
      "purpose": "Job desk for Manager",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "agent",
      "name": "agent_desk",
      "purpose": "Job desk for Agent",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "customer",
      "name": "customer_desk",
      "purpose": "Job desk for Customer",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "admin",
      "name": "admin_desk",
      "purpose": "Job desk for Admin",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "requester",
      "name": "requester_desk",
      "purpose": "Job desk for Requester",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "owner",
      "name": "owner_desk",
      "purpose": "Job desk for Owner",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "staff",
      "name": "staff_desk",
      "purpose": "Job desk for Staff",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "user",
      "name": "user_desk",
      "purpose": "Job desk for User",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "member",
      "name": "member_desk",
      "purpose": "Job desk for Member",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    }
  ],
  "demo_spine": [
    {
      "persona": "manager",
      "story": "Manager has seeded Move rows for their desk",
      "min_rows": 1,
      "entity_hint": "Move"
    },
    {
      "persona": "agent",
      "story": "Agent has seeded Move rows for their desk",
      "min_rows": 1,
      "entity_hint": "Move"
    },
    {
      "persona": "customer",
      "story": "Customer has seeded Move rows for their desk",
      "min_rows": 1,
      "entity_hint": "Move"
    },
    {
      "persona": "admin",
      "story": "Admin has seeded Move rows for their desk",
      "min_rows": 1,
      "entity_hint": "Move"
    },
    {
      "persona": "requester",
      "story": "Requester has seeded Move rows for their desk",
      "min_rows": 1,
      "entity_hint": "Move"
    },
    {
      "persona": "owner",
      "story": "Owner has seeded Move rows for their desk",
      "min_rows": 1,
      "entity_hint": "Move"
    },
    {
      "persona": "staff",
      "story": "Staff has seeded Move rows for their desk",
      "min_rows": 1,
      "entity_hint": "Move"
    },
    {
      "persona": "user",
      "story": "User has seeded Move rows for their desk",
      "min_rows": 1,
      "entity_hint": "Move"
    },
    {
      "persona": "member",
      "story": "Member has seeded Move rows for their desk",
      "min_rows": 1,
      "entity_hint": "Move"
    }
  ],
  "open_questions": [],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL."
  ],
  "rejected_chrome": [
    "Advanced",
    "Attach",
    "Author",
    "Basic",
    "Breadcrumb",
    "Brief",
    "Bulk",
    "Button",
    "Canned",
    "Check",
    "Close",
    "Confirm",
    "Console",
    "Create",
    "Critical",
    "Current",
    "Data",
    "Desk",
    "Easy",
    "Export",
    "File",
    "Fill",
    "Fixe",
    "Fixed",
    "Focused",
    "Full",
    "Funnel",
    "Heroku",
    "High",
    "Icon",
    "Identify",
    "Kanban",
    "Knowledge",
    "Low",
    "Manage",
    "Mark",
    "Medium",
    "Mobile",
    "Normal",
    "Op",
    "Personal",
    "Post",
    "Progre",
    "Quick",
    "Railway",
    "Read",
    "Report",
    "Review",
    "Scenario",
    "Search",
    "Select",
    "Top",
    "Transparency",
    "Trie",
    "Update",
    "Visual",
    "Welcome",
    "Worked",
    "add",
    "agent",
    "are",
    "assign",
    "assigned",
    "assignment",
    "central",
    "complex",
    "confirmed",
    "cracks",
    "creator",
    "detail",
    "don",
    "email",
    "fast",
    "flat",
    "form",
    "generated",
    "integration",
    "investigate",
    "issue",
    "know",
    "left",
    "long",
    "need",
    "open",
    "picture",
    "problem",
    "resolved",
    "someone",
    "submit",
    "team",
    "ticket",
    "work"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
