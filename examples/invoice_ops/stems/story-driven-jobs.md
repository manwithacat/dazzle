# Stem: Story-driven job workspaces (invoice_ops)

## Claim

Invoice work is role-specific desks — approval, pay, requester drafts, audit —
not one shared mega-list plus warehouse CRUD.

## Reconstruct

- requester → `my_invoices` (drafts + in-flight)
- approver → `approval_desk` (awaiting + recently decided)
- finance → `pay_desk` (multi-panel: ready-to-pay + disputes before notes)
- auditor → `audit_review` (payment trail + settled invoices)
- tenant_admin / finance_admin → `finance_ops` (shared ops overview)
- Stories `given:` match each persona’s `default_workspace`.

- List triple-open (story dig cycle 1597 + 1608 journey): `invoice_list` →
  Invoice|Supplier|User(submitted_by); `payment_attempt_list` →
  PaymentAttempt|Invoice|Tenant; `line_item_list` → LineItem|Invoice|Tenant;
  `supplier_bank_account_list` → SupplierBankAccount|Supplier|Tenant.
- List dual-open: `supplier_list` / `user_list` → Tenant via tenant_id
  (admin roster context).

## Not this

- Every product persona defaults to the same finance_ops desk.
- Persona lands on a bare entity list when the job is triage, settle, or audit.
- Story `given:` workspace names that disagree with `default_workspace`.

## Expressions

- `dsl/` workspaces + personas; `docs/guides/story-to-composition.md`
- Product maturity: job workspaces lower warehouse density vs 9 list surfaces
