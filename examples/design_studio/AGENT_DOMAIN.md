# Agent domain: Design Studio — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Design Studio is a creative-operations system for teams that produce branded design work. It manages brands, the design assets created for them, the campaigns those assets serve, and the review feedback that moves an asset from

**Source:** `examples/design_studio/SPECIFICATION.md`
**Fingerprint:** `82205592939831a0`

## Personas (jobs)

- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — role word in founder brief
- **Designer** (`designer`, stable≈`designer`, grounded) — desk `designer_desk` — role word in founder brief
- **Reviewer** (`reviewer`, stable≈`reviewer`, grounded) — desk `reviewer_desk` — role word in founder brief
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user

## Nouns (domain types)

- **Brand** (grounded) owner≈`created_by` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Campaign** (grounded) owner≈`created_by` lifecycle: — — definitional sentence in founder brief (A X is …)
- **DesignAsset** (grounded) owner≈`created_by` lifecycle: — — definitional sentence in founder brief (A X is …)
- **DesignFeedback** (grounded) owner≈`created_by` lifecycle: — — definitional sentence in founder brief (A X is …)

## Rejected chrome (not domain)

`Beyond`, `Catalog`, `Dashboard`, `Data`, `Design`, `Designer`, `Desk`, `JavaScript`, `Metric`, `Studio`, `asset`, `auditable`, `byte`, `campaigns`, `command`, `creative`, `current`, `explicit`, `feedback`, `formal`, `framework`, `live`, `matrix`, `mature`, `people`, `product`, `record`, `review`, `reviewer`, `skeptic`, `specific`, `static`, `technical`, `visibility`

## Desks

- **admin_desk** for `admin` (hypothesis) owner≈`created_by` — Job desk for Admin
- **designer_desk** for `designer` (hypothesis) owner≈`created_by` — Job desk for Designer
- **reviewer_desk** for `reviewer` (hypothesis) owner≈`created_by` — Job desk for Reviewer
- **user_desk** for `user` (hypothesis) owner≈`created_by` — Job desk for User

## Demo spine (seed stories)

- `admin`: Admin has seeded Brand rows for their desk (min_rows=1, entity≈Brand)
- `designer`: Designer has seeded Brand rows for their desk (min_rows=1, entity≈Brand)
- `reviewer`: Reviewer has seeded Brand rows for their desk (min_rows=1, entity≈Brand)
- `user`: User has seeded Brand rows for their desk (min_rows=1, entity≈Brand)

## Open questions

_None blocking._

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.
- Core nouns from SPEC definitions: Brand, DesignAsset, Campaign, DesignFeedback.
- owner_field_hint=created_by matches design_studio DSL User refs.
- Personas: Admin, Designer, Reviewer (+ User entity).

## Machine twin

```json
{
  "version": 1,
  "title": "Design Studio \u2014 System Specification",
  "summary": "*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Design Studio is a creative-operations system for teams that produce branded design work. It manages brands, the design assets created for them, the campaigns those assets serve, and the review feedback that moves an asset from",
  "source_path": "examples/design_studio/SPECIFICATION.md",
  "source_sha256": "82205592939831a0",
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
      "lifecycle_hint": [],
      "owner_field_hint": "created_by"
    },
    {
      "name": "DesignAsset",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "created_by"
    },
    {
      "name": "DesignFeedback",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "created_by"
    }
  ],
  "desks": [
    {
      "persona": "admin",
      "name": "admin_desk",
      "purpose": "Job desk for Admin",
      "owner_field_hint": "created_by",
      "status": "hypothesis"
    },
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
    },
    {
      "persona": "user",
      "name": "user_desk",
      "purpose": "Job desk for User",
      "owner_field_hint": "created_by",
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
      "persona": "user",
      "story": "User has seeded Brand rows for their desk",
      "min_rows": 1,
      "entity_hint": "Brand"
    }
  ],
  "open_questions": [],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.",
    "Core nouns from SPEC definitions: Brand, DesignAsset, Campaign, DesignFeedback.",
    "owner_field_hint=created_by matches design_studio DSL User refs.",
    "Personas: Admin, Designer, Reviewer (+ User entity)."
  ],
  "rejected_chrome": [
    "Beyond",
    "Catalog",
    "Dashboard",
    "Data",
    "Design",
    "Designer",
    "Desk",
    "JavaScript",
    "Metric",
    "Studio",
    "asset",
    "auditable",
    "byte",
    "campaigns",
    "command",
    "creative",
    "current",
    "explicit",
    "feedback",
    "formal",
    "framework",
    "live",
    "matrix",
    "mature",
    "people",
    "product",
    "record",
    "review",
    "reviewer",
    "skeptic",
    "specific",
    "static",
    "technical",
    "visibility"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
