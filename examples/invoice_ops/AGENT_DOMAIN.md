# Agent domain: Invoice Ops — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Invoice Ops is a multi-tenant supplier-invoice processing system. Each customer company operates as its own tenant, managing its suppliers, the invoices those

**Source:** `/Volumes/SSD/Dazzle/examples/invoice_ops/SPECIFICATION.md`
**Fingerprint:** `4de6cd637a659311`

## Personas (jobs)

- **Requester** (`requester`, stable≈`requester`, grounded) — desk `requester_desk` — role word in founder brief
- **Approver** (`approver`, stable≈`approver`, grounded) — desk `approver_desk` — role word in founder brief
- **Finance** (`finance`, stable≈`finance`, grounded) — desk `finance_desk` — role word in founder brief
- **Auditor** (`auditor`, stable≈`auditor`, grounded) — desk `auditor_desk` — role word in founder brief
- **Staff** (`staff`, stable≈`staff`, grounded) — desk `staff_desk` — Internal team member

## Nouns (domain types)

- **Invoice** (grounded) owner≈`requester` lifecycle: draft → submitted → approved → rejected → paid — definitional sentence in founder brief (A X is …)
- **Supplier** (grounded) owner≈`requester` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Tenant** (grounded) owner≈`requester` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Message** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Bank** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Auditor** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Approver** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Payment** (grounded) owner≈`requester` lifecycle: pending → processing → completed → failed → refunded — appears in founder brief (source=capitalized_noun)

## Rejected chrome (not domain)

`Account`, `Administrator`, `Controllership`, `Desk`, `Finally`, `Itemise`, `JavaScript`, `Long`, `Manage`, `Melio`, `Metric`, `Operator`, `Requester`, `Review`, `Significant`, `Tipalti`, `Treasury`, `Two`, `approval`, `approved`, `attempt`, `attempts`, `audit`, `auditable`, `bill`, `built`, `checker`, `command`, `data`, `database`, `declared`, `discrete`, `finance`, `flat`, `fold`, `framework`, `general`, `human`, `informal`, `interrupted`, `invoices`, `item`, `lifecycle`, `line`, `live`, `maker`, `mature`, `model`, `multi`, `operation`, `override`, `people`, `product`, `read`, `record`, `roles`, `rule`, `signed`, `technical`, `users`, `vendor`

## Desks

- **requester_desk** for `requester` (hypothesis) owner≈`requester` — Job desk for Requester
- **approver_desk** for `approver` (hypothesis) owner≈`requester` — Job desk for Approver
- **finance_desk** for `finance` (hypothesis) owner≈`requester` — Job desk for Finance
- **auditor_desk** for `auditor` (hypothesis) owner≈`requester` — Job desk for Auditor
- **staff_desk** for `staff` (hypothesis) owner≈`requester` — Job desk for Staff

## Demo spine (seed stories)

- `requester`: Requester has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `approver`: Approver has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `finance`: Finance has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `auditor`: Auditor has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `staff`: Staff has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)

## Open questions

- `q1`: Can an invoice have multiple payments, or just one?
- `q2`: When is an invoice settled — on approval, on a schedule, or only after a successful payment attempt?

## Process candidates (hypothesis)

- **approval_flow** (hypothesis) entity≈`Payment` personas=[requester, approver] — Payment: requester submits, approver decides (approve/reject)
- **escalation** (hypothesis) entity≈`Payment` personas=[member, manager] — Payment: worker escalates to manager when blocked or SLA risk
- **assignment** (hypothesis) entity≈`Payment` personas=[manager, member] — Payment: auto or manager assignment to a worker
- **settlement** (hypothesis) entity≈`Payment` personas=[finance, approver] — Payment: finance settles / pays after approval
- **triage** (hypothesis) entity≈`Payment` personas=[agent, manager] — Payment: intake triage before deep work

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
  "title": "Invoice Ops \u2014 System Specification",
  "summary": "*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Invoice Ops is a multi-tenant supplier-invoice processing system. Each customer company operates as its own tenant, managing its suppliers, the invoices those",
  "source_path": "/Volumes/SSD/Dazzle/examples/invoice_ops/SPECIFICATION.md",
  "source_sha256": "4de6cd637a659311",
  "personas": [
    {
      "id_hint": "requester",
      "label": "Requester",
      "job": "",
      "desk": "requester_desk",
      "stable_id_candidate": "requester",
      "status": "grounded",
      "evidence": "role word in founder brief"
    },
    {
      "id_hint": "approver",
      "label": "Approver",
      "job": "",
      "desk": "approver_desk",
      "stable_id_candidate": "approver",
      "status": "grounded",
      "evidence": "role word in founder brief"
    },
    {
      "id_hint": "finance",
      "label": "Finance",
      "job": "",
      "desk": "finance_desk",
      "stable_id_candidate": "finance",
      "status": "grounded",
      "evidence": "role word in founder brief"
    },
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
      "owner_field_hint": "requester"
    },
    {
      "name": "Supplier",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Tenant",
      "status": "grounded",
      "evidence": "definitional sentence in founder brief (A X is \u2026)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Message",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Bank",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Auditor",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Approver",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Payment",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [
        "pending",
        "processing",
        "completed",
        "failed",
        "refunded"
      ],
      "owner_field_hint": "requester"
    }
  ],
  "desks": [
    {
      "persona": "requester",
      "name": "requester_desk",
      "purpose": "Job desk for Requester",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "approver",
      "name": "approver_desk",
      "purpose": "Job desk for Approver",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "finance",
      "name": "finance_desk",
      "purpose": "Job desk for Finance",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "auditor",
      "name": "auditor_desk",
      "purpose": "Job desk for Auditor",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "staff",
      "name": "staff_desk",
      "purpose": "Job desk for Staff",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    }
  ],
  "demo_spine": [
    {
      "persona": "requester",
      "story": "Requester has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    },
    {
      "persona": "approver",
      "story": "Approver has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    },
    {
      "persona": "finance",
      "story": "Finance has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    },
    {
      "persona": "auditor",
      "story": "Auditor has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    },
    {
      "persona": "staff",
      "story": "Staff has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    }
  ],
  "open_questions": [
    {
      "id": "q1",
      "text": "Can an invoice have multiple payments, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q2",
      "text": "When is an invoice settled \u2014 on approval, on a schedule, or only after a successful payment attempt?",
      "blocks_promote": false
    }
  ],
  "process_candidates": [
    {
      "id_hint": "approval_flow",
      "summary": "Payment: requester submits, approver decides (approve/reject)",
      "personas": [
        "requester",
        "approver"
      ],
      "entity_hint": "Payment",
      "status": "hypothesis"
    },
    {
      "id_hint": "escalation",
      "summary": "Payment: worker escalates to manager when blocked or SLA risk",
      "personas": [
        "member",
        "manager"
      ],
      "entity_hint": "Payment",
      "status": "hypothesis"
    },
    {
      "id_hint": "assignment",
      "summary": "Payment: auto or manager assignment to a worker",
      "personas": [
        "manager",
        "member"
      ],
      "entity_hint": "Payment",
      "status": "hypothesis"
    },
    {
      "id_hint": "settlement",
      "summary": "Payment: finance settles / pays after approval",
      "personas": [
        "finance",
        "approver"
      ],
      "entity_hint": "Payment",
      "status": "hypothesis"
    },
    {
      "id_hint": "triage",
      "summary": "Payment: intake triage before deep work",
      "personas": [
        "agent",
        "manager"
      ],
      "entity_hint": "Payment",
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
    "Account",
    "Administrator",
    "Controllership",
    "Desk",
    "Finally",
    "Itemise",
    "JavaScript",
    "Long",
    "Manage",
    "Melio",
    "Metric",
    "Operator",
    "Requester",
    "Review",
    "Significant",
    "Tipalti",
    "Treasury",
    "Two",
    "approval",
    "approved",
    "attempt",
    "attempts",
    "audit",
    "auditable",
    "bill",
    "built",
    "checker",
    "command",
    "data",
    "database",
    "declared",
    "discrete",
    "finance",
    "flat",
    "fold",
    "framework",
    "general",
    "human",
    "informal",
    "interrupted",
    "invoices",
    "item",
    "lifecycle",
    "line",
    "live",
    "maker",
    "mature",
    "model",
    "multi",
    "operation",
    "override",
    "people",
    "product",
    "read",
    "record",
    "roles",
    "rule",
    "signed",
    "technical",
    "users",
    "vendor"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
