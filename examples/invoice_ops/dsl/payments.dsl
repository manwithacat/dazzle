module invoice_ops.payments

use invoice_ops.entities

# External payment provider, modelled as an integration service. The stub is
# driven by `dazzle mock` scenarios (success / insufficient-funds / timeout).
service payment_provider "Payment Provider":
  kind: integration

  input:
    invoice_id: uuid required
    amount: decimal(15,2) required
    currency: str(3) required

  output:
    succeeded: bool
    provider_reference: str
    failure_reason: text

  guarantees:
    - "Idempotent for the same invoice_id"
    - "Returns a failure_reason on every non-success outcome"

  stub: python

# Settlement saga: triggered when an invoice reaches `approved`.
process settle_invoice "Settle Approved Invoice":
  trigger:
    when: entity Invoice status -> approved

  input:
    invoice_id: uuid required

  steps:
    - step charge:
        service: payment_provider
        timeout: 30s
        retry:
          max_attempts: 3
          backoff: exponential

  timeout: 5m

# =============================================================================
# PAYMENT ATTEMPT — one attempt to settle an approved invoice.
# =============================================================================

entity PaymentAttempt "Payment Attempt":
  intent: "One attempt to settle an approved invoice via the payment provider"

  id: uuid pk
  tenant_id: ref Tenant required
  invoice: ref Invoice required
  attempt_number: int=1
  status: enum[pending,succeeded,failed]=pending
  provider_reference: str(80) optional
  failure_reason: text optional
  created_at: datetime auto_add

  # Settlement attempt SM (domain residual status∄transitions).
  # Provider outcomes are terminal; finance may re-open failed for retry.
  transitions:
    pending -> succeeded: role(finance) or role(finance_admin)
    pending -> failed: role(finance) or role(finance_admin)
    failed -> pending: role(finance) or role(finance_admin)

  permit:
    create: role(finance) or role(finance_admin)
    read: role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)
    update: role(finance) or role(finance_admin)
    delete: role(tenant_admin)
    list: role(approver) or role(finance) or role(finance_admin) or role(auditor) or role(tenant_admin)

  scope:
    create: tenant_id = current_user.tenant_id
      as: finance, finance_admin
    read: tenant_id = current_user.tenant_id
      as: approver, finance, finance_admin, auditor, tenant_admin
    update: tenant_id = current_user.tenant_id
      as: finance, finance_admin
    delete: tenant_id = current_user.tenant_id
      as: tenant_admin
    list: tenant_id = current_user.tenant_id
      as: approver, finance, finance_admin, auditor, tenant_admin

  audit: all

# =============================================================================
# PAYMENT ATTEMPT SURFACES
# =============================================================================

surface payment_attempt_list "Payment Attempts":
  uses entity PaymentAttempt
  mode: list
  # Triple open (story_walk dig cycle 1597): attempt hub, parent invoice, tenant root.
  open: PaymentAttempt via id | Invoice via invoice | Tenant via tenant_id
  section main:
    field invoice "Invoice"
    field attempt_number "Attempt"
    field status "Status"
    field failure_reason "Failure Reason"
  ux:
    purpose: "Payment trail — open a row for the attempt, invoice, or tenant hub"

# #1666: carbon read order on this VIEW — attempt, then invoice, then tenant.
# List `open:` pipe is three doors, not one folio. `related show: Invoice`
# cannot embed the parent (linker: FK must point at this surface's entity).
surface payment_attempt_detail "Payment Attempt":
  uses entity PaymentAttempt
  mode: view
  section attempt "Attempt":
    field attempt_number "Attempt"
    field status "Status"
  section invoice "Invoice":
    field invoice "Invoice"
  section tenant "Tenant":
    field tenant_id "Tenant"
  section provider "Provider":
    layout: strip
    field provider_reference "Provider reference"
    field failure_reason "Failure Reason"
  ux:
    purpose: "One carbon read: attempt, then invoice, then tenant — three hubs, not trail:"

surface payment_attempt_create "New Payment Attempt":
  uses entity PaymentAttempt
  mode: create
  section main:
    field invoice "Invoice"
    field attempt_number "Attempt"
    field status "Status"
    field provider_reference "Provider reference"
  ux:
    purpose: "Record a settlement attempt against an approved invoice"

# =============================================================================
# PAYMENT WORKSPACES
# =============================================================================
workspace pay_desk "Pay Desk":
  # Goal B command_density + document (cycle 1820/1879): dual attention then
  # remittance / payment-confirmation packets before notes.
  # Cycle 1957: draft packet release gate before ready_to_pay (peer AP settle).
  # Cycle 1961: payment confirmation trail (proof of settle before/after batch).
  # Cycle 1971: credit memo watch — VAT/short-ship credits before settle batch.
  # Cycle 1974: remittance advice watch — SEPA/ACH remittance covers before settle.
  # Cycle 1981: debit memo watch — vendor additional charges before settle batch.
  # Cycle 1983: vendor statement watch — period-end AP reconcile before settle.
  # Cycle 1985: packing slip watch — carrier packing slips for three-way match.
  # Cycle 1987: ACH authorization watch — signed ACH auth before first settle.
  # Cycle 1989: wire instructions watch — bank wire details before first wire release.
  # Cycle 1991: lien waiver watch — conditional/final lien waivers before pay release.
  # Cycle 1993: insurance certificate (COI) watch — proof of insurance before contractor pay.
  # Cycle 1995: Form W-9 watch — IRS W-9 / vendor TIN before first US settle.
  # Cycle 2002: three-way match evidence pack (PO + GRN + packing slip).
  # Cycle 2055: due_stage_density — soft on-time ready vs hard past-due approved
  # dual queues (Bill.com / Melio / Tipalti settle urgency stages; not one mixed
  # ready_to_pay list and not broader open past_due including submitted drafts).
  # Cycle 2071: intake_stage_density — exclusive draft intake vs submitted
  # awaiting-approval Invoice boards after the urgent due-stage decisions.
  # Keep the document rails available for evidence without burying pay work.
  purpose: "Multi-panel settlement — failed rail does not change invoice status; retry is the same pad. Past-due and ready decisions, intake, draft gate, settle rail, match evidence"
  access: persona(finance, finance_admin)

  settle_metrics:
    source: Invoice
    display: metrics
    aggregate:
      ready: count(Invoice where status = approved)
      on_time: count(Invoice where status = approved and due_date >= today)
      past_due: count(Invoice where status = approved and due_date < today)
      disputed: count(Invoice where status = disputed)
    tones:
      ready: accent
      on_time: neutral
      past_due: destructive
      disputed: neutral

  # Settlement is the finance operator's next decision. Past-due approved
  # invoices lead; on-time work follows, both before intake/document context.
  past_due:
    source: Invoice
    filter: status = approved and due_date < today
    sort: due_date asc
    limit: 3
    display: queue
    action: invoice_detail
    transitions: none
    after: next
    empty: "No past-due approved invoices"

  ready_to_pay:
    source: Invoice
    filter: status = approved and due_date >= today
    sort: due_date asc
    limit: 3
    display: queue
    action: invoice_detail
    transitions: none
    after: next
    empty: "Nothing on-time and ready to pay"

  # Live intake stage density (cycle 2071) — separate draft intake from
  # submitted awaiting-approval work, after the due-stage decision queues.
  draft_invoice_queue:
    source: Invoice
    filter: status = draft
    sort: updated_at desc
    limit: 3
    display: queue
    action: invoice_detail
    transitions: none
    empty: "No draft invoices — intake is empty or everything is already submitted"

  awaiting_approval_queue:
    source: Invoice
    filter: status = submitted
    sort: amount desc
    limit: 3
    display: queue
    action: invoice_detail
    transitions: none
    empty: "Nothing awaiting approval — submitted work is cleared or already approved"

  # Honest document pulse (InvoiceDocument source — not cross-entity under Invoice).
  document_pulse:
    source: InvoiceDocument
    display: metrics
    aggregate:
      documents: count(InvoiceDocument)
      published: count(InvoiceDocument where status = published)
      draft: count(InvoiceDocument where status = draft)
      pay_confirms: count(InvoiceDocument where doc_kind = payment_confirmation)
      settle_rail: count(InvoiceDocument where doc_kind = remittance or doc_kind = payment_confirmation)
      adjustment_rail: count(InvoiceDocument where doc_kind = credit_memo or doc_kind = debit_memo)
      bank_rail: count(InvoiceDocument where doc_kind = ach_authorization or doc_kind = wire_instructions)
      tax_identity: count(InvoiceDocument where doc_kind = form_w9 or doc_kind = tax_certificate)
      credit_memos: count(InvoiceDocument where doc_kind = credit_memo)
      debit_memos: count(InvoiceDocument where doc_kind = debit_memo)
      vendor_statements: count(InvoiceDocument where doc_kind = vendor_statement)
      packing_slips: count(InvoiceDocument where doc_kind = packing_slip)
      ach_authorizations: count(InvoiceDocument where doc_kind = ach_authorization)
      wire_instructions: count(InvoiceDocument where doc_kind = wire_instructions)
      lien_waivers: count(InvoiceDocument where doc_kind = lien_waiver)
      insurance_certificates: count(InvoiceDocument where doc_kind = insurance_certificate)
      form_w9s: count(InvoiceDocument where doc_kind = form_w9)
      compliance_drafts: count(InvoiceDocument where status = draft and (doc_kind = form_w9 or doc_kind = insurance_certificate or doc_kind = tax_certificate or doc_kind = lien_waiver or doc_kind = ach_authorization))
      match_evidence: count(InvoiceDocument where doc_kind = po_packet or doc_kind = goods_receipt or doc_kind = packing_slip)
      remittances: count(InvoiceDocument where doc_kind = remittance)
    tones:
      documents: accent
      published: positive
      draft: warning
      pay_confirms: positive
      settle_rail: positive
      adjustment_rail: warning
      bank_rail: warning
      tax_identity: warning
      credit_memos: warning
      debit_memos: destructive
      vendor_statements: accent
      packing_slips: accent
      ach_authorizations: warning
      wire_instructions: warning
      lien_waivers: warning
      insurance_certificates: warning
      form_w9s: warning
      compliance_drafts: destructive
      match_evidence: accent
      remittances: accent

  # Peer-pack draft_packet_release_gate (cycle 1957) — publish remittance /
  # credit memos before releasing the settle batch (not composition re-stack).
  draft_packets:
    source: InvoiceDocument
    filter: status = draft
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No draft packets blocking release — publish remittances before the settle batch"

  # Peer-pack compliance_draft_gate (cycle 2000): Bill.com / Melio / Tipalti
  # vendor onboarding packets still draft (W-9 / COI / tax / lien / ACH) before
  # first settle — compound status+kind (not form_w9-only or all-draft re-stack).
  compliance_drafts:
    source: InvoiceDocument
    filter: status = draft and (doc_kind = form_w9 or doc_kind = insurance_certificate or doc_kind = tax_certificate or doc_kind = lien_waiver or doc_kind = ach_authorization)
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No compliance drafts blocking settle — W-9, COI, tax, lien, ACH published"

  # Peer-pack three_way_match_evidence (cycle 2002): Coupa / Tipalti / Bill.com
  # compound PO + goods receipt + packing slip before settle — not single
  # packing_slip / goods_receipt / po_packet re-stack after compliance_draft_gate.
  match_evidence:
    source: InvoiceDocument
    filter: doc_kind = po_packet or doc_kind = goods_receipt or doc_kind = packing_slip
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No match evidence — attach PO cover, goods receipt, and packing slip for three-way match"

  # Peer-pack settle_rail_evidence (cycle 2004): Bill.com / Melio / Tipalti
  # remittance advice + payment confirmation ACKs before batch close — not
  # remittance-only or payment_confirmation-only re-stack after match_evidence.
  settle_rail:
    source: InvoiceDocument
    filter: doc_kind = remittance or doc_kind = payment_confirmation
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No settle rail — attach remittance advice and bank payment ACKs before batch close"

  # Peer-pack adjustment_rail_evidence (cycle 2006): Bill.com / Melio / Tipalti
  # credit memo + debit memo AP adjustments before settle net — not credit-only
  # or debit-only re-stack after settle_rail / match_evidence.
  adjustment_rail:
    source: InvoiceDocument
    filter: doc_kind = credit_memo or doc_kind = debit_memo
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No adjustment rail — attach credit and debit memos before settle net"

  # Peer-pack bank_rail_evidence (cycle 2008): Bill.com / Melio / Tipalti ACH auth
  # + wire instructions payment-method pack before first settle — not ACH-only
  # or wire-only re-stack after adjustment_rail / settle_rail.
  bank_rail:
    source: InvoiceDocument
    filter: doc_kind = ach_authorization or doc_kind = wire_instructions
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No bank rail — attach ACH auth and wire instructions before first settle"

  # Peer-pack tax_identity_rail (cycle 2010): Bill.com / Melio / Tipalti Form W-9
  # + reverse-charge tax certificate TIN/VAT pack — not form_w9-only or
  # tax_certificate-only re-stack after compliance_draft_gate / bank_rail.
  tax_identity:
    source: InvoiceDocument
    filter: doc_kind = form_w9 or doc_kind = tax_certificate
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No tax identity pack — attach Form W-9 and reverse-charge tax certs before first settle"

  # Peer-pack remittance_advice_watch (cycle 1974): Bill.com / Melio remittance
  # advice on the settle desk so controllers lean into SEPA/ACH covers before
  # batch release (not credit_memo or payment_confirmation re-stack).
  remittances:
    source: InvoiceDocument
    filter: doc_kind = remittance
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No remittance advice — attach SEPA/ACH remittance covers before settle"

  # Peer-pack credit_memo_watch (cycle 1971): Bill.com / Melio / Tipalti credit
  # memos on the settle desk so controllers lean into VAT/short-ship credits
  # before batch release (not payment_confirmation or goods_receipt re-stack).
  credit_memos:
    source: InvoiceDocument
    filter: doc_kind = credit_memo
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No credit memos — attach VAT or short-ship credits before settle"

  # Peer-pack debit_memo_watch (cycle 1981): Bill.com / Melio / Tipalti debit
  # memos on the settle desk — vendor additional charges (fuel surcharge /
  # price correction) opposite credit_memo (not dispute_packet re-stack).
  debit_memos:
    source: InvoiceDocument
    filter: doc_kind = debit_memo
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No debit memos — attach vendor additional-charge memos before settle"

  # Peer-pack vendor_statement_watch (cycle 1983): Bill.com / Melio / Tipalti
  # vendor statements on the settle desk — period-end AP reconcile covers
  # before batch release (not remittance/debit re-stack).
  vendor_statements:
    source: InvoiceDocument
    filter: doc_kind = vendor_statement
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No vendor statements — attach period-end statements before reconcile"

  # Peer-pack packing_slip_watch (cycle 1985): Bill.com / Coupa / Tipalti packing
  # slips on the settle desk — carrier packing slips for three-way match with
  # PO/GRN (not goods_receipt re-stack).
  packing_slips:
    source: InvoiceDocument
    filter: doc_kind = packing_slip
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No packing slips — attach carrier packing slips for three-way match"

  # Peer-pack ach_authorization_watch (cycle 1987): Bill.com / Melio / Tipalti
  # ACH authorizations on the settle desk — signed ACH auth before first
  # SEPA/ACH batch (not remittance / payment_confirmation re-stack).
  ach_authorizations:
    source: InvoiceDocument
    filter: doc_kind = ach_authorization
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No ACH authorizations — attach signed ACH auth before first settle"

  # Peer-pack wire_instructions_watch (cycle 1989): Bill.com / Melio / Tipalti
  # wire instructions on the settle desk — bank wire details before first
  # high-value wire (not ACH mandate / payment_confirmation re-stack).
  wire_instructions:
    source: InvoiceDocument
    filter: doc_kind = wire_instructions
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No wire instructions — attach bank wire details before first wire release"

  # Peer-pack lien_waiver_watch (cycle 1991): Bill.com / Melio / Tipalti lien
  # waivers on the settle desk — conditional/final waivers before construction
  # or facility pay release (not wire/ACH/tax re-stack).
  lien_waivers:
    source: InvoiceDocument
    filter: doc_kind = lien_waiver
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No lien waivers — attach conditional or final waivers before pay release"

  # Peer-pack insurance_certificate_watch (cycle 1993): Bill.com / Melio / Tipalti
  # COI on the settle desk — proof of insurance before contractor/facility pay
  # release (not lien_waiver / wire / ACH re-stack).
  insurance_certificates:
    source: InvoiceDocument
    filter: doc_kind = insurance_certificate
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No insurance certificates — attach COI before contractor pay release"

  # Peer-pack form_w9_watch (cycle 1995): Bill.com / Melio / Tipalti Form W-9
  # on the settle desk — IRS W-9 / vendor TIN before first US settle (not
  # tax_certificate reverse-charge / COI / ACH re-stack).
  form_w9s:
    source: InvoiceDocument
    filter: doc_kind = form_w9
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No Form W-9 — collect vendor TIN before first US settle"

  # Peer-pack payment_confirmation_trail (cycle 1961): Bill.com / Melio /
  # Tipalti put payment confirmations on the settle desk so controllers lean
  # into batch proof (not draft_packet or tax_cert re-stack).
  payment_confirmations:
    source: InvoiceDocument
    filter: doc_kind = payment_confirmation
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No payment confirmations yet — attach batch ACKs after SEPA/ACH release"

  # Goal B document composition — remittance / payment-confirmation packets
  # remain on the desk after the decision and intake queues.
  composition:
    source: InvoiceDocument
    sort: created_at desc
    limit: 4
    display: queue
    action: invoice_document_detail
    empty: "No invoice documents yet — attach remittance or payment confirmation"

  disputed_queue:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 3
    display: queue
    action: invoice_detail
    transitions: none
    empty: "No disputes open"

  # Goal B conversation spine after decisions and evidence.
  # display: conversation → Message/Bubble chrome (not queue meta of note rows).
  live_conversation:
    source: InvoiceNote
    sort: created_at desc
    limit: 5
    display: conversation
    action: invoice_note_detail
    empty: "No conversation yet — payment and dispute notes appear here"

  ux:
    as finance:
      purpose: "Settle pad — failed rail does not move the invoice; retry here. Intake, due stages, settle rail, match evidence"
      focus: settle_metrics, past_due, ready_to_pay, draft_invoice_queue, awaiting_approval_queue, document_pulse, draft_packets, settle_rail, match_evidence, compliance_drafts, composition
    as finance_admin:
      purpose: "Settle pad — failed rail does not move the invoice; retry here. Intake, due stages, settle rail, match evidence"
      focus: settle_metrics, past_due, ready_to_pay, draft_invoice_queue, awaiting_approval_queue, document_pulse, draft_packets, settle_rail, match_evidence, compliance_drafts, composition

  settle_board:
    source: Invoice
    filter: status = approved or status = disputed or status = paid
    display: kanban
    group_by: status
    sort: due_date asc
    action: invoice_detail
    empty: "No invoices in settle pipeline"
# Eighth product workspace: payment trail desk.
workspace payments_trail "Payments":
  purpose: "Payment attempt trail — health metrics and recent attempts"
  access: persona(finance, finance_admin, auditor)

  payment_pulse:
    source: PaymentAttempt
    display: metrics
    aggregate:
      attempts: count(PaymentAttempt)
      invoices: count(Invoice)
      paid: count(Invoice where status = paid)
    tones:
      paid: positive
      attempts: accent

  recent_attempts:
    source: PaymentAttempt
    sort: created_at desc
    limit: 25
    display: queue
    empty: "No payment attempts yet"

  settled:
    source: Invoice
    filter: status = paid
    sort: updated_at desc
    limit: 15
    display: timeline
    action: invoice_detail
    empty: "No paid invoices yet"

  ready_context:
    source: Invoice
    filter: status = approved
    sort: amount desc
    limit: 10
    display: queue
    action: invoice_detail
    empty: "Nothing ready to pay"

  settle_board:
    source: Invoice
    filter: status = approved or status = disputed or status = paid
    display: kanban
    group_by: status
    sort: amount desc
    action: invoice_detail
    empty: "No invoices in settle pipeline"

  attempt_health:
    source: PaymentAttempt
    display: bar_chart
    group_by: status
    aggregate:
      count: count(PaymentAttempt)
    empty: "No payment attempts"
