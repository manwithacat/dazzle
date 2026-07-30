# Agent domain: Contact Manager - Product Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

> **Document Status**: Refined specification ready for DSL conversion > **Complexity Level**: Beginner+ > **DSL Features Demonstrated**: dual_pane_flow stage, intent declaration, domain/pattern tags, indexes A personal contact management app that lets users efficiently browse and manage their professional and personal contacts. The dual-pane interface enables quick scanning of contacts while viewi

**Source:** `/Volumes/SSD/Dazzle/examples/contact_manager/SPEC.md`
**Fingerprint:** `9fbeb4dabddc0413`

## Personas (jobs)

- **Manager** (`manager`, stable≈`manager`, grounded) — desk `manager_desk` — role word in founder brief

## Nouns (domain types)

- **Contact** (grounded) owner≈`owner` lifecycle: — — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Acceptance`, `Add`, `Change`, `Click`, `Criteria`, `Delete`, `Duplicate`, `Edit`, `Efficient`, `Flow`, `Import`, `Indexe`, `Level`, `Multiple`, `Point`, `Profile`, `Rule`, `Sale`, `Scrollable`, `Search`, `Star`, `bare`, `currently`, `detail`, `directory`, `dual`, `email`, `favorite`, `favourites`, `form`, `implementation`, `list`, `pane`, `pattern`, `personal`, `phone`, `save`, `short`, `unique`

## Desks

- **manager_desk** for `manager` (hypothesis) owner≈`owner` — Job desk for Manager

## Demo spine (seed stories)

- `manager`: Manager has seeded Contact rows for their desk (min_rows=1, entity≈Contact)

## Open questions

_None blocking._

## Process candidates (hypothesis)

_None — consider process blocks when ≥2 personas share a lifecycle noun._

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
  "source_path": "/Volumes/SSD/Dazzle/examples/contact_manager/SPEC.md",
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
    }
  ],
  "demo_spine": [
    {
      "persona": "manager",
      "story": "Manager has seeded Contact rows for their desk",
      "min_rows": 1,
      "entity_hint": "Contact"
    }
  ],
  "open_questions": [],
  "process_candidates": [],
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
