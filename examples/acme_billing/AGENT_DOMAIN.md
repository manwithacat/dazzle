# Agent domain: Acme Billing — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Acme Billing is a multi-organization billing system. It manages organizations, the users who belong to them, the projects each organization runs, the invoices

**Source:** `SPECIFICATION.md`
**Fingerprint:** `a68d03bb8d97ad20`

## Personas (jobs)

- **Auditor** (`auditor`, stable≈`auditor`, grounded) — desk `auditor_desk` — role word in founder brief
- **Member** (`member`, stable≈`member`, grounded) — desk `member_desk` — role word in founder brief
- **Owner** (`owner`, stable≈`owner`, grounded) — desk `owner_desk` — Person who owns/creates primary content
- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — System administrator
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user

## Nouns (domain types)

- **Invoice** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Organization** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Project** (grounded) owner≈`owner` lifecycle: — — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Acme`, `Acros`, `Appear`, `Auditor`, `Beyond`, `JavaScript`, `Op`, `administrator`, `assignment`, `auditable`, `boundary`, `break`, `command`, `contractor`, `data`, `declared`, `formal`, `framework`, `given`, `invoices`, `limited`, `live`, `matrix`, `mature`, `membership`, `multi`, `person`, `product`, `projects`, `read`, `record`, `review`, `rules`, `sensitive`, `signed`, `skeptic`, `technical`, `tenancy`, `visibility`, `work`

## Desks

- **auditor_desk** for `auditor` (hypothesis) owner≈`owner` — Job desk for Auditor
- **member_desk** for `member` (hypothesis) owner≈`owner` — Job desk for Member
- **owner_desk** for `owner` (hypothesis) owner≈`owner` — Job desk for Owner
- **admin_desk** for `admin` (hypothesis) owner≈`owner` — Job desk for Admin
- **user_desk** for `user` (hypothesis) owner≈`owner` — Job desk for User

## Demo spine (seed stories)

- `auditor`: Auditor has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `member`: Member has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `owner`: Owner has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `admin`: Admin has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `user`: User has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)

## Open questions

- `q1`: Can a organization have multiple theirs, or just one?
- `q6`: Can a organization have multiple audits, or just one?

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.

## Machine twin

```json
{
  "version": 1,
  "title": "Acme Billing \u2014 System Specification",
  "summary": "*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Acme Billing is a multi-organization billing system. It manages organizations, the users who belong to them, the projects each organization runs, the invoices",
  "source_path": "SPECIFICATION.md",
  "source_sha256": "a68d03bb8d97ad20",
  "personas": [
    {
      "id_hint": "auditor",
      "label": "Auditor",
      "job": "",
      "desk": "auditor_desk",
      "stable_id_candidate": "auditor",
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
      "id_hint": "owner",
      "label": "Owner",
      "job": "Person who owns/creates primary content",
      "desk": "owner_desk",
      "stable_id_candidate": "owner",
      "status": "grounded",
      "evidence": "extract_personas + brief"
    },
    {
      "id_hint": "admin",
      "label": "Admin",
      "job": "System administrator",
      "desk": "admin_desk",
      "stable_id_candidate": "admin",
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
      "name": "Invoice",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "Organization",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "Project",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    }
  ],
  "desks": [
    {
      "persona": "auditor",
      "name": "auditor_desk",
      "purpose": "Job desk for Auditor",
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
      "persona": "owner",
      "name": "owner_desk",
      "purpose": "Job desk for Owner",
      "owner_field_hint": "owner",
      "status": "hypothesis"
    },
    {
      "persona": "admin",
      "name": "admin_desk",
      "purpose": "Job desk for Admin",
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
      "persona": "auditor",
      "story": "Auditor has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    },
    {
      "persona": "member",
      "story": "Member has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    },
    {
      "persona": "owner",
      "story": "Owner has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    },
    {
      "persona": "admin",
      "story": "Admin has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    },
    {
      "persona": "user",
      "story": "User has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    }
  ],
  "open_questions": [
    {
      "id": "q1",
      "text": "Can a organization have multiple theirs, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q6",
      "text": "Can a organization have multiple audits, or just one?",
      "blocks_promote": false
    }
  ],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL."
  ],
  "rejected_chrome": [
    "Acme",
    "Acros",
    "Appear",
    "Auditor",
    "Beyond",
    "JavaScript",
    "Op",
    "administrator",
    "assignment",
    "auditable",
    "boundary",
    "break",
    "command",
    "contractor",
    "data",
    "declared",
    "formal",
    "framework",
    "given",
    "invoices",
    "limited",
    "live",
    "matrix",
    "mature",
    "membership",
    "multi",
    "person",
    "product",
    "projects",
    "read",
    "record",
    "review",
    "rules",
    "sensitive",
    "signed",
    "skeptic",
    "technical",
    "tenancy",
    "visibility",
    "work"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
