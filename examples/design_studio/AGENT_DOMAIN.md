# Agent domain: Design Studio — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Design Studio is a creative-operations system for teams that produce branded design work. It manages brands, the design assets created for them, the campaigns those assets serve, and the review feedback that moves an asset from

**Source:** `/Volumes/SSD/Dazzle/examples/design_studio/SPECIFICATION.md`
**Fingerprint:** `fc0e9022e61d09ce`

## Personas (jobs)

- **Designer** (`designer`, stable≈`designer`, grounded) — desk `designer_desk` — role word in founder brief
- **Reviewer** (`reviewer`, stable≈`reviewer`, grounded) — desk `reviewer_desk` — role word in founder brief

## Nouns (domain types)

- **Brand** (grounded) owner≈`created_by` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Campaign** (grounded) owner≈`created_by` lifecycle: planning → active → completed → cancelled — definitional sentence in founder brief (A X is …)
- **DesignAsset** (grounded) owner≈`created_by` lifecycle: draft → review → approved → published → archived — definitional sentence in founder brief (A X is …)
- **DesignFeedback** (grounded) owner≈`created_by` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Feedback** (grounded) owner≈`created_by` lifecycle: — — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Beyond`, `Campaigns`, `Catalog`, `Dashboard`, `Data`, `Design`, `Designer`, `Desk`, `JavaScript`, `Metric`, `Reviewer`, `Studio`, `asset`, `auditable`, `byte`, `command`, `creative`, `current`, `explicit`, `formal`, `framework`, `live`, `matrix`, `mature`, `people`, `product`, `record`, `review`, `skeptic`, `specific`, `static`, `technical`, `visibility`

## Desks

- **designer_desk** for `designer` (hypothesis) owner≈`created_by` — Job desk for Designer
- **reviewer_desk** for `reviewer` (hypothesis) owner≈`created_by` — Job desk for Reviewer

## Demo spine (seed stories)

- `designer`: Designer has seeded Brand rows for their desk (min_rows=1, entity≈Brand)
- `reviewer`: Reviewer has seeded Brand rows for their desk (min_rows=1, entity≈Brand)

## Open questions

- `q1`: Can a brand have multiple assets, or just one?
- `q2`: Can both parties leave reviews, or just one side?

## Process candidates (hypothesis)

- **assignment** (hypothesis) entity≈`Campaign` personas=[manager, member] — Campaign: auto or manager assignment to a worker

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
  "source_sha256": "fc0e9022e61d09ce",
  "personas": [
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
    }
  ],
  "nouns": [
    {
      "name": "Brand",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "created_by"
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
      "owner_field_hint": "created_by"
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
      "owner_field_hint": "created_by"
    },
    {
      "name": "DesignFeedback",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "created_by"
    },
    {
      "name": "Feedback",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "created_by"
    }
  ],
  "desks": [
    {
      "persona": "designer",
      "name": "designer_desk",
      "purpose": "Job desk for Designer",
      "owner_field_hint": "created_by",
      "status": "hypothesis"
    },
    {
      "persona": "reviewer",
      "name": "reviewer_desk",
      "purpose": "Job desk for Reviewer",
      "owner_field_hint": "created_by",
      "status": "hypothesis"
    }
  ],
  "demo_spine": [
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
      "summary": "Campaign: auto or manager assignment to a worker",
      "personas": [
        "manager",
        "member"
      ],
      "entity_hint": "Campaign",
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
    "Beyond",
    "Campaigns",
    "Catalog",
    "Dashboard",
    "Data",
    "Design",
    "Designer",
    "Desk",
    "JavaScript",
    "Metric",
    "Reviewer",
    "Studio",
    "asset",
    "auditable",
    "byte",
    "command",
    "creative",
    "current",
    "explicit",
    "formal",
    "framework",
    "live",
    "matrix",
    "mature",
    "people",
    "product",
    "record",
    "review",
    "skeptic",
    "specific",
    "static",
    "technical",
    "visibility"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
