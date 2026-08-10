# Agent domain: Domain Join Co — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Domain Join Co is a workspace system built around verified-domain membership: a company's workspace is anchored to its verified email domain, employees join

**Source:** `/Volumes/SSD/Dazzle/examples/domain_join_co/SPECIFICATION.md`
**Fingerprint:** `f87028fae6c74bc0`

## Personas (jobs)

- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — role word in founder brief
- **Member** (`member`, stable≈`member`, grounded) — desk `member_desk` — role word in founder brief
- **Staff** (`staff`, stable≈`staff`, grounded) — desk `staff_desk` — Internal team member

## Nouns (domain types)

- **Announcement** (grounded) owner≈`owner` lifecycle: draft → published → archived — definitional sentence in founder brief (A X is …)
- **JoinCo** (grounded) owner≈`owner` lifecycle: pending → active → offboarded — definitional sentence in founder brief (A X is …)
- **Join** (grounded) owner≈`owner` lifecycle: pending → active → offboarded — appears in founder brief (source=capitalized_noun)
- **Document** (grounded) owner≈`owner` lifecycle: draft → published → archived — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Data`, `Entra`, `Facilitie`, `Goal`, `Google`, `JavaScript`, `Message`, `Microsoft`, `Op`, `Policie`, `Readines`, `Security`, `Team`, `approve`, `auditable`, `board`, `clear`, `command`, `company`, `current`, `discussion`, `flat`, `framework`, `home`, `joined`, `live`, `mature`, `named`, `people`, `playbook`, `product`, `right`, `root`, `technical`, `tenant`, `verified`

## Desks

- **admin_desk** for `admin` (hypothesis) owner≈`owner` — Job desk for Admin
- **member_desk** for `member` (hypothesis) owner≈`owner` — Job desk for Member
- **staff_desk** for `staff` (hypothesis) owner≈`owner` — Job desk for Staff

## Demo spine (seed stories)

- `admin`: Admin has seeded Announcement rows for their desk (min_rows=1, entity≈Announcement)
- `member`: Member has seeded Announcement rows for their desk (min_rows=1, entity≈Announcement)
- `staff`: Staff has seeded Announcement rows for their desk (min_rows=1, entity≈Announcement)

## Open questions

_None blocking._

## Process candidates (hypothesis)

- **assignment** (hypothesis) entity≈`Announcement` personas=[manager, member] — Announcement: auto or manager assignment to a worker

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.
- process_candidates are hypotheses — author `process` blocks when multi-persona handoffs are real; do not invent decorative processes.
- 4 noun(s) carry lifecycle_hint — emit transitions: (and lifecycle: evidence when product requires ADR-0020).

## Machine twin

```json
{
  "version": 1,
  "title": "Domain Join Co \u2014 System Specification",
  "summary": "*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Domain Join Co is a workspace system built around verified-domain membership: a company's workspace is anchored to its verified email domain, employees join",
  "source_path": "/Volumes/SSD/Dazzle/examples/domain_join_co/SPECIFICATION.md",
  "source_sha256": "f87028fae6c74bc0",
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
      "id_hint": "member",
      "label": "Member",
      "job": "",
      "desk": "member_desk",
      "stable_id_candidate": "member",
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
    }
  ],
  "nouns": [
    {
      "name": "Announcement",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [
        "draft",
        "published",
        "archived"
      ],
      "owner_field_hint": "owner"
    },
    {
      "name": "JoinCo",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [
        "pending",
        "active",
        "offboarded"
      ],
      "owner_field_hint": "owner"
    },
    {
      "name": "Join",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [
        "pending",
        "active",
        "offboarded"
      ],
      "owner_field_hint": "owner"
    },
    {
      "name": "Document",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [
        "draft",
        "published",
        "archived"
      ],
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
      "persona": "member",
      "name": "member_desk",
      "purpose": "Job desk for Member",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    },
    {
      "persona": "staff",
      "name": "staff_desk",
      "purpose": "Job desk for Staff",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    }
  ],
  "demo_spine": [
    {
      "persona": "admin",
      "story": "Admin has seeded Announcement rows for their desk",
      "min_rows": 1,
      "entity_hint": "Announcement"
    },
    {
      "persona": "member",
      "story": "Member has seeded Announcement rows for their desk",
      "min_rows": 1,
      "entity_hint": "Announcement"
    },
    {
      "persona": "staff",
      "story": "Staff has seeded Announcement rows for their desk",
      "min_rows": 1,
      "entity_hint": "Announcement"
    }
  ],
  "open_questions": [],
  "process_candidates": [
    {
      "id_hint": "assignment",
      "summary": "Announcement: auto or manager assignment to a worker",
      "personas": [
        "manager",
        "member"
      ],
      "entity_hint": "Announcement",
      "status": "hypothesis"
    }
  ],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.",
    "process_candidates are hypotheses \u2014 author `process` blocks when multi-persona handoffs are real; do not invent decorative processes.",
    "4 noun(s) carry lifecycle_hint \u2014 emit transitions: (and lifecycle: evidence when product requires ADR-0020)."
  ],
  "rejected_chrome": [
    "Data",
    "Entra",
    "Facilitie",
    "Goal",
    "Google",
    "JavaScript",
    "Message",
    "Microsoft",
    "Op",
    "Policie",
    "Readines",
    "Security",
    "Team",
    "approve",
    "auditable",
    "board",
    "clear",
    "command",
    "company",
    "current",
    "discussion",
    "flat",
    "framework",
    "home",
    "joined",
    "live",
    "mature",
    "named",
    "people",
    "playbook",
    "product",
    "right",
    "root",
    "technical",
    "tenant",
    "verified"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
