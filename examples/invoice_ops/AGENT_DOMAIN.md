# Agent domain: Invoice Ops — System Specification

> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.
> Promote only when `dazzle domain promote` is green. No chrome entities.

## Summary

*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Invoice Ops is a multi-tenant supplier-invoice processing system. Each customer company operates as its own tenant, managing its suppliers, the invoices those

**Source:** `/Volumes/SSD/Dazzle/examples/invoice_ops/SPECIFICATION.md`
**Fingerprint:** `829eb476d540bff7`

## Personas (jobs)

- **Requester** (`requester`, stable≈`requester`, grounded) — desk `requester_desk` — role word in founder brief
- **Approver** (`approver`, stable≈`approver`, grounded) — desk `approver_desk` — role word in founder brief
- **Finance** (`finance`, stable≈`finance`, grounded) — desk `finance_desk` — role word in founder brief
- **Auditor** (`auditor`, stable≈`auditor`, grounded) — desk `auditor_desk` — role word in founder brief
- **Customer** (`customer`, stable≈`customer`, grounded) — desk `customer_desk` — Person who purchases/consumes
- **Admin** (`admin`, stable≈`admin`, grounded) — desk `admin_desk` — System administrator
- **Staff** (`staff`, stable≈`staff`, grounded) — desk `staff_desk` — Internal team member
- **User** (`user`, stable≈`user`, grounded) — desk `user_desk` — Generic system user
- **Provider** (`provider`, stable≈`provider`, grounded) — desk `provider_desk` — Person who provides services

## Nouns (domain types)

- **Invoice** (grounded) owner≈`requester` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Supplier** (grounded) owner≈`requester` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Tenant** (grounded) owner≈`requester` lifecycle: — — definitional sentence in founder brief (A X is …)
- **Bank** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=capitalized_noun)
- **Approver** (grounded) owner≈`requester` lifecycle: — — appears in founder brief (source=article_noun)

## Rejected chrome (not domain)

`Account`, `Administrator`, `Auditor`, `Desk`, `Finally`, `Item`, `Itemise`, `JavaScript`, `Long`, `Manage`, `Metric`, `Operator`, `Requester`, `Review`, `Significant`, `Two`, `approval`, `approved`, `attempt`, `attempts`, `auditable`, `built`, `checker`, `command`, `data`, `database`, `declared`, `discrete`, `flat`, `framework`, `general`, `human`, `informal`, `interrupted`, `invoices`, `lifecycle`, `line`, `live`, `maker`, `mature`, `model`, `multi`, `operation`, `override`, `payment`, `product`, `read`, `roles`, `rule`, `signed`, `technical`, `users`

## Desks

- **requester_desk** for `requester` (hypothesis) owner≈`requester` — Job desk for Requester
- **approver_desk** for `approver` (hypothesis) owner≈`requester` — Job desk for Approver
- **finance_desk** for `finance` (hypothesis) owner≈`requester` — Job desk for Finance
- **auditor_desk** for `auditor` (hypothesis) owner≈`requester` — Job desk for Auditor
- **customer_desk** for `customer` (hypothesis) owner≈`requester` — Job desk for Customer
- **admin_desk** for `admin` (hypothesis) owner≈`requester` — Job desk for Admin
- **staff_desk** for `staff` (hypothesis) owner≈`requester` — Job desk for Staff
- **user_desk** for `user` (hypothesis) owner≈`requester` — Job desk for User
- **provider_desk** for `provider` (hypothesis) owner≈`requester` — Job desk for Provider

## Demo spine (seed stories)

- `requester`: Requester has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `approver`: Approver has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `finance`: Finance has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `auditor`: Auditor has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `customer`: Customer has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `admin`: Admin has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `staff`: Staff has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `user`: User has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)
- `provider`: Provider has seeded Invoice rows for their desk (min_rows=1, entity≈Invoice)

## Open questions

- `q1`: Can a tenant have multiple theirs, or just one?
- `q2`: Can a invoice have multiple theirs, or just one?
- `q5`: Can a supplier have multiple theirs, or just one?
- `q6`: Can a invoice have multiple payments, or just one?

## Research notes

- Prefer knowledge concepts before inventing structure.
- Do not promote ungrounded nouns.
- Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.

## Machine twin

```json
{
  "version": 1,
  "title": "Invoice Ops \u2014 System Specification",
  "summary": "*Generated from the application model. Every guarantee cited below can be independently verified with the command shown beside it.* Invoice Ops is a multi-tenant supplier-invoice processing system. Each customer company operates as its own tenant, managing its suppliers, the invoices those",
  "source_path": "/Volumes/SSD/Dazzle/examples/invoice_ops/SPECIFICATION.md",
  "source_sha256": "829eb476d540bff7",
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
      "id_hint": "customer",
      "label": "Customer",
      "job": "Person who purchases/consumes",
      "desk": "customer_desk",
      "stable_id_candidate": "customer",
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
      "id_hint": "staff",
      "label": "Staff",
      "job": "Internal team member",
      "desk": "staff_desk",
      "stable_id_candidate": "staff",
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
    },
    {
      "id_hint": "provider",
      "label": "Provider",
      "job": "Person who provides services",
      "desk": "provider_desk",
      "stable_id_candidate": "provider",
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
      "name": "Bank",
      "status": "grounded",
      "evidence": "appears in founder brief (source=capitalized_noun)",
      "lifecycle_hint": [],
      "owner_field_hint": "requester"
    },
    {
      "name": "Approver",
      "status": "grounded",
      "evidence": "appears in founder brief (source=article_noun)",
      "lifecycle_hint": [],
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
      "persona": "customer",
      "name": "customer_desk",
      "purpose": "Job desk for Customer",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "admin",
      "name": "admin_desk",
      "purpose": "Job desk for Admin",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "staff",
      "name": "staff_desk",
      "purpose": "Job desk for Staff",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "user",
      "name": "user_desk",
      "purpose": "Job desk for User",
      "owner_field_hint": "requester",
      "status": "hypothesis"
    },
    {
      "persona": "provider",
      "name": "provider_desk",
      "purpose": "Job desk for Provider",
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
      "persona": "customer",
      "story": "Customer has seeded Invoice rows for their desk",
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
      "persona": "staff",
      "story": "Staff has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    },
    {
      "persona": "user",
      "story": "User has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    },
    {
      "persona": "provider",
      "story": "Provider has seeded Invoice rows for their desk",
      "min_rows": 1,
      "entity_hint": "Invoice"
    }
  ],
  "open_questions": [
    {
      "id": "q1",
      "text": "Can a tenant have multiple theirs, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q2",
      "text": "Can a invoice have multiple theirs, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q5",
      "text": "Can a supplier have multiple theirs, or just one?",
      "blocks_promote": false
    },
    {
      "id": "q6",
      "text": "Can a invoice have multiple payments, or just one?",
      "blocks_promote": false
    }
  ],
  "research_notes": [
    "Prefer knowledge concepts before inventing structure.",
    "Do not promote ungrounded nouns.",
    "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL."
  ],
  "rejected_chrome": [
    "Account",
    "Administrator",
    "Auditor",
    "Desk",
    "Finally",
    "Item",
    "Itemise",
    "JavaScript",
    "Long",
    "Manage",
    "Metric",
    "Operator",
    "Requester",
    "Review",
    "Significant",
    "Two",
    "approval",
    "approved",
    "attempt",
    "attempts",
    "auditable",
    "built",
    "checker",
    "command",
    "data",
    "database",
    "declared",
    "discrete",
    "flat",
    "framework",
    "general",
    "human",
    "informal",
    "interrupted",
    "invoices",
    "lifecycle",
    "line",
    "live",
    "maker",
    "mature",
    "model",
    "multi",
    "operation",
    "override",
    "payment",
    "product",
    "read",
    "roles",
    "rule",
    "signed",
    "technical",
    "users"
  ]
}
```

<!-- dazzle-agent-domain: v1 -->
