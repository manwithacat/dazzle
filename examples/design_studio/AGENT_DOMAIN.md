# Agent domain: Design Studio — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Design Studio is a creative-operations system for teams that produce branded design work. It manages brands, the design assets created for them, the campaigns those assets serve, and the review feedback that moves an asset from

**Source:** `/Volumes/SSD/Dazzle/examples/design_studio/SPECIFICATION.md`
**Fingerprint:** `12d37e021a31b281`

## Personas (jobs)

- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — role word in founder brief
- **Designer** (`designer`, stable≈`designer`, grounded) — desk `designer_desk` — role word in founder brief
- **Reviewer** (`reviewer`, stable≈`reviewer`, grounded) — desk `reviewer_desk` — role word in founder brief
- **Staff** (`staff`, stable≈`staff`, grounded) — desk `staff_desk` — Internal team member
- **Host** (`host`, stable≈`host`, grounded) — desk `host_desk` — Person who hosts/provides space

## Nouns (domain types)

- **Brand** (grounded) owner≈`assigned_to` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Campaign** (grounded) owner≈`assigned_to` lifecycle: planning → active → completed → cancelled — definitional sentence in founder brief (A X is …)
- **DesignAsset** (grounded) owner≈`assigned_to` lifecycle: draft → review → approved → published → archived — definitional sentence in founder brief (A X is …)
- **DesignFeedback** (grounded) owner≈`assigned_to` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Feedback** (grounded) owner≈`assigned_to` lifecycle: — — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Abstract`, `Adobe`, `Beyond`, `Campaigns`, `Catalog`, `Dashboard`, `Data`, `Design`, `Designer`, `Frame`, `Goal`, `JavaScript`, `Named`, `Op`, `Reviewer`, `Strategy`, `Studio`, `System`, `asset`, `assigned`, `auditable`, `bare`, `byte`, `command`, `creative`, `critique`, `current`, `desk`, `document`, `draft`, `explicit`, `flat`, `fold`, `formal`, `framework`, `informal`, `live`, `matrix`, `mature`, `people`, `pipeline`, `product`, `pull`, `record`, `review`, `schedule`, `skeptic`, `specific`, `static`, `technical`, `visibility`, `work`

## Desks

- **admin_desk** for `admin` (hypothesis) owner≈`assigned_to` — Job desk for Admin
- **designer_desk** for `designer` (hypothesis) owner≈`assigned_to` — Job desk for Designer
- **reviewer_desk** for `reviewer` (hypothesis) owner≈`assigned_to` — Job desk for Reviewer
- **staff_desk** for `staff` (hypothesis) owner≈`assigned_to` — Job desk for Staff
- **host_desk** for `host` (hypothesis) owner≈`assigned_to` — Job desk for Host

## Demo spine (seed stories)

- `admin`: Admin has seeded Brand rows for their desk (min_rows=1, entity≈Brand)
- `designer`: Designer has seeded Brand rows for their desk (min_rows=1, entity≈Brand)
- `reviewer`: Reviewer has seeded Brand rows for their desk (min_rows=1, entity≈Brand)
- `staff`: Staff has seeded Brand rows for their desk (min_rows=1, entity≈Brand)
- `host`: Host has seeded Brand rows for their desk (min_rows=1, entity≈Brand)

## Open questions

- `q1`: Can a brand have multiple assets, or just one?
- `q2`: Can both parties leave reviews, or just one side?

## Process candidates (hypothesis)

- **assignment** (hypothesis) entity≈`DesignAsset` personas=[manager, member] — DesignAsset: auto or manager assignment to a worker

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.
- process_candidates are hypotheses — author `process` blocks when multi-persona handoffs are real; do not invent decorative processes.
- 2 noun(s) carry lifecycle_hint — emit transitions: (and lifecycle: evidence when product requires ADR-0020).

## Machine twin

```json
{
  "version": 1,
  "title": "Design Studio \u2014 System Specification",
  "summary": "*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Design Studio is a creative-operations system for teams that produce branded design work. It manages brands, the design assets created for them, the campaigns those assets serve, and the review feedback that moves an asset from",
  "source_path": "/Volumes/SSD/Dazzle/examples/design_studio/SPECIFICATION.md",
  "source_sha256": "12d37e021a31b281",
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
      "id_hint": "designer",
      "label": "Designer",
      "job": "",
      "desk": "designer_desk",
      "stable_id_candidate": "designer",
      "status": "grounded",
      "evidence": "role word in founder brief"
    },
    {
      "id_hint": "reviewer",
      "label": "Reviewer",
      "job": "",
      "desk": "reviewer_desk",
      "stable_id_candidate": "reviewer",
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
      "id_hint": "host",
      "label": "Host",
      "job": "Person who hosts/provides space",
      "desk": "host_desk",
      "stable_id_candidate": "host",
      "status": "grounded",
      "evidence": "extract_personas + brief"
    }
  ],
  "nouns": [
    {
      "name": "Brand",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "Campaign",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [
        "planning",
        "active",
        "completed",
        "cancelled"
      ],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "DesignAsset",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [
        "draft",
        "review",
        "approved",
        "published",
        "archived"
      ],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "DesignFeedback",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    },
    {
      "name": "Feedback",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "assigned_to"
    }
  ],
  "desks": [
    {
      "persona": "admin",
      "name": "admin_desk",
      "purpose": "Job desk for Admin",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    },
    {
      "persona": "designer",
      "name": "designer_desk",
      "purpose": "Job desk for Designer",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    },
    {
      "persona": "reviewer",
      "name": "reviewer_desk",
      "purpose": "Job desk for Reviewer",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    },
    {
      "persona": "staff",
      "name": "staff_desk",
      "purpose": "Job desk for Staff",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    },
    {
      "persona": "host",
      "name": "host_desk",
      "purpose": "Job desk for Host",
      "owner_field_hint": "assigned_to",
      "status": "hypothesis"
    }
  ],
  "demo_spine": [
    {
      "persona": "admin",
      "story": "Admin has seeded Brand rows for their desk",
      "min_rows": 1,
      "entity_hint": "Brand"
    },
    {
      "persona": "designer",
      "story": "Designer has seeded Brand rows for their desk",
      "min_rows": 1,
      "entity_hint": "Brand"
    },
    {
      "persona": "reviewer",
      "story": "Reviewer has seeded Brand rows for their desk",
      "min_rows": 1,
      "entity_hint": "Brand"
    },
    {
      "persona": "staff",
      "story": "Staff has seeded Brand rows for their desk",
      "min_rows": 1,
      "entity_hint": "Brand"
    },
    {
      "persona": "host",
      "story": "Host has seeded Brand rows for their desk",
      "min_rows": 1,
      "entity_hint": "Brand"
    }
  ],
  "open_questions": [
    {
      "id": "q1",
      "text": "Can a brand have multiple assets, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q2",
      "text": "Can both parties leave reviews, or just one side?",
      "blocks_promote": false
    }
  ],
  "process_candidates": [
    {
      "id_hint": "assignment",
      "summary": "DesignAsset: auto or manager assignment to a worker",
      "personas": [
        "manager",
        "member"
      ],
      "entity_hint": "DesignAsset",
      "status": "hypothesis"
    }
  ],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.",
    "process_candidates are hypotheses \u2014 author `process` blocks when multi-persona handoffs are real; do not invent decorative processes.",
    "2 noun(s) carry lifecycle_hint \u2014 emit transitions: (and lifecycle: evidence when product requires ADR-0020)."
  ],
  "rejected_chrome": [
    "Abstract",
    "Adobe",
    "Beyond",
    "Campaigns",
    "Catalog",
    "Dashboard",
    "Data",
    "Design",
    "Designer",
    "Frame",
    "Goal",
    "JavaScript",
    "Named",
    "Op",
    "Reviewer",
    "Strategy",
    "Studio",
    "System",
    "asset",
    "assigned",
    "auditable",
    "bare",
    "byte",
    "command",
    "creative",
    "critique",
    "current",
    "desk",
    "document",
    "draft",
    "explicit",
    "flat",
    "fold",
    "formal",
    "framework",
    "informal",
    "live",
    "matrix",
    "mature",
    "people",
    "pipeline",
    "product",
    "pull",
    "record",
    "review",
    "schedule",
    "skeptic",
    "specific",
    "static",
    "technical",
    "visibility",
    "work"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
