# Stem: Story-driven job workspaces (invoice_ops)

## Claim

Invoice work is role-specific desks — approval, pay, requester drafts, audit —
not one shared mega-list plus warehouse CRUD.

## Reconstruct

- requester → `my_invoices` (needs-you: drafts, in-flight, rejected, disputed, approved-unsettled; lines on the slip)
- approver → `approval_desk` (inspect then stamp released for settlement, not paid)
- finance → `pay_desk` (ready-to-pay + disputes; failed rail does not move Invoice)
- auditor → `audit_review` (today's attempts; earlier tries on the invoice)
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
- Job workspace that is still a **filtered entity list** as the work
  object. Blue Sky 2026-08-30 (`invoice_ops` approver/finance/requester/auditor):
  the object in hand is the sheet, blotter paper, slip, or carbon — next
  after a decision, not return-to-list. Do not invent `stack:` from that
  run; the stem is the judgement.
- Approver stamps from the pile. `approval_desk.awaiting_approval`
  uses `transitions: none` (#1663); inspect the invoice, then stamp.
- Role-only approve is a lie (#1668): `submitted -> approved` requires
  `approval_exception` (spoken "released for settlement"). Unmatched
  submit still cannot collection-guard LineItem `po_match` (leftover;
  `not_applicable` is a kind per `ap-domain-theory.md`).

## Expressions

- `dsl/` workspaces + personas; `docs/guides/story-to-composition.md`
- Product maturity: job workspaces lower warehouse density vs 9 list surfaces
- Money words (settle vs attest, NSF, `not_applicable`): `ap-domain-theory.md`
