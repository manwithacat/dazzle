# Stem: Story-driven job workspaces (invoice_ops)

## Claim

Invoice work is role-specific desks — approval, pay, requester drafts, audit —
not one shared mega-list plus warehouse CRUD.

## Reconstruct

- requester → `my_invoices` (drafts + in-flight)
- approver → `approval_desk` (awaiting + recently decided)
- finance → `pay_desk` (ready-to-pay + disputes + payment health)
- auditor → `audit_review` (payment trail + settled invoices)
- tenant_admin / finance_admin → `finance_ops` (shared ops overview)
- Stories `given:` match each persona’s `default_workspace`.

## Not this

- Every product persona defaults to the same finance_ops desk.
- Persona lands on a bare entity list when the job is triage, settle, or audit.
- Story `given:` workspace names that disagree with `default_workspace`.

## Expressions

- `dsl/` workspaces + personas; `docs/guides/story-to-composition.md`
- Product maturity: job workspaces lower warehouse density vs 9 list surfaces
