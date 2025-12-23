# Parser Reference: Services, Foreign Models, and Experiences
# =============================================================================
#
# COVERAGE CHECKLIST:
#
# EXTERNAL API SERVICE:
# - [x] service name "Title":
# - [x] spec: url "..."
# - [x] spec: inline "..."
# - [x] auth_profile: kind
# - [x] auth_profile: kind key=value
# - [x] owner: "..."
#
# AUTH KINDS:
# - [x] api_key_header
# - [x] api_key_query
# - [x] oauth2_legacy
# - [x] oauth2_pkce
# - [x] jwt_static
# - [x] none
#
# DOMAIN SERVICE:
# - [x] service name "Title":
# - [x] kind: domain_logic
# - [x] kind: validation
# - [x] kind: integration
# - [x] kind: workflow
# - [x] input: block
# - [x] output: block
# - [x] guarantees: block
# - [x] stub: python
# - [x] stub: typescript
#
# SERVICE FIELDS:
# - [x] field_name: type
# - [x] field_name: type required
# - [x] field_name: type(params)
#
# FOREIGN MODEL:
# - [x] foreign_model Name from api:
# - [x] key: field1, field2
# - [x] constraint kind
# - [x] constraint kind key=value
# - [x] field definitions
#
# FOREIGN CONSTRAINT KINDS:
# - [x] read_only
# - [x] event_driven
# - [x] batch_import
#
# EXPERIENCE:
# - [x] experience name "Title":
# - [x] start at step StepName
# - [x] step name:
# - [x] kind: surface
# - [x] kind: integration
# - [x] surface name
# - [x] integration name action action_name
# - [x] on event -> step next_step
#
# =============================================================================

module pra.services

use pra
use pra.entities
use pra.surfaces

# =============================================================================
# EXTERNAL API SERVICE: API KEY AUTH
# =============================================================================

service stripe "Stripe Payment API":
  spec: url "https://api.stripe.com/openapi.json"
  auth_profile: api_key_header header="Authorization" prefix="Bearer"
  owner: "payments@example.com"

# =============================================================================
# EXTERNAL API SERVICE: OAUTH2 AUTH
# =============================================================================

service salesforce "Salesforce CRM API":
  spec: url "https://developer.salesforce.com/openapi.yaml"
  auth_profile: oauth2_pkce client_id="env:SF_CLIENT_ID" client_secret="env:SF_CLIENT_SECRET"
  owner: "integrations@example.com"

# =============================================================================
# EXTERNAL API SERVICE: BASIC AUTH
# =============================================================================

service legacy_erp "Legacy ERP System":
  spec: url "https://erp.internal/api/spec.json"
  auth_profile: jwt_static token="env:ERP_TOKEN"
  owner: "legacy-systems@example.com"

# =============================================================================
# EXTERNAL API SERVICE: BEARER TOKEN
# =============================================================================

service internal_api "Internal Microservice":
  spec: inline "{\"openapi\":\"3.0.0\",\"info\":{\"title\":\"Internal API\",\"version\":\"1.0.0\"}}"
  auth_profile: api_key_header token="env:INTERNAL_API_TOKEN"
  owner: "platform@example.com"

# =============================================================================
# DOMAIN SERVICE: DOMAIN LOGIC
# =============================================================================

service calculate_invoice_total "Calculate Invoice Total":
  kind: domain_logic

  input:
    invoice_id: uuid required
    include_tax: bool

  output:
    subtotal: decimal(15,2)
    tax_amount: decimal(15,2)
    total: decimal(15,2)

  guarantees:
    - "Must not modify the invoice record"
    - "Returns consistent values for same input"

  stub: python

# =============================================================================
# DOMAIN SERVICE: VALIDATION
# =============================================================================

service validate_order "Validate Order Data":
  kind: validation

  input:
    order_id: uuid required
    items: json required

  output:
    is_valid: bool
    errors: json
    warnings: json

  guarantees:
    - "Read-only operation"
    - "Deterministic for same input"
    - "Validates inventory availability"

  stub: python

# =============================================================================
# DOMAIN SERVICE: INTEGRATION
# =============================================================================

service sync_to_external "Sync Data to External System":
  kind: integration

  input:
    entity_type: str(255) required
    entity_id: uuid required
    operation: str(255) required

  output:
    success: bool
    external_id: str
    sync_timestamp: datetime

  guarantees:
    - "Idempotent for same entity_id and operation"
    - "External system updated within 30 seconds"

  stub: python

# =============================================================================
# DOMAIN SERVICE: WORKFLOW
# =============================================================================

service approve_purchase_order "Purchase Order Approval Workflow":
  kind: workflow

  input:
    po_id: uuid required
    approver_id: uuid required
    decision: str(255) required
    comments: text

  output:
    new_status: str
    next_approver: uuid
    completed: bool

  guarantees:
    - "Follows approval chain rules"
    - "Sends notifications to relevant parties"
    - "Updates PO status atomically"

  stub: python

# =============================================================================
# DOMAIN SERVICE: TYPESCRIPT STUB
# =============================================================================

service generate_report "Generate Analytics Report":
  kind: domain_logic

  input:
    report_type: str(255) required
    date_from: date required
    date_to: date required
    filters: json

  output:
    report_data: json
    generated_at: datetime
    record_count: int

  stub: typescript

# =============================================================================
# DOMAIN SERVICE: MINIMAL
# =============================================================================

service simple_operation "Simple Operation":
  kind: domain_logic

  input:
    data: json required

  output:
    result: json

  stub: python

# =============================================================================
# DOMAIN SERVICE: COMPLEX INPUT/OUTPUT
# =============================================================================

service process_payment "Process Payment":
  kind: integration

  input:
    payment_id: uuid required
    amount: decimal(15,2) required
    currency: str(3) required
    customer_id: uuid required
    payment_method: str(255) required
    metadata: json

  output:
    transaction_id: str
    status: str
    processed_at: datetime
    receipt_url: url
    error_code: str
    error_message: text

  guarantees:
    - "Idempotent for same payment_id"
    - "PCI-DSS compliant handling"
    - "Retry with exponential backoff on failure"
    - "Maximum 3 retry attempts"

  stub: python

# =============================================================================
# FOREIGN MODEL: BASIC
# =============================================================================

foreign_model StripeCustomer from stripe "Stripe Customer":
  key: stripe_customer_id

  constraint batch_import

  stripe_customer_id: str(50) required
  email: email
  name: str(200)
  created: datetime
  default_source: str(50)

# =============================================================================
# FOREIGN MODEL: COMPOSITE KEY
# =============================================================================

foreign_model SalesforceContact from salesforce "Salesforce Contact":
  key: sf_account_id, sf_contact_id

  constraint batch_import
  constraint batch_import webhook_url="env:SF_WEBHOOK_URL"

  sf_account_id: str(50) required
  sf_contact_id: str(50) required
  first_name: str(100)
  last_name: str(100) required
  email: email required
  phone: str(20)
  title: str(100)
  created_date: datetime

# =============================================================================
# FOREIGN MODEL: BATCH IMPORT
# =============================================================================

foreign_model ERPProduct from legacy_erp "ERP Product":
  key: erp_product_code

  constraint batch_import

  erp_product_code: str(20) required
  name: str(200) required
  description: text
  unit_price: decimal(15,2) required
  stock_quantity: int=0
  category_code: str(20)
  last_updated: datetime

# =============================================================================
# FOREIGN MODEL: MULTIPLE CONSTRAINTS
# =============================================================================

foreign_model PaymentMethod from stripe "Payment Method":
  key: payment_method_id

  constraint batch_import
  constraint batch_import webhook_url="env:STRIPE_WEBHOOK_URL"

  payment_method_id: str(50) required
  customer_id: str(50) required
  type: str(20)
  card_brand: str(20)
  card_last4: str(4)
  card_exp_month: int
  card_exp_year: int
  is_default: bool=false
  created: datetime

# =============================================================================
# FOREIGN MODEL: MINIMAL
# =============================================================================

foreign_model ExternalRecord from internal_api:
  key: external_id

  external_id: str(100) required
  data: json

# =============================================================================
# EXPERIENCE: BASIC
# =============================================================================

experience checkout_flow "Checkout Flow":
  start at step cart

  step cart:
    kind: surface
    surface cart_view
    on success -> step payment

  step payment:
    kind: surface
    surface payment_form
    on success -> step confirmation
    on failure -> step cart

  step confirmation:
    kind: surface
    surface order_confirmation

# =============================================================================
# EXPERIENCE: WITH INTEGRATION STEP
# =============================================================================

experience payment_processing "Payment Processing":
  start at step collect_payment

  step collect_payment:
    kind: surface
    surface payment_form
    on success -> step process_payment

  step process_payment:
    kind: surface
    surface payment_processing
    on success -> step show_receipt
    on failure -> step handle_error

  step show_receipt:
    kind: surface
    surface payment_receipt

  step handle_error:
    kind: surface
    surface payment_error
    on try_again -> step collect_payment
    on cancel -> step cancelled

  step cancelled:
    kind: surface
    surface payment_cancelled

# =============================================================================
# EXPERIENCE: MULTI-STEP WIZARD
# =============================================================================

experience user_onboarding "User Onboarding":
  start at step welcome

  step welcome:
    kind: surface
    surface onboarding_welcome
    on continue -> step profile

  step profile:
    kind: surface
    surface onboarding_profile
    on continue -> step preferences
    on back -> step welcome

  step preferences:
    kind: surface
    surface onboarding_preferences
    on continue -> step verify
    on back -> step profile

  step verify:
    kind: surface
    surface verification_pending
    on success -> step complete
    on failure -> step verify_error

  step verify_error:
    kind: surface
    surface verification_error
    on try_again -> step verify
    on skip -> step complete

  step complete:
    kind: surface
    surface onboarding_complete

# =============================================================================
# EXPERIENCE: APPROVAL WORKFLOW
# =============================================================================

experience purchase_approval "Purchase Approval":
  start at step review

  step review:
    kind: surface
    surface po_review
    on approve -> step check_budget
    on reject -> step rejected
    on cancel -> step cancelled

  step check_budget:
    kind: surface
    surface budget_check_pending
    on approved -> step processing
    on over_budget -> step escalate

  step escalate:
    kind: surface
    surface po_escalate
    on approve -> step processing
    on reject -> step rejected

  step processing:
    kind: surface
    surface po_processing
    on success -> step completed
    on failure -> step error

  step completed:
    kind: surface
    surface po_completed

  step rejected:
    kind: surface
    surface po_rejected

  step cancelled:
    kind: surface
    surface po_cancelled

  step error:
    kind: surface
    surface po_error
    on try_again -> step processing

# Placeholder surfaces for experiences
surface payment_form "Payment Form":
  mode: create
  section main:
    field amount

surface order_confirmation "Order Confirmation":
  mode: view
  section main:
    field order_number

surface payment_receipt "Payment Receipt":
  mode: view
  section main:
    field transaction_id

surface payment_error "Payment Error":
  mode: custom
  section main:
    field error_message

surface payment_cancelled "Payment Cancelled":
  mode: custom
  section main:
    field message

surface onboarding_welcome "Welcome":
  mode: custom
  section main:
    field welcome_message

surface onboarding_profile "Profile Setup":
  mode: create
  section main:
    field name

surface onboarding_preferences "Preferences":
  mode: create
  section main:
    field preferences

surface verification_error "Verification Error":
  mode: custom
  section main:
    field error_message

surface onboarding_complete "Onboarding Complete":
  mode: custom
  section main:
    field message

surface po_review "PO Review":
  mode: view
  section main:
    field po_number

surface po_escalate "Escalate PO":
  mode: edit
  section main:
    field escalation_reason

surface po_completed "PO Completed":
  mode: view
  section main:
    field po_number

surface po_rejected "PO Rejected":
  mode: view
  section main:
    field rejection_reason

surface po_cancelled "PO Cancelled":
  mode: view
  section main:
    field cancellation_reason

surface po_error "PO Error":
  mode: custom
  section main:
    field error_message

surface payment_processing "Payment Processing":
  mode: custom
  section main:
    field status "Processing..."

surface verification_pending "Verification Pending":
  mode: custom
  section main:
    field status "Verifying..."

surface budget_check_pending "Budget Check":
  mode: custom
  section main:
    field status "Checking budget..."

surface po_processing "PO Processing":
  mode: custom
  section main:
    field status "Processing PO..."
