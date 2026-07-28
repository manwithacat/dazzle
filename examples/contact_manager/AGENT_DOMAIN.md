# Agent domain: Contact Manager - Product Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

> **Document Status**: Refined specification ready for DSL conversion > **Complexity Level**: Beginner+ > **DSL Features Demonstrated**: dual_pane_flow stage, intent declaration, domain/pattern tags, indexes A personal contact management app that lets users efficiently browse and manage their professional and personal contacts. The dual-pane interface enables quick scanning of contacts while viewi

**Source:** `examples/contact_manager/SPEC.md`
**Fingerprint:** `9fbeb4dabddc0413`

## Personas (jobs)

- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief
- **Owner** (`owner`, stable≈`owner`, grounded) — desk `owner_desk` — Person who owns/creates primary content
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user

## Nouns (domain types)

- **Contact** (grounded) owner≈`owner` lifecycle: — — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Acceptance`, `Add`, `Change`, `Click`, `Criteria`, `Delete`, `Duplicate`, `Edit`, `Efficient`, `Flow`, `Import`, `Indexe`, `Level`, `Multiple`, `Point`, `Profile`, `Rule`, `Sale`, `Scrollable`, `Search`, `Star`, `bare`, `currently`, `detail`, `directory`, `dual`, `email`, `favorite`, `favourites`, `form`, `implementation`, `list`, `pane`, `pattern`, `personal`, `phone`, `save`, `short`, `unique`

## Desks

- **manager_desk** for `manager` (hypothesis) owner≈`owner` — Job desk for Manager
- **owner_desk** for `owner` (hypothesis) owner≈`owner` — Job desk for Owner
- **user_desk** for `user` (hypothesis) owner≈`owner` — Job desk for User

## Demo spine (seed stories)

- `manager`: Manager has seeded Contact rows for their desk (min_rows=1, entity≈Contact)
- `owner`: Owner has seeded Contact rows for their desk (min_rows=1, entity≈Contact)
- `user`: User has seeded Contact rows for their desk (min_rows=1, entity≈Contact)

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
  "title": "Contact Manager - Product Specification",
  "summary": "> **Document Status**: Refined specification ready for DSL conversion > **Complexity Level**: Beginner+ > **DSL Features Demonstrated**: dual_pane_flow stage, intent declaration, domain/pattern tags, indexes A personal contact management app that lets users efficiently browse and manage their professional and personal contacts. The dual-pane interface enables quick scanning of contacts while viewi",
  "source_path": "examples/contact_manager/SPEC.md",
  "source_sha256": "9fbeb4dabddc0413",
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
      "id_hint": "owner",
      "label": "Owner",
      "job": "Person who owns/creates primary content",
      "desk": "owner_desk",
      "stable_id_candidate": "owner",
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
    }
  ],
  "nouns": [
    {
      "name": "Contact",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    }
  ],
  "desks": [
    {
      "persona": "manager",
      "name": "manager_desk",
      "purpose": "Job desk for Manager",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    },
    {
      "persona": "owner",
      "name": "owner_desk",
      "purpose": "Job desk for Owner",
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
      "persona": "manager",
      "story": "Manager has seeded Contact rows for their desk",
      "min_rows": 1,
      "entity_hint": "Contact"
    },
    {
      "persona": "owner",
      "story": "Owner has seeded Contact rows for their desk",
      "min_rows": 1,
      "entity_hint": "Contact"
    },
    {
      "persona": "user",
      "story": "User has seeded Contact rows for their desk",
      "min_rows": 1,
      "entity_hint": "Contact"
    }
  ],
  "open_questions": [],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL."
  ],
  "rejected_chrome": [
    "Acceptance",
    "Add",
    "Change",
    "Click",
    "Criteria",
    "Delete",
    "Duplicate",
    "Edit",
    "Efficient",
    "Flow",
    "Import",
    "Indexe",
    "Level",
    "Multiple",
    "Point",
    "Profile",
    "Rule",
    "Sale",
    "Scrollable",
    "Search",
    "Star",
    "bare",
    "currently",
    "detail",
    "directory",
    "dual",
    "email",
    "favorite",
    "favourites",
    "form",
    "implementation",
    "list",
    "pane",
    "pattern",
    "personal",
    "phone",
    "save",
    "short",
    "unique"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
