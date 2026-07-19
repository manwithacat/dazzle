# Agent domain: FieldTest Hub – Product Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

**Project Type**: Distributed beta testing + product quality platform **Target Users**: Hardware founders, product managers, QA engineers, beta testers **Deployment**: Multi-tenant app for startups and hardware teams I need an application that allows early-stage hardware companies to coordinate real-world field testing of physical devices (e.g., wearables, IoT sensors, robotics components). Curren

**Source:** `/Volumes/SSD/Dazzle/examples/fieldtest_hub/SPEC.md`
**Fingerprint:** `20f06d857af42844`

## Personas (jobs)

- **Tester** (`tester`, stable≈`tester`, grounded) — desk `tester_desk` — role word in founder brief
- **Engineer** (`engineer`, stable≈`engineer`, grounded) — desk `engineer_desk` — role word in founder brief
- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user

## Nouns (domain types)

- **Device** (grounded) owner≈`—` lifecycle: — — entity section header in founder brief
- **FirmwareRelease** (grounded) owner≈`—` lifecycle: — — entity section header in founder brief
- **IssueReport** (grounded) owner≈`—` lifecycle: — — entity section header in founder brief
- **Task** (grounded) owner≈`assigned_to` lifecycle: — — entity section header in founder brief
- **TestSession** (grounded) owner≈`—` lifecycle: — — entity section header in founder brief
- **Issue** (grounded) owner≈`assigned_to` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Firmware** (grounded) owner≈`—` lifecycle: — — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Assign`, `Assigned`, `Auto`, `Automated`, `Batch`, `Board`, `Cancelled`, `Capture`, `Casual`, `Cluster`, `Completed`, `Connectivity`, `Crash`, `Critical`, `Dashboard`, `Date`, `Deprecated`, `Detail`, `Detect`, `Directory`, `Draft`, `Engineer`, `Enthusiast`, `File`, `Filter`, `Fixed`, `Fleet`, `Form`, `Full`, `Geo`, `Hardware`, `High`, `Identify`, `Indoor`, `Industrial`, `Kanban`, `Know`, `Latch`, `Level`, `List`, `Low`, `Mark`, `Medium`, `Non`, `Notification`, `Number`, `Outdoor`, `Page`, `Personal`, `Problem`, `Progre`, `Prototype`, `Queue`, `Recall`, `Recalled`, `Release`, `Released`, `Report`, `Reproduce`, `Request`, `Result`, `Retired`, `Robotic`, `Role`, `Scenario`, `Session`, `Slack`, `Specific`, `Spreadsheet`, `Team`, `Test`, `Tester`, `Timeline`, `Triage`, `Triaged`, `Update`, `Vehicle`, `Verified`, `Version`, `Wearable`

## Desks

- **tester_desk** for `tester` (hypothesis) owner≈`assigned_to` — Job desk for Tester
- **engineer_desk** for `engineer` (hypothesis) owner≈`assigned_to` — Job desk for Engineer
- **manager_desk** for `manager` (hypothesis) owner≈`assigned_to` — Job desk for Manager
- **user_desk** for `user` (hypothesis) owner≈`assigned_to` — Job desk for User

## Demo spine (seed stories)

- `tester`: Tester has seeded Device rows for their desk (min_rows=1, entity≈Device)
- `engineer`: Engineer has seeded Device rows for their desk (min_rows=1, entity≈Device)
- `manager`: Manager has seeded Device rows for their desk (min_rows=1, entity≈Device)
- `user`: User has seeded Device rows for their desk (min_rows=1, entity≈Device)

## Open questions

- `q1`: Can a startup have multiple hardwares, or just one?
- `q2`: Can a batche have multiple firmwares, or just one?
- `q5`: Can both parties leave reviews, or just one side?

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.

## Machine twin

```json
{
  "version": 1,
  "title": "FieldTest Hub \u2013 Product Specification",
  "summary": "**Project Type**: Distributed beta testing + product quality platform **Target Users**: Hardware founders, product managers, QA engineers, beta testers **Deployment**: Multi-tenant app for startups and hardware teams I need an application that allows early-stage hardware companies to coordinate real-world field testing of physical devices (e.g., wearables, IoT sensors, robotics components). Curren",
  "source_path": "/Volumes/SSD/Dazzle/examples/fieldtest_hub/SPEC.md",
  "source_sha256": "20f06d857af42844",
  "personas": [
    {
      "id_hint": "tester",
      "label": "Tester",
      "job": "",
      "desk": "tester_desk",
      "stable_id_candidate": "tester",
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
      "id_hint": "manager",
      "label": "Manager",
      "job": "",
      "desk": "manager_desk",
      "stable_id_candidate": "manager",
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
      "name": "Device",
      "status": "grounded",
      "evidence": "entity section header in founder brief",
      "lifecycle_hint": [],
      "owner_field_hint": null
    },
    {
      "name": "FirmwareRelease",
      "status": "grounded",
      "evidence": "entity section header in founder brief",
      "lifecycle_hint": [],
      "owner_field_hint": null
    },
    {
      "name": "IssueReport",
      "status": "grounded",
      "evidence": "entity section header in founder brief",
      "lifecycle_hint": [],
      "owner_field_hint": null
    },
    {
      "name": "Task",
      "status": "grounded",
      "evidence": "entity section header in founder brief",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "TestSession",
      "status": "grounded",
      "evidence": "entity section header in founder brief",
      "lifecycle_hint": [],
      "owner_field_hint": null
    },
    {
      "name": "Issue",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "Firmware",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": null
    }
  ],
  "desks": [
    {
      "persona": "tester",
      "name": "tester_desk",
      "purpose": "Job desk for Tester",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    },
    {
      "persona": "engineer",
      "name": "engineer_desk",
      "purpose": "Job desk for Engineer",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    },
    {
      "persona": "manager",
      "name": "manager_desk",
      "purpose": "Job desk for Manager",
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
      "persona": "tester",
      "story": "Tester has seeded Device rows for their desk",
      "min_rows": 1,
      "entity_hint": "Device"
    },
    {
      "persona": "engineer",
      "story": "Engineer has seeded Device rows for their desk",
      "min_rows": 1,
      "entity_hint": "Device"
    },
    {
      "persona": "manager",
      "story": "Manager has seeded Device rows for their desk",
      "min_rows": 1,
      "entity_hint": "Device"
    },
    {
      "persona": "user",
      "story": "User has seeded Device rows for their desk",
      "min_rows": 1,
      "entity_hint": "Device"
    }
  ],
  "open_questions": [
    {
      "id": "q1",
      "text": "Can a startup have multiple hardwares, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q2",
      "text": "Can a batche have multiple firmwares, or just one?",
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
    "Assign",
    "Assigned",
    "Auto",
    "Automated",
    "Batch",
    "Board",
    "Cancelled",
    "Capture",
    "Casual",
    "Cluster",
    "Completed",
    "Connectivity",
    "Crash",
    "Critical",
    "Dashboard",
    "Date",
    "Deprecated",
    "Detail",
    "Detect",
    "Directory",
    "Draft",
    "Engineer",
    "Enthusiast",
    "File",
    "Filter",
    "Fixed",
    "Fleet",
    "Form",
    "Full",
    "Geo",
    "Hardware",
    "High",
    "Identify",
    "Indoor",
    "Industrial",
    "Kanban",
    "Know",
    "Latch",
    "Level",
    "List",
    "Low",
    "Mark",
    "Medium",
    "Non",
    "Notification",
    "Number",
    "Outdoor",
    "Page",
    "Personal",
    "Problem",
    "Progre",
    "Prototype",
    "Queue",
    "Recall",
    "Recalled",
    "Release",
    "Released",
    "Report",
    "Reproduce",
    "Request",
    "Result",
    "Retired",
    "Robotic",
    "Role",
    "Scenario",
    "Session",
    "Slack",
    "Specific",
    "Spreadsheet",
    "Team",
    "Test",
    "Tester",
    "Timeline",
    "Triage",
    "Triaged",
    "Update",
    "Vehicle",
    "Verified",
    "Version",
    "Wearable"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
