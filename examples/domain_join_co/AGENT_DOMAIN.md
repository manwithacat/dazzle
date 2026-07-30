# Agent domain: Domain Join Co — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Domain Join Co is a workspace system built around verified-domain membership: a company's workspace is anchored to its verified email domain, employees join

**Source:** `/Volumes/SSD/Dazzle/examples/domain_join_co/SPECIFICATION.md`
**Fingerprint:** `3ccb170d6a173dd6`

## Personas (jobs)

- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — role word in founder brief

## Nouns (domain types)

- **JoinCo** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Announcement** (grounded) owner≈`owner` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Join** (grounded) owner≈`owner` lifecycle: — — appears in founder brief (source=article_noun)

## Rejected chrome (not domain)

`Data`, `JavaScript`, `Readines`, `approve`, `auditable`, `board`, `clear`, `command`, `company`, `current`, `framework`, `home`, `live`, `mature`, `post`, `product`, `right`, `root`, `team`, `technical`, `tenant`, `verified`

## Desks

- **admin_desk** for `admin` (hypothesis) owner≈`owner` — Job desk for Admin

## Demo spine (seed stories)

- `admin`: Admin has seeded JoinCo rows for their desk (min_rows=1, entity≈JoinCo)

## Open questions

_None blocking._

## Process candidates (hypothesis)

- **assignment** (hypothesis) entity≈`JoinCo` personas=[manager, member] — JoinCo: auto or manager assignment to a worker

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.
- process_candidates are hypotheses — author `process` blocks when multi-persona handoffs are real; do not invent decorative processes.

## Machine twin

```json
{
  "version": 1,
  "title": "Domain Join Co \u2014 System Specification",
  "summary": "*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Domain Join Co is a workspace system built around verified-domain membership: a company's workspace is anchored to its verified email domain, employees join",
  "source_path": "/Volumes/SSD/Dazzle/examples/domain_join_co/SPECIFICATION.md",
  "source_sha256": "3ccb170d6a173dd6",
  "personas": [
    {
      "id_hint": "admin",
      "label": "Admin",
      "job": "",
      "desk": "admin_desk",
      "stable_id_candidate": "admin",
      "status": "grounded",
      "evidence": "role word in founder brief"
    }
  ],
  "nouns": [
    {
      "name": "JoinCo",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "Announcement",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "owner"
    },
    {
      "name": "Join",
      "status": "grounded",
      "evidence": "appears in founder brief (source=article_noun)",
      "lifecycle_hint": [],
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
    }
  ],
  "demo_spine": [
    {
      "persona": "admin",
      "story": "Admin has seeded JoinCo rows for their desk",
      "min_rows": 1,
      "entity_hint": "JoinCo"
    }
  ],
  "open_questions": [],
  "process_candidates": [
    {
      "id_hint": "assignment",
      "summary": "JoinCo: auto or manager assignment to a worker",
      "personas": [
        "manager",
        "member"
      ],
      "entity_hint": "JoinCo",
      "status": "hypothesis"
    }
  ],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.",
    "process_candidates are hypotheses \u2014 author `process` blocks when multi-persona handoffs are real; do not invent decorative processes."
  ],
  "rejected_chrome": [
    "Data",
    "JavaScript",
    "Readines",
    "approve",
    "auditable",
    "board",
    "clear",
    "command",
    "company",
    "current",
    "framework",
    "home",
    "live",
    "mature",
    "post",
    "product",
    "right",
    "root",
    "team",
    "technical",
    "tenant",
    "verified"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
