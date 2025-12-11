# Integrations

Integrations orchestrate data flow between your application and external services.

## Basic Syntax

```dsl
integration integration_name "Display Title":
  uses service ServiceName
  uses foreign ForeignModelName

  action action_name:
    # Action definition

  sync sync_name:
    # Sync definition
```

## Integration Components

### Uses Declarations

Reference services and foreign models:

```dsl
integration tax_integration "Tax Integration":
  uses service hmrc
  uses service companies_house
  uses foreign VATObligation, CompanyInfo
```

## Actions

Actions define request-response operations triggered by user interactions.

### Action Syntax

```dsl
action action_name:
  when surface surface_name
  call service service_name
  call operation /api/path
  call mapping:
    target -> source_path
  response foreign ForeignModelName
  response entity EntityName
  response mapping:
    target -> source_path
```

### Action Properties

| Property | Description |
|----------|-------------|
| `when surface` | Surface that triggers this action |
| `call service` | External service to call |
| `call operation` | API endpoint path |
| `call mapping` | Map form data to API request |
| `response foreign` | Expected response model |
| `response entity` | Entity to create/update from response |
| `response mapping` | Map response to entity fields |

### Action Example

```dsl
integration crm_integration "CRM Integration":
  uses service salesforce
  uses foreign SalesforceContact

  action sync_contact:
    when surface customer_form
    call service salesforce
    call operation /services/data/v52.0/sobjects/Contact
    call mapping:
      FirstName -> form.first_name
      LastName -> form.last_name
      Email -> form.email
      Phone -> form.phone
    response foreign SalesforceContact
    response entity Customer
    response mapping:
      salesforce_id -> Id
      last_synced -> SystemModstamp
```

## Syncs

Syncs define scheduled or event-driven data synchronization.

### Sync Syntax

```dsl
sync sync_name:
  mode: scheduled "cron_expression" | event_driven
  from service service_name
  from operation /api/path
  from foreign ForeignModelName
  into entity EntityName
  match rules:
    foreign_field <-> entity_field
```

### Sync Properties

| Property | Description |
|----------|-------------|
| `mode` | `scheduled "cron"` or `event_driven` |
| `from service` | Source service |
| `from operation` | API endpoint to call |
| `from foreign` | Foreign model defining response shape |
| `into entity` | Target entity to update |
| `match rules` | Bidirectional field mappings for matching |

### Sync Example

```dsl
integration inventory_sync "Inventory Sync":
  uses service warehouse_api
  uses foreign WarehouseItem

  sync daily_inventory:
    mode: scheduled "0 2 * * *"
    from service warehouse_api
    from operation /api/inventory/list
    from foreign WarehouseItem
    into entity Product
    match rules:
      sku <-> product_sku
      warehouse_id <-> external_id

  sync stock_updates:
    mode: event_driven
    from service warehouse_api
    from operation /api/inventory/changes
    from foreign WarehouseItem
    into entity Product
    match rules:
      sku <-> product_sku
```

## Complete Example

```dsl
# External service definition
service hmrc "HMRC VAT API":
  spec: url "https://api.hmrc.gov.uk/vat/openapi.json"
  auth_profile: oauth2 client_id_env="HMRC_CLIENT_ID" client_secret_env="HMRC_SECRET" token_url="https://api.hmrc.gov.uk/oauth/token"
  owner: "finance@company.com"

# Foreign model from external service
foreign_model VATObligation from hmrc "VAT Obligation":
  key: period_key
  constraint cache ttl="3600"

  period_key: str(20) required
  start_date: date required
  end_date: date required
  due_date: date required
  status: enum[open,fulfilled,overdue]

foreign_model VATReturn from hmrc "VAT Return":
  key: period_key
  period_key: str(20) required
  vat_due_sales: decimal(10,2)
  vat_due_acquisitions: decimal(10,2)
  total_vat_due: decimal(10,2)
  vat_reclaimed: decimal(10,2)
  net_vat_due: decimal(10,2)

# Integration orchestration
integration vat_integration "VAT Integration":
  uses service hmrc
  uses foreign VATObligation, VATReturn

  # Triggered when user submits VAT return form
  action submit_return:
    when surface vat_return_form
    call service hmrc
    call operation /organisations/vat/{vrn}/returns
    call mapping:
      vrn -> entity.company.vat_number
      periodKey -> form.period_key
      vatDueSales -> form.vat_due_sales
      vatDueAcquisitions -> form.vat_due_acquisitions
      totalVatDue -> form.total_vat_due
      vatReclaimedCurrPeriod -> form.vat_reclaimed
      netVatDue -> form.net_vat_due
    response foreign VATReturn
    response entity TaxReturn
    response mapping:
      submission_id -> processingDate
      status -> "submitted"

  # Scheduled sync of VAT obligations
  sync obligations:
    mode: scheduled "0 6 * * *"
    from service hmrc
    from operation /organisations/vat/{vrn}/obligations
    from foreign VATObligation
    into entity TaxPeriod
    match rules:
      period_key <-> hmrc_period_key
      start_date <-> period_start
      end_date <-> period_end

  # Event-driven updates when HMRC pushes changes
  sync obligation_updates:
    mode: event_driven
    from service hmrc
    from operation /webhook/obligations
    from foreign VATObligation
    into entity TaxPeriod
    match rules:
      period_key <-> hmrc_period_key
```

## Mapping Expressions

### Source Paths

| Path | Description |
|------|-------------|
| `form.field_name` | Form field value |
| `entity.field_name` | Current entity field |
| `entity.relation.field` | Related entity field |
| `foreign.field_name` | Foreign model field |
| `"literal"` | Literal string value |

### Examples

```dsl
call mapping:
  # From form fields
  email -> form.email_address

  # From entity
  customer_id -> entity.id

  # From related entity
  company_name -> entity.company.name

  # Literal value
  source -> "web_app"

response mapping:
  # From API response
  external_id -> id

  # Nested response path
  address_line -> address.street
```

## Best Practices

1. **Define foreign models** - Type your external API responses
2. **Use match rules** - Enable bidirectional sync with clear field mapping
3. **Set appropriate schedules** - Balance freshness vs. API rate limits
4. **Handle errors** - Integrations should be resilient to API failures
5. **Log operations** - Track sync history for debugging
