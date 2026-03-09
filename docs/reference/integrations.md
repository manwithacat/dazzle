# Integrations

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

Integrations connect DAZZLE apps to external systems via declarative API bindings with triggers, field mappings, and error handling. Foreign models define the shape of external data for type-safe rendering without owning the source records.

---

## Integration

External service integration declaration. Defines API connections, actions,
data sync points, and declarative field mappings for external systems.

v0.30.0 adds declarative mapping blocks: base_url, auth, mapping with triggers,
HTTP requests, request/response field mappings, and error handling strategies.

### Syntax

```dsl
integration <name> ["<Title>"]:
  [base_url: "<url>"]
  [auth: <api_key|oauth2|bearer|basic> from env("<KEY>")[, env("<KEY2>")]]

  [mapping <mapping_name> on <EntityName>:]
    [trigger: on_create [when <expr>]]
    [trigger: on_update [when <expr>]]
    [trigger: on_transition <from> -> <to>]
    [trigger: manual "<Label>"]
    request: <GET|POST|PUT|DELETE|PATCH> "<url_template>"
    [map_request:]
      <field> <- <source.path>
    [map_response:]
      <field> <- <source.path>
    [on_error: <ignore|log_warning|revert_transition|retry>]
    [on_error: set <field> = "<value>", <action>]
```

### Example

```dsl
integration companies_house:
  base_url: "https://api.company-information.service.gov.uk"
  auth: api_key from env("COMPANIES_HOUSE_API_KEY")

  mapping fetch_company on Company:
    trigger: on_create when company_number != null
    trigger: manual "Look up company"
    request: GET "/company/{self.company_number}"
    map_response:
      company_name <- response.company_name
      company_type <- response.type
      incorporation_date <- response.date_of_creation
    on_error: set company_status = "lookup_failed", log_warning

integration hmrc_mtd:
  base_url: "https://api.service.hmrc.gov.uk"
  auth: oauth2 from env("HMRC_CLIENT_ID"), env("HMRC_CLIENT_SECRET")

  mapping submit_vat on VATReturn:
    trigger: on_transition reviewed -> submitted
    request: POST "/organisations/vat/returns"
    map_request:
      periodKey <- self.period_key
      vatDueSales <- self.box1_vat_due_sales
    map_response:
      hmrc_receipt_id <- response.formBundleNumber
    on_error: revert_transition
```

**Related:** [Domain Service](services.md#domain-service), [Foreign Model](integrations.md#foreign-model), [Entity](entities.md#entity)

---

## Foreign Model

Declaration of data structures from external systems (APIs, services) that Dazzle surfaces can display but doesn't own. Foreign models define the shape of external data for type-safe rendering.

### Syntax

```dsl
foreign_model <ModelName> "<Title>":
  <field_name>: <type>
  ...
```

**Related:** [Integration](integrations.md#integration), [Domain Service](services.md#domain-service)

---

## Webhook

Outbound HTTP notification triggered by entity lifecycle events (created, updated, deleted). Webhooks send JSON payloads to external URLs with configurable authentication (HMAC-SHA256, bearer, basic), field selection, and retry policies.

### Syntax

```dsl
webhook <name> "<Title>":
  entity: <EntityName>
  events: [created, updated, deleted]
  url: config("<ENV_VAR>") | "<url>"
  [auth:]
    [method: <hmac_sha256|bearer|basic>]
    [secret: config("<ENV_VAR>")]
  [payload:]
    [include: [<field1>, <field2>, <entity.field>]]
    [format: json]
  [retry:]
    [max_attempts: <int>]
    [backoff: <exponential|linear>]
```

### Example

```dsl
webhook OrderNotification "Order Status Webhook":
  entity: Order
  events: [created, updated]
  url: config("ORDER_WEBHOOK_URL")
  auth:
    method: hmac_sha256
    secret: config("WEBHOOK_SECRET")
  payload:
    include: [id, status, total, customer.name]
    format: json
  retry:
    max_attempts: 3
    backoff: exponential

webhook AuditLog "Audit Event Webhook":
  entity: AuditEntry
  events: [created]
  url: config("AUDIT_WEBHOOK_URL")
  auth:
    method: bearer
    secret: config("AUDIT_API_KEY")
```

### Best Practices

- Use config() for URLs and secrets - never hardcode credentials
- Use HMAC-SHA256 for webhook signature verification
- Select only needed fields in payload to minimize data exposure
- Set retry with exponential backoff for resilient delivery

**Related:** [Entity](entities.md#entity), [Integration](integrations.md#integration), [Channel](messaging.md#channel)

---
