# Services

DAZZLE supports two types of services: External APIs and Domain Services.

## External APIs

External APIs define connections to third-party services via OpenAPI/Swagger specs.

### Syntax

```dsl
service service_name "Display Title":
  spec: url "https://api.example.com/openapi.json"
  auth_profile: auth_kind option=value
  owner: "team@example.com"
```

### Auth Profile Types

| Type | Description | Options |
|------|-------------|---------|
| `api_key` | API key authentication | `header`, `name` |
| `bearer` | Bearer token | `token_url` |
| `oauth2` | OAuth 2.0 | `client_id_env`, `client_secret_env`, `token_url` |
| `basic` | Basic auth | `username_env`, `password_env` |
| `none` | No authentication | - |

### Examples

```dsl
# API key authentication
service stripe "Stripe Payments":
  spec: url "https://api.stripe.com/openapi.yaml"
  auth_profile: api_key header="Authorization" name="Bearer"
  owner: "payments@company.com"

# OAuth2 authentication
service salesforce "Salesforce CRM":
  spec: url "https://developer.salesforce.com/openapi.json"
  auth_profile: oauth2 client_id_env="SF_CLIENT_ID" client_secret_env="SF_CLIENT_SECRET" token_url="https://login.salesforce.com/services/oauth2/token"
  owner: "crm-team@company.com"

# Basic auth
service legacy_api "Legacy System":
  spec: url "https://internal.company.com/api/swagger.json"
  auth_profile: basic username_env="LEGACY_USER" password_env="LEGACY_PASS"
  owner: "devops@company.com"

# Inline spec (for small APIs)
service webhook "Webhook Service":
  spec: inline "{ paths: { /notify: { post: {} } } }"
  auth_profile: none
```

## Domain Services

Domain services define internal business logic operations with typed inputs/outputs.

### Syntax

```dsl
service service_name "Display Title":
  kind: domain_logic|validation|integration|workflow

  input:
    field_name: type_name [required]

  output:
    field_name: type_name

  guarantees:
    - "Guarantee statement"

  stub: python|typescript
```

### Service Kinds

| Kind | Description |
|------|-------------|
| `domain_logic` | Core business rules and calculations |
| `validation` | Complex validation logic |
| `integration` | Orchestration between systems |
| `workflow` | Multi-step business processes |

### Examples

```dsl
# VAT calculation service
service calculate_vat "Calculate VAT":
  kind: domain_logic

  input:
    invoice_id: uuid required
    country_code: str(2) required

  output:
    vat_amount: decimal(10,2)
    vat_rate: decimal(5,4)
    breakdown: json

  guarantees:
    - "Must not mutate the invoice record"
    - "Returns zero VAT for exempt categories"
    - "Supports all EU country codes"

  stub: python

# Order validation service
service validate_order "Validate Order":
  kind: validation

  input:
    order_id: uuid required

  output:
    is_valid: bool
    errors: json

  guarantees:
    - "Checks inventory availability"
    - "Validates customer credit limit"
    - "Returns all errors, not just first"

  stub: python

# Payment processing service
service process_payment "Process Payment":
  kind: integration

  input:
    order_id: uuid required
    payment_method: str(50) required
    amount: decimal(10,2) required

  output:
    transaction_id: str(100)
    status: str(20)
    error_message: str(500)

  guarantees:
    - "Idempotent - safe to retry"
    - "Logs all attempts for audit"
    - "Times out after 30 seconds"

  stub: python

# Onboarding workflow
service customer_onboarding "Customer Onboarding":
  kind: workflow

  input:
    customer_id: uuid required
    onboarding_type: str(20) required

  output:
    completed_steps: json
    next_step: str(50)
    is_complete: bool

  guarantees:
    - "Can be resumed from any step"
    - "Sends notifications at key milestones"
    - "Creates audit trail"

  stub: python
```

## Foreign Models

Foreign models define data structures from external APIs that you want to work with:

```dsl
foreign_model ModelName from service_name "Display Title":
  key: key_field[, key_field2]

  constraint constraint_type option=value

  field_name: type modifiers
```

### Constraint Types

| Type | Description | Options |
|------|-------------|---------|
| `cache` | Cache responses | `ttl` |
| `rate_limit` | Rate limiting | `per_minute` |
| `retry` | Retry failed requests | `attempts`, `backoff` |

### Example

```dsl
service hmrc "HMRC API":
  spec: url "https://api.hmrc.gov.uk/openapi.json"
  auth_profile: oauth2 client_id_env="HMRC_CLIENT_ID" client_secret_env="HMRC_SECRET" token_url="https://api.hmrc.gov.uk/oauth/token"
  owner: "tax-team@company.com"

foreign_model VATObligation from hmrc "VAT Obligation":
  key: period_key

  constraint cache ttl="3600"
  constraint rate_limit per_minute="60"
  constraint retry attempts="3" backoff="exponential"

  period_key: str(20) required
  start_date: date required
  end_date: date required
  due_date: date required
  status: enum[open,fulfilled,overdue]
  received_date: date optional

foreign_model CompanyInfo from companies_house "Company Information":
  key: company_number

  constraint cache ttl="86400"

  company_number: str(10) required pk
  company_name: str(200) required
  company_status: str(50)
  date_of_creation: date
  registered_office: embeds Address
```

## Best Practices

1. **Use domain services for business logic** - Keep complex rules testable and isolated
2. **Define guarantees** - Document what callers can rely on
3. **Choose appropriate service kind** - Helps with code generation and testing
4. **Cache foreign models** - Reduce API calls with appropriate TTLs
5. **Handle rate limits** - Configure constraints to stay within API quotas
