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

A `map_request` target is a dotted path. An all-digit segment is a list index:
`otherGains.0.assetType` renders `{"otherGains": [{"assetType": ...}]}`, and a
later `.1` extends that list. `map_response` accepts the same target string and
stores it as one entity field name.

`transport: app` renders the request and calls
`pipeline.serve.app_init.integration_transport` instead of opening a socket.
The hook receives the method, interpolated path, declared base_url, static
mapping headers, and JSON body, and returns the status and body. The
application adds per-request headers and chooses the host. `on_error: retry`
calls the hook again. A missing hook is an error.

### Syntax

```dsl
integration <name> ["<Title>"]:
  [transport: app]
  [base_url: "<url>"]
  [auth: <api_key|oauth2|bearer|basic> from env("<KEY>")[, env("<KEY2>")]]

  [mapping <mapping_name> on <EntityName>:]
    [trigger: on_create [when <expr>]]
    [trigger: on_update [when <expr>]]
    [trigger: on_transition <from> -> <to>]
    [trigger: manual "<Label>"]
    request: <GET|POST|PUT|DELETE|PATCH> "<url_template>"
    [headers:]
      "<Header-Name>": "<value>"
    [map_request:]
      <field[.index][.path]> <- <source.path>
    [map_response:]
      <field[.path]> <- <source.path>
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

integration xero_accounting:
  base_url: "https://api.xero.com/api.xro/2.0"
  auth: oauth2 from env("XERO_CLIENT_ID"), env("XERO_CLIENT_SECRET")

  mapping create_invoice on Invoice:
    trigger: on_transition reviewed -> submitted
    request: POST "/Invoices"
    headers:
      "Accept": "application/json"
    map_request:
      Type <- self.invoice_type
      Contact.ContactID <- self.contact_id
    map_response:
      xero_invoice_id <- response.InvoiceID
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
