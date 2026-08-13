module invoice_ops.surfaces

use invoice_ops.entities

# =============================================================================
# INVOICE SURFACES
# =============================================================================

surface invoice_list "Invoices":
  uses entity Invoice
  mode: list
  # Triple open (story_walk dig cycle 1597): invoice hub, supplier vendor,
  # submitter teammate (when submitted_by is set).
  open: Invoice via id | Supplier via supplier | User via submitted_by
  section main:
    field invoice_number "Number"
    field supplier "Supplier"
    field amount "Amount" format: currency:GBP
    field due_date "Due"
    field currency "Currency"
    field status "Status"
    # Goal B document (cycle 1921): dispute reason on the list row so controllers
    # scan exception prose without opening every disputed hub (Bill.com peer).
    field dispute_reason "Dispute"
    field submitted_by "Submitted By"
  ux:
    purpose: "Browse invoices — amount, due, vendor, and dispute reason on the work row; open hub, supplier, or submitter"

surface invoice_detail "Invoice":
  uses entity Invoice
  mode: view
  section summary "Summary":
    field invoice_number "Number"
    field supplier "Supplier"
    field amount "Amount" format: currency:GBP
    field currency "Currency"
    field due_date "Due Date"
  section status "Status":
    layout: strip
    field status "Status"
    field po_number "PO Number"
    field due_date "Due Date"
    # Dispute grain above the fold on the hub strip (not only buried review notes).
    field dispute_reason "Dispute Reason"
  section review "Review notes":
    field rejection_reason "Rejection Reason"
    field dispute_reason "Dispute Reason"
    field submitted_by "Submitted By"
  # Document composition (Goal B): line items are the invoice body, not a
  # warehouse table — ST-002/003/005 acceptance path scans composition then
  # settlement trail.
  related lines "Line items":
    display: queue
    show: LineItem
    # Goal B document peer-pack (cycle 1900): tax + PO match on composition rows.
    columns: description, quantity, unit_amount, tax_code, po_match
    limit: 8
  # Goal B document: named AP packets (remittance / credit memo / PO) on the hub.
  related documents "Documents":
    display: queue
    show: InvoiceDocument
    columns: headline, doc_kind, status, author
    limit: 6
  related payments "Payment attempts":
    display: queue
    show: PaymentAttempt
    columns: attempt_number, status, failure_reason, created_at
    limit: 5
  # Goal B conversation (cycle 1899 hub wave): invoice hub Discussion uses
  # RelatedDisplayMode.conversation → Message/Bubble chrome (AP desk
  # live_conversation parity). Peer AP tools show discussion copy as a
  # content-first trail on the invoice — not queue meta rows.
  related discussion "Discussion":
    display: conversation
    show: InvoiceNote
    columns: body, author, created_at
    limit: 5
  ux:
    purpose: "Invoice document — header, line composition, named packets, discussion, and payment trail"

surface invoice_create "New Invoice":
  uses entity Invoice
  mode: create
  section main:
    field invoice_number "Number"
    field supplier "Supplier"
    field amount "Amount"
    field currency "Currency"
    field due_date "Due Date"
    field po_number "PO Number"

surface invoice_note_list "Invoice Notes":
  uses entity InvoiceNote
  mode: list
  open: InvoiceNote via id | Invoice via invoice
  section main:
    field body "Note"
    field author "Author"
    field invoice "Invoice"
    field created_at "When"
  ux:
    purpose: "AP discussion — open a note or its parent invoice"
    sort: created_at desc
    search: body, author
    empty: "No invoice notes yet"

surface invoice_note_detail "Invoice Note":
  uses entity InvoiceNote
  mode: view
  section summary "Note":
    field body "Note"
    field author "Author"
    field invoice "Invoice"
    field created_at "When"
  ux:
    purpose: "Read an AP discussion note in context of its parent invoice"

surface invoice_note_create "Add Invoice Note":
  uses entity InvoiceNote
  mode: create
  section main:
    field invoice "Invoice"
    field author "Author"
    field body "Note"

# =============================================================================
# SUPPLIER SURFACES
# =============================================================================

surface supplier_list "Suppliers":
  uses entity Supplier
  mode: list
  # Dual open: supplier hub first, tenant root second (multi-tenant AP admin).
  open: Supplier via id | Tenant via tenant_id
  section main:
    field name "Name"
    field contact_email "Contact"
    field region "Region"
  ux:
    purpose: "Browse suppliers by region — open supplier hub or hop to tenant root"
    filter: region
    search: name, contact_email, region
    sort: name asc

surface supplier_detail "Supplier":
  uses entity Supplier
  mode: view
  section identity "Identity":
    field name "Name"
    field contact_email "Contact"
    field region "Region"
  related bank "Bank accounts":
    display: queue
    show: SupplierBankAccount
  related invoices "Invoices":
    display: queue
    show: Invoice
    columns: invoice_number, amount, status
  ux:
    purpose: "Supplier hub — identity, bank-ref queue, and invoice history queue"

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

# View surface so dual-open PaymentAttempt via id lands a readable attempt note.
surface payment_attempt_detail "Payment Attempt":
  uses entity PaymentAttempt
  mode: view
  section summary "Attempt":
    field invoice "Invoice"
    field attempt_number "Attempt"
    field status "Status"
  section provider "Provider":
    layout: strip
    field provider_reference "Provider reference"
    field failure_reason "Failure Reason"
  ux:
    purpose: "Read one settlement attempt with invoice context"

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
# AUDIT EXPORT SURFACE
# =============================================================================

# NOTE: a second `mode: list` surface on Invoice (e.g. an "Audit Export" view)
# can't be reached — it resolves to the same GET /invoices route as invoice_list
# and is dropped at boot (#1489). For a secondary invoice view, use a workspace
# region or a filtered list, not a second list surface on the same entity.

# =============================================================================
# TENANT SURFACES
# =============================================================================

surface tenant_list "Tenants":
  uses entity Tenant
  mode: list
  open: Tenant via id
  section main:
    field name "Name"
    field region "Region"
    field status "Status"
  ux:
    purpose: "Tenant roster — open a row for the tenant hub"

surface tenant_detail "Tenant":
  uses entity Tenant
  mode: view
  section identity "Identity":
    field name "Name"
    field slug "Slug"
  section ops "Ops":
    layout: strip
    field region "Region"
    field status "Status"
  related people "Users":
    display: queue
    show: User
    columns: name, email
  related suppliers "Suppliers":
    display: queue
    show: Supplier
    columns: name, region, contact_email
  ux:
    purpose: "Tenant hub — identity, people queue, and supplier roster queue"

# =============================================================================
# USER SURFACES
# =============================================================================

surface user_list "Users":
  uses entity User
  mode: list
  # Dual open: person hub first, tenant root second (admin roster context).
  open: User via id | Tenant via tenant_id
  section main:
    field photo_url "Photo"
    field email "Email"
    field name "Name"
    field job_title "Job Title"
    field department "Department"
    field tenant_id "Tenant"
  ux:
    purpose: "Team roster — open person hub or hop to tenant root"
    sort: department asc, name asc
    filter: department, job_title
    search: name, email, department, job_title

surface user_detail "User":
  uses entity User
  mode: view
  section identity "Identity":
    field photo_url "Photo"
    field name "Name"
    field email "Email"
  section org "Org placement":
    layout: strip
    field job_title "Job Title"
    field department "Department"
  section tenant_link "Tenant":
    layout: strip
    field tenant_id "Tenant"
  related invoices_raised "Invoices raised":
    display: queue
    show: Invoice
    columns: invoice_number, amount, status
  ux:
    purpose: "Person hub — identity, org placement, and submitted-invoice pull queue"

# =============================================================================
# LINE ITEM SURFACES
# =============================================================================

surface line_item_list "Line Items":
  uses entity LineItem
  mode: list
  # Triple open: line hub, parent invoice, tenant root (ST-005 path + multi-tenant AP).
  open: LineItem via id | Invoice via invoice | Tenant via tenant_id
  section main:
    field invoice "Invoice"
    field description "Description"
    field quantity "Qty"
    field unit_amount "Unit Amount" format: currency:GBP
    field tax_code "Tax"
    field po_match "PO Match"
  ux:
    purpose: "Document lines — tax + PO match grain; open a row for the line, parent invoice, or tenant root"

# Explicit VIEW so related-table drills and synthetic #1421 detail routes
# share one authored surface (substrate + sections) instead of an empty shell.
surface lineitem_detail "Line Item":
  uses entity LineItem
  mode: view
  section main "Line":
    field invoice "Invoice"
    field description "Description"
    field quantity "Qty"
    field unit_amount "Unit Amount" format: currency:GBP
    field tax_code "Tax Code"
    field po_match "PO Match"
  ux:
    purpose: "One line on an invoice document — tax/PO match grain; hop to parent invoice for composition + settlement"

# =============================================================================
# INVOICE DOCUMENT SURFACES (Goal B document composition — named AP packets)
# =============================================================================

surface invoice_document_list "Invoice Documents":
  uses entity InvoiceDocument
  mode: list
  # Dual open: document hub first; parent Invoice document second.
  open: InvoiceDocument via id | Invoice via invoice
  section main:
    field preview_url "Cover"
    field headline "Headline"
    field invoice "Invoice"
    field doc_kind "Kind"
    field status "Status"
    field author "Author"
    field created_at "Created"
  ux:
    purpose: "Scan remittance, credit memos, and PO packets — open a row for the packet or parent invoice"
    sort: created_at desc
    filter: doc_kind, status
    search: headline, body, author
    empty: "No invoice documents yet — attach a remittance or PO packet on an invoice hub"

surface invoice_document_detail "Invoice Document":
  uses entity InvoiceDocument
  mode: view
  section summary "Document":
    field preview_url "Cover"
    field headline "Headline"
    field invoice "Invoice"
    field doc_kind "Kind"
    field author "Author"
  section lifecycle "Lifecycle":
    layout: strip
    field status "Status"
    field created_at "Created"
  section body "Body":
    field body "Body"
  ux:
    purpose: "Invoice document hub — named packet, cover, lifecycle strip, parent invoice, and body in one place"

surface invoice_document_create "Add Invoice Document":
  uses entity InvoiceDocument
  mode: create
  section main "New document":
    field invoice "Invoice"
    field headline "Headline"
    field doc_kind "Kind"
    field body "Body"
    field preview_url "Cover URL"
    field status "Status"
    field author "Author"
  ux:
    purpose: "Attach a named remittance, credit memo, or PO packet to an invoice"

surface invoice_document_edit "Edit Invoice Document":
  uses entity InvoiceDocument
  mode: edit
  section main "Edit document":
    field headline "Headline"
    field doc_kind "Kind"
    field body "Body"
    field preview_url "Cover URL"
    field status "Status"
    field author "Author"
  ux:
    purpose: "Update invoice document headline, kind, cover, or status"

# =============================================================================
# INVOICE EDIT SURFACE — generates PUT /invoices/{id} + drives state machine
# =============================================================================

surface invoice_edit "Edit Invoice":
  uses entity Invoice
  mode: edit
  section main:
    field invoice_number "Number"
    field supplier "Supplier"
    field amount "Amount"
    field currency "Currency"
    field due_date "Due Date"
    field po_number "PO Number"
    field status "Status"
    field rejection_reason "Rejection Reason"
    field dispute_reason "Dispute Reason"

# =============================================================================
# SUPPLIER CREATE / EDIT SURFACES — tenant_admin & finance manage suppliers
# =============================================================================

surface supplier_create "New Supplier":
  uses entity Supplier
  mode: create
  section main:
    field name "Name"
    field contact_email "Contact"
    field region "Region"

surface supplier_edit "Edit Supplier":
  uses entity Supplier
  mode: edit
  section main:
    field name "Name"
    field contact_email "Contact"
    field region "Region"

surface supplier_bank_account_list "Supplier Bank Accounts":
  uses entity SupplierBankAccount
  mode: list
  # Triple open: bank-ref hub, supplier hub, tenant root (finance isolation path).
  open: SupplierBankAccount via id | Supplier via supplier | Tenant via tenant_id
  section main:
    field supplier "Supplier"
    field bank_account_ref "Bank Ref"
    field account_name "Account Name"
  ux:
    purpose: "Bank refs — open a row for the bank hub, parent supplier hub, or tenant root"

surface supplier_bank_account_detail "Supplier Bank Account":
  uses entity SupplierBankAccount
  mode: view
  section summary "Account":
    field supplier "Supplier"
    field bank_account_ref "Bank Ref"
    field account_name "Account Name"
  ux:
    purpose: "Read one supplier bank reference with supplier context"

surface supplier_bank_account_edit "Edit Supplier Bank Account":
  uses entity SupplierBankAccount
  mode: edit
  section main:
    field bank_account_ref "Bank Ref"
    field account_name "Account Name"
    field iban "IBAN"

# =============================================================================
# USER CREATE / EDIT SURFACES — tenant_admin manages domain users
# (user_edit deliberately omits tenant_id — users must not be moved between tenants)
# =============================================================================

surface user_create "New User":
  uses entity User
  mode: create
  section main:
    field photo_url "Photo URL"
    field email "Email"
    field name "Name"
    field job_title "Job Title"
    field department "Department"
    field tenant_id "Tenant"

surface user_edit "Edit User":
  uses entity User
  mode: edit
  section main:
    field photo_url "Photo URL"
    field email "Email"
    field name "Name"
    field job_title "Job Title"
    field department "Department"

# =============================================================================
# LINE ITEM CREATE SURFACE — requester adds line items to an invoice
# =============================================================================

surface lineitem_create "New Line Item":
  uses entity LineItem
  mode: create
  section main:
    field invoice "Invoice"
    field description "Description"
    field quantity "Qty"
    field unit_amount "Unit Amount"
    field tax_code "Tax Code"
    field po_match "PO Match"

# ── Finance operations workspace (#1537) ─────────────────────────────────────
# The app's home surface for fleet capture rounds: a persona-homed
# workspace (the framework-injected `_platform_admin` is gated to
# framework roles and is never a capture target).
# Story-driven (docs/guides/story-to-composition.md): metrics + review
# queues — not bare invoice lists named "queue".
workspace finance_ops "Finance Operations":
  # Goal B document peer-pack (cycle 1892) + conversation + empty_region:
  # Bill.com / Melio / Tipalti put remittance / PO / tax packet covers on the
  # money desk first — not teammate headshot shelves (peer refuse). Dual
  # attention, line composition, and live discussion follow the packet wall.
  # Cycle 1909: due-date / past-due work rows (amount + due + vendor pressure).
  purpose: "Day-to-day invoice throughput — packet covers, draft gate, compliance drafts, tax certs, PO packets, dispute packets, past-due pressure, dual attention, named packets, line composition, and live discussion"
  access: persona(requester, approver, finance, finance_admin, auditor, tenant_admin)

  # Goal B document FIRST — recipe packet_cover_wall (novel vs headshot_shelf).
  # Peer money desks show remittance/PO cover thumbs before metrics and queues.
  packet_covers:
    source: InvoiceDocument
    filter: preview_url != null
    display: grid
    sort: created_at desc
    limit: 4
    action: invoice_document_detail
    empty: "No packet covers yet — attach remittance or PO packets with cover previews"

  ops_metrics:
    source: Invoice
    display: metrics
    aggregate:
      submitted: count(Invoice where status = submitted)
      approved: count(Invoice where status = approved)
      past_due: count(Invoice where due_date < today and status != paid and status != rejected and status != draft)
      disputed: count(Invoice where status = disputed)
      conversation: count(InvoiceNote)
    tones:
      submitted: warning
      past_due: destructive
      disputed: destructive
      conversation: accent
      approved: accent

  # Goal B document metric — named AP packets only (InvoiceDocument source).
  # Cross-entity count(LineItem) / count(Invoice) under this source paints 0
  # theater; line body pulse lives on line_items_desk / my_invoices.
  document_pulse:
    source: InvoiceDocument
    display: metrics
    aggregate:
      documents: count(InvoiceDocument)
      published: count(InvoiceDocument where status = published)
      draft: count(InvoiceDocument where status = draft)
      tax_certs: count(InvoiceDocument where doc_kind = tax_certificate)
      po_packs: count(InvoiceDocument where doc_kind = po_packet)
      goods_receipts: count(InvoiceDocument where doc_kind = goods_receipt)
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
      remittances: count(InvoiceDocument where doc_kind = remittance)
      dispute_packets: count(InvoiceDocument where doc_kind = dispute_packet)
    tones:
      documents: accent
      published: positive
      draft: warning
      tax_certs: accent
      po_packs: accent
      goods_receipts: accent
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
      remittances: accent
      dispute_packets: destructive

  # Peer-pack document upgrade (cycle 1957): Bill.com / Melio / Tipalti
  # "release gate" — draft remittance/credit packets must publish before
  # settle (recipe draft_packet_release_gate; not packet_cover_wall re-stack).
  draft_packets:
    source: InvoiceDocument
    filter: status = draft
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No draft packets — every remittance and credit memo is published or archived"

  # Peer-pack document upgrade (cycle 2000): Bill.com / Melio / Tipalti
  # compliance draft gate — vendor onboarding packets still draft (W-9 / COI /
  # reverse-charge tax / lien / ACH) before first settle. Compound status+kind
  # filter (recipe compliance_draft_gate; not form_w9-only or all-draft re-stack).
  compliance_drafts:
    source: InvoiceDocument
    filter: status = draft and (doc_kind = form_w9 or doc_kind = insurance_certificate or doc_kind = tax_certificate or doc_kind = lien_waiver or doc_kind = ach_authorization)
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No compliance drafts — W-9, COI, tax cert, lien, and ACH packets are published"

  # Peer-pack document upgrade (cycle 1965): Bill.com / Coupa / Tipalti PO
  # packet watch — signed PO cover before approve/ops (recipe po_packet_watch;
  # not tax_cert / draft_packet / payment_confirmation re-stack). Above tax
  # certs so finance_ops hero stills can read PO packet titles when focused.
  po_packets:
    source: InvoiceDocument
    filter: doc_kind = po_packet
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No PO packets on file — attach signed PO covers before approve"

  # Peer-pack document upgrade (cycle 1959): Bill.com / Tipalti reverse-charge
  # tax certificates controllers lean into before approve/settle
  # (recipe tax_certificate_watch; not draft_packet re-stack).
  tax_certificates:
    source: InvoiceDocument
    filter: doc_kind = tax_certificate
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No tax certificates on file — attach reverse-charge certs before approve"

  # Peer-pack document upgrade (cycle 1967): Coupa / Tipalti / Bill.com
  # three-way match — goods receipts close PO+invoice before approve
  # (recipe goods_receipt_match; not PO/tax/payment packet re-stack).
  goods_receipts:
    source: InvoiceDocument
    filter: doc_kind = goods_receipt
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No goods receipts on file — attach receiving slips for three-way match"

  # Peer-pack document upgrade (cycle 1971): Bill.com / Melio / Tipalti credit
  # memo watch — VAT/short-ship credits before settle (recipe credit_memo_watch;
  # not goods_receipt / PO / tax / payment re-stack).
  credit_memos:
    source: InvoiceDocument
    filter: doc_kind = credit_memo
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No credit memos on file — attach VAT or short-ship credits before settle"

  # Peer-pack document upgrade (cycle 1974): Bill.com / Melio remittance advice
  # watch — SEPA/ACH remittance covers before settle (recipe remittance_advice_watch;
  # not credit_memo / goods_receipt / payment_confirmation re-stack).
  remittances:
    source: InvoiceDocument
    filter: doc_kind = remittance
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No remittance advice on file — attach SEPA/ACH remittance covers before settle"

  # Peer-pack document upgrade (cycle 1978): Bill.com / Melio / Tipalti dispute
  # evidence packets — GRN mismatch / missing tax cert / closed PO covers before
  # re-approve (recipe dispute_packet_watch; not remittance/credit/goods re-stack).
  dispute_packets:
    source: InvoiceDocument
    filter: doc_kind = dispute_packet
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No dispute packets on file — attach exception evidence when invoices are disputed"

  # Peer-pack document upgrade (cycle 1981): Bill.com / Melio / Tipalti debit
  # memo watch — vendor-issued additional charges (fuel surcharge / price fix)
  # opposite credit_memo (recipe debit_memo_watch; not credit/dispute re-stack).
  debit_memos:
    source: InvoiceDocument
    filter: doc_kind = debit_memo
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No debit memos on file — attach vendor additional-charge memos before settle"

  # Peer-pack document upgrade (cycle 1983): Bill.com / Melio / Tipalti vendor
  # statement watch — period-end AP reconcile covers before settle batch
  # (recipe vendor_statement_watch; not remittance/debit/dispute re-stack).
  vendor_statements:
    source: InvoiceDocument
    filter: doc_kind = vendor_statement
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No vendor statements on file — attach period-end statements before reconcile"

  # Peer-pack document upgrade (cycle 1985): Bill.com / Coupa / Tipalti packing
  # slip watch — carrier packing slips for three-way match with PO/GRN
  # (recipe packing_slip_watch; not goods_receipt / PO re-stack).
  packing_slips:
    source: InvoiceDocument
    filter: doc_kind = packing_slip
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No packing slips on file — attach carrier packing slips for three-way match"

  # Peer-pack document upgrade (cycle 1987): Bill.com / Melio / Tipalti ACH
  # authorization watch — signed ACH auth before first SEPA/ACH settle
  # (recipe ach_authorization_watch; not remittance / payment_confirmation re-stack).
  ach_authorizations:
    source: InvoiceDocument
    filter: doc_kind = ach_authorization
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No ACH authorizations on file — attach signed ACH auth before first settle"

  # Peer-pack document upgrade (cycle 1989): Bill.com / Melio / Tipalti wire
  # instructions watch — bank wire details before first high-value wire release
  # (recipe wire_instructions_watch; not ACH mandate / payment_confirmation re-stack).
  wire_instructions:
    source: InvoiceDocument
    filter: doc_kind = wire_instructions
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No wire instructions on file — attach bank wire details before first wire release"

  # Peer-pack document upgrade (cycle 1991): Bill.com / Melio / Tipalti lien
  # waiver watch — conditional/final lien waivers before construction or facility
  # pay release (recipe lien_waiver_watch; not wire/ACH/tax re-stack).
  lien_waivers:
    source: InvoiceDocument
    filter: doc_kind = lien_waiver
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No lien waivers on file — attach conditional or final waivers before pay release"

  # Peer-pack document upgrade (cycle 1993): Bill.com / Melio / Tipalti
  # insurance certificate (COI) watch — proof of insurance on file before
  # contractor/facility pay release (recipe insurance_certificate_watch; not
  # lien_waiver / wire / ACH re-stack).
  insurance_certificates:
    source: InvoiceDocument
    filter: doc_kind = insurance_certificate
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No insurance certificates on file — attach COI before contractor pay release"

  # Peer-pack document upgrade (cycle 1995): Bill.com / Melio / Tipalti Form
  # W-9 watch — IRS W-9 / vendor TIN on file before first US settle (recipe
  # form_w9_watch; not tax_certificate reverse-charge / COI / ACH re-stack).
  form_w9s:
    source: InvoiceDocument
    filter: doc_kind = form_w9
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No Form W-9 on file — collect vendor TIN before first US settle"

  # Goal B document composition AFTER cover wall — named remittance /
  # credit memo / PO packets so hero stills also read packet titles in queue.
  composition:
    source: InvoiceDocument
    sort: created_at desc
    limit: 5
    display: queue
    action: invoice_document_detail
    empty: "No invoice documents yet — attach a remittance or PO packet on an invoice hub"

  # Dual attention after named packets (fold share with capped conversation).
  # Goal B document (cycle 1909): sort by due_date so SLA pressure is visible.
  awaiting_approval:
    source: Invoice
    filter: status = submitted
    sort: due_date asc
    limit: 3
    display: queue
    action: invoice_detail
    empty: "Nothing awaiting approval"

  ready_to_pay:
    source: Invoice
    filter: status = approved
    sort: due_date asc
    limit: 3
    display: queue
    action: invoice_detail
    empty: "Nothing ready to pay"

  # Peer AP desks put past-due open invoices above the fold (amount + due + vendor).
  past_due:
    source: Invoice
    filter: due_date < today and status != paid and status != rejected and status != draft
    sort: due_date asc
    limit: 4
    display: queue
    action: invoice_detail
    empty: "No past-due open invoices"

  # Line body under dual attention (still domain-true composition, not warehouse).
  line_composition:
    source: LineItem
    sort: created_at desc
    limit: 4
    display: queue
    action: invoice_detail
    empty: "No line items yet — add lines to a draft invoice"

  # Goal B conversation spine AFTER packets + dual attention.
  # display: conversation → MessageScroller / Message + Bubble (not queue meta rows).
  live_conversation:
    source: InvoiceNote
    sort: created_at desc
    limit: 4
    display: conversation
    action: invoice_note_detail
    empty: "No conversation yet — approval and payment notes appear here"

  disputed_queue:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 8
    display: queue
    action: invoice_detail
    empty: "No disputes open"

  ops_board:
    source: Invoice
    filter: status != draft
    display: kanban
    group_by: status
    sort: due_date asc
    action: invoice_detail
    empty: "No invoices in the pipeline"

  ux:
    as finance_admin:
      purpose: "AP ops — packet covers, compliance draft gate, W-9 + remittance watch, past-due, dual attention"
      focus: packet_covers, ops_metrics, document_pulse, draft_packets, compliance_drafts, remittances, form_w9s, packing_slips, composition, past_due, awaiting_approval
    as tenant_admin:
      purpose: "AP ops — packet covers, compliance draft gate, W-9 + remittance watch, past-due, dual attention"
      focus: packet_covers, ops_metrics, document_pulse, draft_packets, compliance_drafts, remittances, form_w9s, packing_slips, composition, past_due, awaiting_approval
    as finance:
      purpose: "AP ops — packet covers, compliance draft gate, W-9 + remittance watch, past-due settle pressure"
      focus: packet_covers, ops_metrics, document_pulse, draft_packets, compliance_drafts, remittances, form_w9s, packing_slips, composition, past_due, ready_to_pay
    as approver:
      purpose: "AP ops — packet covers, compliance draft gate, W-9 + remittance watch, past-due + review queues"
      focus: packet_covers, ops_metrics, document_pulse, draft_packets, compliance_drafts, remittances, form_w9s, packing_slips, composition, past_due, awaiting_approval
    as auditor:
      purpose: "AP ops — packet covers, compliance draft gate, W-9 + remittance watch, settle packets"
      focus: packet_covers, ops_metrics, document_pulse, draft_packets, compliance_drafts, remittances, form_w9s, packing_slips, composition, past_due, disputed_queue
    as requester:
      purpose: "AP ops overview — packet covers, packets, lines, and conversation"
      focus: packet_covers, ops_metrics, composition, past_due, line_composition, live_conversation, awaiting_approval

# ── Job workspaces (product maturity: anti-warehouse) ────────────────────────
# Separate product landings per role so density is not one mega-desk + 9 lists.
# finance_ops remains the shared ops overview for admin/oversight personas.

workspace my_invoices "My Invoices":
  # Goal B document + empty_region (cycle 1820): requester home shows line
  # composition + draft/submit queues + kanban — not status bar-chart voids or
  # twin invoice timelines under the fold.
  purpose: "Requester desk — line composition, drafts, submissions, and line-item work on my invoices"
  access: persona(requester)

  my_pipeline:
    source: Invoice
    display: metrics
    aggregate:
      draft: count(Invoice where status = draft)
      submitted: count(Invoice where status = submitted)
      approved: count(Invoice where status = approved)
      paid: count(Invoice where status = paid)
    tones:
      draft: warning
      submitted: accent
      paid: positive

  # Goal B document metric from LineItem source (honest line count).
  document_pulse:
    source: LineItem
    display: metrics
    aggregate:
      documents: count(LineItem)
    tones:
      documents: accent

  # Goal B document spine on requester home — composition lines pull open the
  # parent invoice document hub (description as title).
  composition:
    source: LineItem
    sort: created_at desc
    limit: 12
    display: queue
    action: invoice_detail
    empty: "No line items yet — add lines to a draft invoice"

  drafts:
    source: Invoice
    filter: status = draft
    sort: updated_at desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "No draft invoices — create one to get started"

  in_flight:
    source: Invoice
    filter: status = submitted
    sort: amount desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "Nothing waiting on approval"

  my_status_board:
    source: Invoice
    filter: status = draft or status = submitted or status = approved or status = paid
    display: kanban
    group_by: status
    sort: updated_at desc
    action: invoice_detail
    empty: "No invoices yet"

  suppliers_nearby:
    source: Supplier
    sort: name asc
    limit: 10
    display: queue
    action: supplier_detail
    empty: "No suppliers yet"

  ux:
    as requester:
      purpose: "My invoices — composition and draft/submit queues (no chart voids)"
      focus: my_pipeline, document_pulse, composition, drafts, in_flight, my_status_board

workspace approval_desk "Approval Desk":
  # Goal B document (cycle 1879): peer AP approval homes (Bill.com / Coupa)
  # put named remittance / PO packets above the discussion trail — not notes-only.
  # Cycle 1959: tax certificate watch before approve (reverse-charge lean-in).
  # Cycle 1965: PO packet watch — signed PO cover before approve (Coupa lean-in).
  # Cycle 1967: goods receipt three-way match before approve (Tipalti lean-in).
  purpose: "Approver job — goods receipt + PO/tax watch, awaiting queue, named AP packets, then live discussion"
  access: persona(approver, finance_admin)

  approval_load:
    source: Invoice
    display: metrics
    aggregate:
      awaiting: count(Invoice where status = submitted)
      approved: count(Invoice where status = approved)
      conversation: count(InvoiceNote)
    tones:
      awaiting: warning
      approved: positive
      conversation: accent

  # Honest document counts — source InvoiceDocument (not cross-entity under Invoice).
  document_pulse:
    source: InvoiceDocument
    display: metrics
    aggregate:
      documents: count(InvoiceDocument)
      published: count(InvoiceDocument where status = published)
      tax_certs: count(InvoiceDocument where doc_kind = tax_certificate)
      po_packs: count(InvoiceDocument where doc_kind = po_packet)
      goods_receipts: count(InvoiceDocument where doc_kind = goods_receipt)
    tones:
      documents: accent
      published: positive
      tax_certs: accent
      po_packs: accent
      goods_receipts: accent

  # Peer-pack goods_receipt_match (cycle 1967) — three-way match receipts before
  # approve (Coupa / Tipalti / Bill.com; not PO/tax/payment re-stack).
  goods_receipts:
    source: InvoiceDocument
    filter: doc_kind = goods_receipt
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No goods receipts — attach receiving slips for three-way match"

  # Peer-pack po_packet_watch (cycle 1965) — signed PO covers before approve
  # (Bill.com / Coupa / Tipalti; not tax_cert or payment_confirmation re-stack).
  # Placed above tax certs so hero stills read PO packet titles above the fold.
  po_packets:
    source: InvoiceDocument
    filter: doc_kind = po_packet
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No PO packets — attach signed PO covers before approve"

  # Peer-pack tax_certificate_watch (cycle 1959) — reverse-charge certs before
  # approve (Bill.com / Tipalti controller lean-in; not composition re-stack).
  tax_certificates:
    source: InvoiceDocument
    filter: doc_kind = tax_certificate
    sort: created_at desc
    limit: 6
    display: queue
    action: invoice_document_detail
    empty: "No tax certificates — attach reverse-charge certs before approve"

  # Goal B document composition — named packets before conversation trail.
  composition:
    source: InvoiceDocument
    sort: created_at desc
    limit: 5
    display: queue
    action: invoice_document_detail
    empty: "No invoice documents yet — attach a remittance or PO packet on an invoice hub"

  awaiting_approval:
    source: Invoice
    filter: status = submitted
    sort: due_date asc
    limit: 6
    display: queue
    action: invoice_detail
    empty: "Nothing awaiting approval"

  # display: conversation → Message/Bubble chrome (not queue meta of note rows).
  live_conversation:
    source: InvoiceNote
    sort: created_at desc
    limit: 6
    display: conversation
    action: invoice_note_detail
    empty: "No conversation yet — notes on invoices in review appear here"

  approval_board:
    source: Invoice
    filter: status = submitted or status = approved or status = rejected
    display: kanban
    group_by: status
    sort: due_date asc
    action: invoice_detail
    empty: "No invoices in the approval pipeline"

  suppliers_nearby:
    source: Supplier
    sort: name asc
    limit: 12
    display: queue
    action: supplier_detail
    empty: "No suppliers yet"

  ux:
    as approver:
      purpose: "Approval — goods receipt + PO/tax watch, named packets, queue, conversation"
      focus: approval_load, document_pulse, goods_receipts, po_packets, composition, awaiting_approval, live_conversation
    as finance_admin:
      purpose: "Approval — goods receipt + PO/tax watch, named packets, queue, conversation"
      focus: approval_load, document_pulse, goods_receipts, po_packets, composition, awaiting_approval, live_conversation

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
  purpose: "Multi-panel settlement — draft gate, remittances, W-9, packing slips, payment confirmations, dual attention"
  access: persona(finance, finance_admin)

  settle_metrics:
    source: Invoice
    display: metrics
    aggregate:
      ready: count(Invoice where status = approved)
      past_due: count(Invoice where due_date < today and status != paid and status != rejected and status != draft)
      disputed: count(Invoice where status = disputed)
      conversation: count(InvoiceNote)
    tones:
      ready: accent
      past_due: destructive
      disputed: destructive
      conversation: accent

  # Honest document pulse (InvoiceDocument source — not cross-entity under Invoice).
  document_pulse:
    source: InvoiceDocument
    display: metrics
    aggregate:
      documents: count(InvoiceDocument)
      published: count(InvoiceDocument where status = published)
      draft: count(InvoiceDocument where status = draft)
      pay_confirms: count(InvoiceDocument where doc_kind = payment_confirmation)
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
      remittances: count(InvoiceDocument where doc_kind = remittance)
    tones:
      documents: accent
      published: positive
      draft: warning
      pay_confirms: positive
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
  # above dual attention so hero stills show titles above the fold.
  composition:
    source: InvoiceDocument
    sort: created_at desc
    limit: 4
    display: queue
    action: invoice_document_detail
    empty: "No invoice documents yet — attach remittance or payment confirmation"

  # Dual attention after named packets — due_date first (SLA settle pressure).
  ready_to_pay:
    source: Invoice
    filter: status = approved
    sort: due_date asc
    limit: 3
    display: queue
    action: invoice_detail
    empty: "Nothing ready to pay"

  past_due:
    source: Invoice
    filter: due_date < today and status != paid and status != rejected and status != draft
    sort: due_date asc
    limit: 3
    display: queue
    action: invoice_detail
    empty: "No past-due open invoices"

  disputed_queue:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 3
    display: queue
    action: invoice_detail
    empty: "No disputes open"

  # Goal B conversation spine AFTER packets + dual attention.
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
      purpose: "Multi-panel settlement — compliance draft gate, remittances, W-9, dual attention"
      focus: settle_metrics, document_pulse, draft_packets, compliance_drafts, remittances, form_w9s, packing_slips, composition, ready_to_pay
    as finance_admin:
      purpose: "Multi-panel settlement — compliance draft gate, remittances, W-9, dual attention"
      focus: settle_metrics, document_pulse, draft_packets, compliance_drafts, remittances, form_w9s, packing_slips, composition, ready_to_pay

  settle_board:
    source: Invoice
    filter: status = approved or status = disputed or status = paid
    display: kanban
    group_by: status
    sort: due_date asc
    action: invoice_detail
    empty: "No invoices in settle pipeline"

workspace audit_review "Audit Review":
  # Goal B document peer-pack upgrade (cycle 1942): Bill.com / Tipalti audit
  # desks put named remittance / PO / tax packet covers + composition above the
  # payment trail — not chart theater or trail-only evidence (recipe
  # audit_evidence_packets; not conversation re-stack after 1940).
  purpose: "Auditor job — evidence packets first, then payment trail without warehouse CRUD"
  access: persona(auditor, finance_admin, tenant_admin)

  # Document pulse first — evidence volume buyers scan before attempt timelines.
  document_pulse:
    source: InvoiceDocument
    display: metrics
    aggregate:
      documents: count(InvoiceDocument)
      published: count(InvoiceDocument where status = published)
      disputed: count(Invoice where status = disputed)
      paid: count(Invoice where status = paid)
    tones:
      documents: accent
      published: positive
      disputed: destructive
      paid: positive

  # Goal B document FIRST — packet covers (preview thumbs) before trail dumps.
  packet_covers:
    source: InvoiceDocument
    filter: preview_url != null
    sort: created_at desc
    limit: 6
    display: grid
    action: invoice_document_detail
    empty: "No packet covers yet — attach remittance or PO packets with cover previews"

  # Named AP packets (remittance / credit memo / PO / tax) — composition titles.
  composition:
    source: InvoiceDocument
    sort: created_at desc
    limit: 8
    display: queue
    action: invoice_document_detail
    empty: "No invoice documents yet — attach a remittance or PO packet on an invoice hub"

  # Disputed work rows after evidence packets (payment/approval state on the row).
  disputed_queue:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 8
    display: queue
    action: invoice_detail
    empty: "No disputes open"

  # Work-surface utility: payment attempts are dated events → timeline (under-fold).
  payment_attempts:
    source: PaymentAttempt
    display: timeline
    sort: created_at desc
    limit: 12
    empty: "No payment attempts to review"

  settled_invoices:
    source: Invoice
    filter: status = paid
    sort: updated_at desc
    limit: 10
    display: queue
    action: invoice_detail
    empty: "No paid invoices yet"

  # Under-fold chart dogfood — not in multi-panel focus spine (empty_region honesty).
  audit_mix:
    source: Invoice
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices to chart"

  audit_board:
    source: Invoice
    filter: status = paid or status = disputed or status = rejected
    display: kanban
    group_by: status
    sort: updated_at desc
    action: invoice_detail
    empty: "No invoices in the audit trail"

  ux:
    as auditor:
      purpose: "Evidence packets + composition before payment trail — multi-panel audit desk"
      focus: document_pulse, packet_covers, composition, disputed_queue, payment_attempts, settled_invoices
    as finance_admin:
      purpose: "Evidence packets + composition before payment trail — multi-panel audit desk"
      focus: document_pulse, packet_covers, composition, disputed_queue, payment_attempts, settled_invoices
    as tenant_admin:
      purpose: "Evidence packets + composition before payment trail — multi-panel audit desk"
      focus: document_pulse, packet_covers, composition, disputed_queue, payment_attempts, settled_invoices

# Sixth product workspace: supplier / vendor desk so list shells
# no longer dominate vs job workspaces (vendors + bank refs, not bare CRUD).
# Goal B org_structure (cycle 1863): peer AP tools (Tipalti / Bill.com / Coupa)
# show vendor geography and multi-invoice supplier load before a flat A–Z
# roster + status bar dump — buyers call suppliers by region and account load.
workspace suppliers_desk "Suppliers":
  purpose: "Vendor org structure — region board and multi-invoice load before flat roster"
  access: persona(finance, tenant_admin, finance_admin, approver)

  vendor_pulse:
    source: Supplier
    display: metrics
    aggregate:
      suppliers: count(Supplier)
      bank_accounts: count(SupplierBankAccount)
      invoices: count(Invoice)
    tones:
      suppliers: accent

  # Region board — geographic org of the vendor book (EMEA / AMER / APAC).
  by_region:
    source: Supplier
    display: kanban
    group_by: region
    sort: name asc
    limit: 24
    action: supplier_detail
    empty: "No suppliers in this region"

  # Multi-invoice supplier placement — open AP load grouped by vendor before
  # flat recents (not a warehouse A–Z dump of invoices).
  by_supplier:
    source: Invoice
    filter: status != paid and status != rejected
    display: kanban
    group_by: supplier
    sort: amount desc
    limit: 30
    action: invoice_detail
    empty: "No open invoices by supplier"

  # Secondary flat roster after hierarchy.
  roster:
    source: Supplier
    display: queue
    sort: name asc
    limit: 25
    action: supplier_detail
    empty: "No suppliers yet"

  bank_refs:
    source: SupplierBankAccount
    display: queue
    limit: 20
    empty: "No bank accounts on file"

  recent_invoices:
    source: Invoice
    sort: updated_at desc
    limit: 12
    display: queue
    action: invoice_detail
    empty: "No invoices yet"

  ux:
    as finance:
      purpose: "Vendor org structure — region and multi-invoice load before flat roster"
      focus: vendor_pulse, by_region, by_supplier, roster, bank_refs
    as finance_admin:
      purpose: "Vendor org structure — region board then supplier AP load"
      focus: vendor_pulse, by_region, by_supplier, roster, bank_refs
    as tenant_admin:
      purpose: "Vendor org shape — region board then open invoices by supplier"
      focus: vendor_pulse, by_region, by_supplier, roster
    as approver:
      purpose: "See which region and supplier carries open AP before flat recents"
      focus: vendor_pulse, by_region, by_supplier, recent_invoices


# Seventh product workspace: tenant admin people desk.
workspace team_desk "Team":
  # Goal B org_structure (cycle 1863): peer AP tools (Coupa / Bill.com / NetSuite)
  # show finance staff by job title and department before open invoice load —
  # admins reassign and audit from org shape, not a flat people dump.
  purpose: "Org structure for AP — title and department before flat roster and open load"
  access: persona(tenant_admin, finance_admin, auditor)

  team_pulse:
    source: User
    display: metrics
    aggregate:
      people: count(User)
      suppliers: count(Supplier)
      open_invoices: count(Invoice where status = submitted or status = approved)
    tones:
      people: accent
      open_invoices: warning

  # Title board — Requester / Approver / Finance / Auditor columns.
  by_title:
    source: User
    display: kanban
    group_by: job_title
    sort: name asc
    limit: 40
    action: user_detail
    empty: "No titled staff yet"

  # Department placement — AP / Treasury / Controllership / Audit before flat roster.
  by_department:
    source: User
    display: queue
    sort: department asc, name asc
    limit: 40
    action: user_detail
    empty: "No staff placed in departments yet"

  # Secondary flat roster (after hierarchy).
  people:
    source: User
    display: queue
    sort: department asc, name asc
    limit: 25
    action: user_detail
    empty: "No users yet"

  # Open load after org shape — who owns pressure, not before hierarchy.
  open_invoices:
    source: Invoice
    filter: status = submitted or status = approved
    sort: amount desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "Nothing awaiting action"

  org_hint:
    display: status_list
    entries:
      - title: "By title board"
        caption: "Requester / Approver / Finance / Auditor columns show who can act"
        icon: "users"
        state: accent
      - title: "Department queue"
        caption: "AP / Treasury / Controllership / Audit placement before flat roster"
        icon: "building-2"
        state: positive
      - title: "Open load last"
        caption: "Submitted and approved invoices after you read org shape"
        icon: "file-text"
        state: warning

  ux:
    as tenant_admin:
      purpose: "See staff by title and department before open invoice load"
      focus: team_pulse, by_title, by_department, people
    as finance_admin:
      purpose: "Org structure for finance oversight — role board then department"
      focus: team_pulse, by_title, by_department, people
    as auditor:
      purpose: "Read team org shape before open invoice pressure"
      focus: team_pulse, by_title, by_department, people

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

# Ninth product workspace: invoice document composition desk (Goal B document).
# Peer tools (Bill.com / Tipalti) show line composition with invoice numbers —
# not UUID shells or bare CRUD lists.
workspace line_items_desk "Line Items":
  # Goal B document peer-pack (cycle 1900): recipe line_tax_po_match —
  # Bill.com / Melio controllers scan tax line + PO match boards, not bare
  # description queues that feel like a spreadsheet export.
  purpose: "Invoice document composition — tax + PO match grain, line body, open docs (not warehouse CRUD)"
  access: persona(requester, finance, finance_admin, auditor)

  line_pulse:
    source: LineItem
    display: metrics
    aggregate:
      lines: count(LineItem)
      matched: count(LineItem where po_match = matched)
      unmatched: count(LineItem where po_match = unmatched)
      open_invoices: count(Invoice where status != paid and status != rejected)
    tones:
      open_invoices: accent
      lines: positive
      matched: positive
      unmatched: destructive

  # Controller-true match board FIRST (still proof above the fold).
  po_match_board:
    source: LineItem
    display: kanban
    group_by: po_match
    sort: unit_amount desc
    action: invoice_detail
    empty: "No line items yet — add lines to a draft invoice"

  # Document body: composition lines pull open the parent invoice hub —
  # description as title; tax + PO match travel on the line entity.
  composition:
    source: LineItem
    sort: created_at desc
    limit: 25
    display: queue
    action: invoice_detail
    empty: "No line items yet — add lines to a draft invoice"

  # Open invoice documents still in flight (header roster under composition).
  open_documents:
    source: Invoice
    filter: status = draft or status = submitted or status = approved
    sort: updated_at desc
    limit: 15
    display: queue
    action: invoice_detail
    empty: "No open invoice documents"

  invoice_trail:
    source: Invoice
    sort: updated_at desc
    limit: 12
    display: timeline
    action: invoice_detail
    empty: "No invoices yet"

  ux:
    as requester:
      purpose: "Composition — PO match board, then line body (no bare spreadsheet theater)"
      focus: line_pulse, po_match_board, composition, open_documents
    as finance:
      purpose: "Composition — PO match board, unmatched grain, then line body"
      focus: line_pulse, po_match_board, composition, open_documents
    as finance_admin:
      purpose: "Composition — PO match board, unmatched grain, then line body"
      focus: line_pulse, po_match_board, composition, open_documents
    as auditor:
      purpose: "Composition evidence — PO match board then line body"
      focus: line_pulse, po_match_board, composition, open_documents

# Tenth product workspace: dedicated Disputes desk (SPEC + Goal B document).
# Peer AP tools (Bill.com / Melio / Tipalti) give controllers a dispute home
# where exception *reason* prose is the work grain — not status-only counts
# buried under packet walls on finance_ops.
workspace dispute_desk "Disputes":
  # Recipe dispute_reason_desk (cycle 1921): dispute pulse + reason-bearing
  # disputed queue before settle board / attempt trail / status mix.
  # Cycle 1978: dispute_packet_watch — named evidence packets (GRN / tax / PO)
  # before the exception queue (Bill.com / Melio / Tipalti controller lean-in).
  purpose: "Dispute desk — evidence packets, exception reasons, disputed invoices, settle pipeline, and payment attempts"
  access: persona(finance, finance_admin, auditor, tenant_admin)

  dispute_pulse:
    source: Invoice
    display: metrics
    aggregate:
      disputed: count(Invoice where status = disputed)
      with_reason: count(Invoice where status = disputed and dispute_reason != null)
      ready: count(Invoice where status = approved)
      conversation: count(InvoiceNote)
    tones:
      disputed: destructive
      with_reason: accent
      ready: positive
      conversation: accent

  # Honest document counts on the dispute home (InvoiceDocument source only).
  document_pulse:
    source: InvoiceDocument
    display: metrics
    aggregate:
      dispute_packets: count(InvoiceDocument where doc_kind = dispute_packet)
      published: count(InvoiceDocument where status = published)
      draft: count(InvoiceDocument where status = draft)
      documents: count(InvoiceDocument)
    tones:
      dispute_packets: destructive
      published: positive
      draft: warning
      documents: accent

  # Peer-pack dispute_packet_watch (cycle 1978): evidence covers before the
  # reason-bearing exception queue (not remittance/credit re-stack on ops).
  dispute_packets:
    source: InvoiceDocument
    filter: doc_kind = dispute_packet
    sort: created_at desc
    limit: 8
    display: queue
    action: invoice_document_detail
    empty: "No dispute packets — attach GRN mismatch, tax, or closed-PO evidence"

  # Exception queue — Invoice.fitness.repr_fields carries dispute_reason
  # so queue cards show why the invoice is blocked (still proof above the fold).
  disputed_queue:
    source: Invoice
    filter: status = disputed
    sort: updated_at desc
    limit: 12
    display: queue
    action: invoice_detail
    empty: "No open disputes — exceptions land here with reasons"

  settle_pipeline:
    source: Invoice
    filter: status = approved or status = disputed or status = partially_paid
    display: kanban
    group_by: status
    sort: due_date asc
    action: invoice_detail
    empty: "No invoices in the settle pipeline"

  payment_attempts:
    source: PaymentAttempt
    display: timeline
    sort: created_at desc
    limit: 12
    empty: "No payment attempts yet"

  status_mix:
    source: Invoice
    display: bar_chart
    group_by: status
    aggregate:
      count: count(Invoice)
    empty: "No invoices to chart"

  ux:
    as finance:
      purpose: "Disputes — evidence packets, reason-bearing queue, then settle pipeline"
      focus: dispute_pulse, document_pulse, dispute_packets, disputed_queue, settle_pipeline, payment_attempts
    as finance_admin:
      purpose: "Disputes — evidence packets, exception reasons, settle pipeline oversight"
      focus: dispute_pulse, document_pulse, dispute_packets, disputed_queue, settle_pipeline, payment_attempts
    as auditor:
      purpose: "Dispute evidence — packets, exceptions, pipeline, and attempt trail"
      focus: dispute_pulse, document_pulse, dispute_packets, disputed_queue, settle_pipeline, payment_attempts
    as tenant_admin:
      purpose: "Dispute oversight — evidence packets, exception queue, and settle mix"
      focus: dispute_pulse, document_pulse, dispute_packets, disputed_queue, settle_pipeline
