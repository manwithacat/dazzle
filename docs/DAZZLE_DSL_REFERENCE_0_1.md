# DAZZLE DSL 0.1 – Language Reference

This document describes the **surface syntax** for the DAZZLE DSL in version 0.1.

The DSL is intentionally compact and regular. It is designed to be:

- **Token-efficient** for LLMs (short, low-entropy, predictable structure)
- **Human-readable** for architects and analysts
- **Directly mappable** to the DAZZLE IR

This is not a full formal grammar (see the separate grammar file), but a pragmatic reference with examples.

---

## Top-level structure

A DAZZLE file describes a single app:

```text
app <app_name> "<Title>"
  [app-level options / metadata in future]

entity ...
surface ...
experience ...
service ...
foreign_model ...
integration ...
```

The ordering of sections is flexible, but an idiomatic order is:

1. `app`
2. `entity` blocks
3. `surface` blocks
4. `experience` blocks
5. `service` and `foreign_model` blocks
6. `integration` blocks

Comments are introduced with `#` and extend to the end of the line.

```text
# This is a comment
```

---

## Entities (domain models)

### Syntax

```text
entity <Name> [ "<Title>" ]:
  <field_line>*
  [constraint lines]*
```

Example:

```text
entity Client "Client":
  id: uuid pk
  name: str(200) required
  email: email unique?
  created_at: datetime auto_add

  unique email
```

### Field lines

Each field line has the form:

```text
<field_name>: <type_spec> [modifiers...]
```

#### Types

Supported base type specs:

```text
str(<max_length>)      # e.g. str(200)
text                   # long text
int
decimal(<precision>,<scale>)
bool
date
datetime
uuid
enum[opt1,opt2,...]
ref <EntityName>       # reference to another entity
email                  # shorthand, treated as str with email metadata
```

Examples:

```text
name: str(200) required
total: decimal(10,2) required
status: enum[draft,issued,paid,void]=draft
client: ref Client required
created_at: datetime auto_add
```

#### Modifiers

Modifiers adjust field behaviour:

- `required` (default for most fields)
- `optional` (alias for “not required”)
- `pk` (primary key)
- `unique` (unique constraint on this field)
- `unique?` (nullable unique)
- `auto_add` (auto_now_add for datetime)
- `auto_update` (auto_now for datetime)
- `default=<value>` (scalar default)

Examples:

```text
id: uuid pk
email: email unique?
issued_at: date optional
status: enum[draft,issued,paid,void]=draft
```

### Constraints

Constraints apply at the entity level:

```text
unique <field1>[,<field2>...]
index <field1>[,<field2>...]
```

Example:

```text
entity Invoice:
  id: uuid pk
  client: ref Client required
  issued_at: date?
  total: decimal(10,2) required

  unique client,issued_at
  index client
```

---

## Surfaces

A **surface** describes a user-facing screen / form / dashboard.

### Syntax

```text
surface <name> "<Title>":
  uses entity <EntityName>   # optional but common
  mode: <mode>

  section <section_name> [ "<Title>" ]:
    <element_line>*

  action <action_name> [ "<Label>" ]:
    on <trigger> -> <outcome>
```

Where:

- `<mode>` ∈ `view | create | edit | list | custom`
- `<trigger>` ∈ `submit | click | auto`
- `<outcome>` is an outcome directive (see below).

### Elements

Currently we support simple field elements; lists and widgets can be added as extensions.

```text
field <field_name> [ "<Label>" ] [options...]
```

Example:

```text
surface invoice_intake "Invoice Intake":
  uses entity Invoice
  mode: create

  section main "Main":
    field client "Client"
    field total "Total amount"
    field status "Status"

  action submit "Save":
    on submit -> experience upload_and_match step match
```

### Outcomes

Outcomes describe what happens when the action fires. For DAZZLE 0.1:

```text
-> surface <SurfaceName>
-> experience <ExperienceName> [step <StepName>]
-> integration <IntegrationName> action <ActionName>
```

Example:

```text
action lookup_vat "Check VAT":
  on click -> integration check_vat_registration action lookup
```

---

## Experiences

An **experience** orchestrates steps in a flow.

### Syntax

```text
experience <name> "<Title>":
  start at step <step_name>

  step <step_name>:
    kind: surface|process|integration
    surface <SurfaceName>      # if kind: surface
    integration <IntegrationName> action <ActionName>  # if kind: integration

    on success -> step <next_step_name>
    on failure -> step <other_step_name>
```

Example:

```text
experience upload_and_match "Upload and Match Invoices":
  start at step capture

  step capture:
    kind: surface
    surface invoice_intake
    on success -> step match

  step match:
    kind: integration
    integration nightly_bank_sync action match_now
    on success -> step summary

  step summary:
    kind: surface
    surface invoice_summary
```

For 0.1, `kind` is explicit to keep flows clear and parsing simple.

---

## Services (external systems)

A **service** describes a third‑party system.

### Syntax

```text
service <name> "<Title>":
  spec: url "<URL>" | inline "<ID>"
  auth_profile: <auth_kind> [options...]
  owner: "<OwnerName>"
```

Supported auth kinds (DAZZLE 0.1):

```text
oauth2_legacy
oauth2_pkce
jwt_static
api_key_header
api_key_query
none
```

Examples:

```text
service hmrc_vat "HMRC VAT API":
  spec: url "https://api.gov.uk/hmrc/vat/openapi.json"
  auth_profile: oauth2_legacy scopes="read:vat"
  owner: "HMRC"

service bank_feed "Bank Feed Provider":
  spec: url "https://api.bankfeed.example/openapi.json"
  auth_profile: oauth2_pkce scopes="transactions:read"
  owner: "Acme Bank Services"
```

Options after `auth_profile` are treated as key=value metadata.

---

## Foreign models

A **foreign_model** defines an external data structure owned by a service.

### Syntax

```text
foreign_model <Name> from <service_name> [ "<Title>" ]:
  key: <field1>[,<field2>...]
  constraint <kind> [details...]

  field <field_name>: <type_spec> [modifiers...]
```

Where `constraint <kind>` includes:

- `read_only`
- `event_driven`
- `batch_import`

Example:

```text
foreign_model VatRegistration from hmrc_vat "VAT Registration":
  key: vrn
  constraint read_only
  constraint batch_import frequency=daily

  field vrn: str(12)
  field name: str(200)
  field effective_date: date
```

Foreign field types and modifiers mirror entity fields but do not carry ownership semantics.

---

## Integrations

An **integration** encodes how services and foreign models interact with internal entities and experiences.

### Syntax

```text
integration <name> "<Title>":
  uses service <service_name>[,<service_name>...]
  uses foreign_model <ForeignName>[,<ForeignName>...]

  action <action_name>:
    when surface <surface_name> submitted
    call <service_name>.<operation_name> with:
      <external_field> <- <expression>
    map response <ForeignName> -> entity <EntityName>:
      <entity_field> <- <expression>

  sync <sync_name>:
    mode: scheduled|event_driven
    schedule: "<cron_expr>"          # if scheduled
    from <service_name>.<operation_name> as <ForeignName>
    into entity <EntityName>
    match on:
      <foreign_field> <-> <entity_field>
```

### Expressions

Expressions are kept simple:

- Paths: `form.vrn`, `surface.vrn`, `entity.client_id`, `foreign.vrn`
- Literals: `"GB123456789"`, `true`, `42`

Example (lookup integration):

```text
integration check_vat_registration "Check VAT Registration":
  uses service hmrc_vat
  uses foreign_model VatRegistration

  action lookup:
    when surface vat_check submitted
    call hmrc_vat.get_registration with:
      vrn <- form.vrn
    map response VatRegistration -> entity Client:
      tax_vrn <- foreign.vrn
      tax_name <- foreign.name
```

Example (nightly sync):

```text
integration nightly_bank_sync "Nightly Bank Sync":
  uses service bank_feed
  uses foreign_model BankTransaction

  sync import_transactions:
    mode: scheduled
    schedule: "0 2 * * *"   # nightly at 02:00
    from bank_feed.list_transactions as BankTransaction
    into entity LedgerTransaction
    match on:
      bank_id <-> external_id
```

---

## Metadata and extensions

Where necessary, additional hints can be attached via a simple `meta` directive.

Pattern (reserved for future use, not fully specified in 0.1):

```text
meta <key>=<value> [<key2>=<value2> ...]
```

Example usage (hypothetical):

```text
surface invoice_intake "Invoice Intake":
  uses entity Invoice
  mode: create
  meta ui:layout="two-column"

  section main:
    field client
    field total
```

Backends and modules can interpret `meta` keys as needed without affecting core semantics.

---

## Summary

The DAZZLE DSL 0.1:

- Provides a small, regular set of constructs: `app`, `entity`, `surface`, `experience`, `service`, `foreign_model`, `integration`.  
- Treats 3rd‑party APIs via abstract `service` + `foreign_model` + `integration` blocks, not low‑level HTTP.  
- Keeps flows (experiences) and interactions (surfaces) straightforward, with explicit steps and outcomes.  
- Is deliberately limited to stay token‑efficient and leave complex detail to the IR, backends, and LLM assistants.

Further revisions may add richer expression support, more surface element types, and reusable “pattern” modules, but 0.1 aims to prove the viability of this core. 
