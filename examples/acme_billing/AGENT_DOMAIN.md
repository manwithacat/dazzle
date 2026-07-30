# Agent domain: Acme Billing — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Acme Billing is a multi-organization billing system. It manages organizations, the users who belong to them, the projects each organization runs, the invoices

**Source:** `/Volumes/SSD/Dazzle/examples/acme_billing/SPECIFICATION.md`
**Fingerprint:** `d179e4aceb2e6883`

## Personas (jobs)

- **Auditor** (`auditor`, stable≈`auditor`, grounded) — desk `auditor_desk` — role word in founder brief
- **Member** (`member`, stable≈`member`, grounded) — desk `member_desk` — role word in founder brief
- **Owner** (`owner`, stable≈`owner`, grounded) — desk `owner_desk` — Person who owns/creates primary content

## Nouns (domain types)

- **Invoice** (grounded) owner≈`owner` lifecycle: draft → submitted → approved → rejected → paid — definitional sentence in founder brief (A X is …)
- **Organization** (grounded) owner≈`owner` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Project** (grounded) owner≈`owner` lifecycle: backlog → todo → in_progress → review → done → cancelled — appears in founder brief (source=capitalized_noun)
- **Membership** (grounded) owner≈`owner` lifecycle: — — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Acme`, `Acros`, `Administrator`, `Appear`, `Auditor`, `Beyond`, `Invoices`, `JavaScript`, `Op`, `Projects`, `assignment`, `auditable`, `boundary`, `break`, `command`, `contractor`, `data`, `declared`, `formal`, `framework`, `given`, `limited`, `live`, `matrix`, `mature`, `multi`, `person`, `product`, `read`, `record`, `review`, `rules`, `sensitive`, `signed`, `skeptic`, `technical`, `tenancy`, `visibility`, `work`

## Desks

- **auditor_desk** for `auditor` (hypothesis) owner≈`owner` — Job desk for Auditor
- **member_desk** for `member` (hypothesis) owner≈`owner` — Job desk for Member
- **owner_desk** for `owner` (hypothesis) owner≈`owner` — Job desk for Owner

## Demo spine (seed stories)

- `auditor`: Auditor has seeded Organization rows for their desk (min_rows=1, entity≈Organization)
- `member`: Member has seeded Organization rows for their desk (min_rows=1, entity≈Organization)
- `owner`: Owner has seeded Organization rows for their desk (min_rows=1, entity≈Organization)

## Open questions

- `q1`: Can an invoice have multiple projects, or just one?

## Process candidates (hypothesis)

- **approval_flow** (hypothesis) entity≈`Invoice` personas=[requester, approver] — Invoice: requester submits, approver decides (approve/reject)
- **assignment** (hypothesis) entity≈`Invoice` personas=[manager, member] — Invoice: auto or manager assignment to a worker

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
  "title": "Acme Billing \u2014 System Specification",
  "summary": "*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Acme Billing is a multi-organization billing system. It manages organizations, the users who belong to them, the projects each organization runs, the invoices",
  "source_path": "/Volumes/SSD/Dazzle/examples/acme_billing/SPECIFICATION.md",
  "source_sha256": "d179e4aceb2e6883",
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
    }
  ],
  "nouns": [
    {
      "name": "Invoice",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [
        "draft",
        "submitted",
        "approved",
        "rejected",
        "paid"
      ],
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
      "lifecycle_hint": [
        "backlog",
        "todo",
        "in_progress",
        "review",
        "done",
        "cancelled"
      ],
      "owner_field_hint": "owner"
    },
    {
      "name": "Membership",
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
    }
  ],
  "demo_spine": [
    {
      "persona": "auditor",
      "story": "Auditor has seeded Organization rows for their desk",
      "min_rows": 1,
      "entity_hint": "Organization"
    },
    {
      "persona": "member",
      "story": "Member has seeded Organization rows for their desk",
      "min_rows": 1,
      "entity_hint": "Organization"
    },
    {
      "persona": "owner",
      "story": "Owner has seeded Organization rows for their desk",
      "min_rows": 1,
      "entity_hint": "Organization"
    }
  ],
  "open_questions": [
    {
      "id": "q1",
      "text": "Can an invoice have multiple projects, or just one?",
      "blocks_promote": false
    }
  ],
  "process_candidates": [
    {
      "id_hint": "approval_flow",
      "summary": "Invoice: requester submits, approver decides (approve/reject)",
      "personas": [
        "requester",
        "approver"
      ],
      "entity_hint": "Invoice",
      "status": "hypothesis"
    },
    {
      "id_hint": "assignment",
      "summary": "Invoice: auto or manager assignment to a worker",
      "personas": [
        "manager",
        "member"
      ],
      "entity_hint": "Invoice",
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
    "Acme",
    "Acros",
    "Administrator",
    "Appear",
    "Auditor",
    "Beyond",
    "Invoices",
    "JavaScript",
    "Op",
    "Projects",
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
    "limited",
    "live",
    "matrix",
    "mature",
    "multi",
    "person",
    "product",
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
