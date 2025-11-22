# DAZZLE IR 0.1 (Conceptual Spec)

This document defines the **internal representation (IR)** for DAZZLE 0.1.  
The IR is a framework‑agnostic model of an application, used as the single source of truth for all generators.

In an implementation, these structures are likely represented as Pydantic models, but this spec is *conceptual* rather than tied to a specific language.

---

## Top-level: AppSpec

```text
AppSpec
  - name: string            # short identifier, e.g. "billing_core"
  - title: string           # human‑friendly name, e.g. "Billing Core"
  - version: string?        # optional semver-like tag
  - domain: DomainSpec
  - surfaces: [SurfaceSpec]
  - experiences: [ExperienceSpec]
  - services: [ServiceSpec]
  - foreign_models: [ForeignModelSpec]
  - integrations: [IntegrationSpec]
  - metadata: Metadata?     # arbitrary key/value tags
```

---

## Domain

```text
DomainSpec
  - entities: [EntitySpec]
```

### EntitySpec

```text
EntitySpec
  - name: string            # e.g. "Invoice"
  - title: string?          # e.g. "Invoice"
  - description: string?
  - fields: [FieldSpec]
  - constraints: [EntityConstraintSpec]
  - metadata: Metadata?
```

### FieldSpec

The type system is intentionally small and composable.

```text
FieldSpec
  - name: string             # e.g. "total"
  - title: string?
  - type: FieldType          # see below
  - required: bool = true
  - primary_key: bool = false
  - unique: bool = false
  - default: LiteralValue?   # scalar default (string/number/bool)
  - max_length: int?         # for string-like
  - precision: int?          # for decimal (total digits)
  - scale: int?              # for decimal (fractional digits)
  - ref: string?             # entity name if type == ref
  - enum_values: [string]?   # if type == enum
  - auto_now: bool?          # datetime auto update
  - auto_now_add: bool?      # datetime on create
  - metadata: Metadata?
```

### FieldType

```text
FieldType = "string" | "text" | "int" | "decimal" | "bool" |
            "date" | "datetime" | "uuid" | "enum" | "ref"
```

### EntityConstraintSpec

```text
EntityConstraintSpec
  - kind: "unique" | "index"
  - fields: [string]          # field names
  - name: string?             # optional explicit name
```

---

## Surfaces

A **surface** is a user‑facing interaction layer (screen, form, dashboard, etc.).

```text
SurfaceSpec
  - name: string             # e.g. "invoice_intake"
  - title: string?
  - description: string?
  - mode: "view" | "create" | "edit" | "list" | "custom"
  - primary_entity: string?  # entity name, if this surface is entity-centric
  - sections: [SurfaceSectionSpec]
  - actions: [SurfaceActionSpec]
  - metadata: Metadata?
```

### SurfaceSectionSpec

```text
SurfaceSectionSpec
  - name: string             # logical identifier, e.g. "main"
  - title: string?
  - elements: [SurfaceElementSpec]
```

### SurfaceElementSpec

Elements are kept simple: fields, lists, or references to pre-defined widgets.

```text
SurfaceElementSpec
  - kind: "field" | "list" | "widget"
  - ref: string              # field name, widget name, or nested surface
  - label: string?
  - options: Map<string, LiteralValue>  # backend-specific hints
```

### SurfaceActionSpec

Actions describe what happens when users interact (submit, click a button, etc.).

```text
SurfaceActionSpec
  - name: string             # e.g. "submit"
  - label: string?
  - trigger: "submit" | "click" | "auto"
  - outcome: ActionOutcomeSpec
```

### ActionOutcomeSpec

Outcomes can be:

- Transition to another surface/experience
- Invoke a process or integration
- Mutate an entity

```text
ActionOutcomeSpec
  - kind: "navigate" | "invoke_process" | "invoke_integration"
  - target: string           # experience/surface/process/integration name
  - params: Map<string, Expression>  # input mapping, expressed as simple expressions
```

---

## Experiences

An **experience** is an orchestrated flow of steps.

```text
ExperienceSpec
  - name: string
  - title: string?
  - description: string?
  - start_step: string            # step name
  - steps: [ExperienceStepSpec]
  - metadata: Metadata?
```

### ExperienceStepSpec

```text
ExperienceStepSpec
  - name: string
  - kind: "surface" | "process" | "integration"
  - surface: string?             # if kind == surface
  - process: string?             # if kind == process (future extension)
  - integration: string?         # if kind == integration
  - on_success: StepTransition?
  - on_failure: StepTransition?
  - metadata: Metadata?
```

### StepTransition

```text
StepTransition
  - target_step: string
  - condition: Expression?       # optional condition to branch on
```

Experiences encode a DAG-like execution graph without requiring a full workflow language.

---

## Services (external systems)

A **ServiceSpec** describes a 3rd‑party system.

```text
ServiceSpec
  - name: string                 # e.g. "hmrc_vat"
  - title: string?
  - description: string?
  - spec_ref: ServiceSpecRef
  - auth_profile: AuthProfileSpec
  - owner: string?
  - operational: ServiceOperationalSpec?
  - metadata: Metadata?
```

### ServiceSpecRef

```text
ServiceSpecRef
  - kind: "openapi_url" | "openapi_inline" | "custom_schema"
  - location: string           # URL, file path, or identifier
```

### AuthProfileSpec

Abstracts authentication style without locking in an implementation.

```text
AuthProfileSpec
  - kind: "oauth2_legacy" | "oauth2_pkce" | "jwt_static" |
          "api_key_header" | "api_key_query" | "none"
  - parameters: Map<string, LiteralValue>   # e.g. header name, scopes
```

### ServiceOperationalSpec

Hints that influence generated clients and infra but are not required to build the IR.

```text
ServiceOperationalSpec
  - rate_limit_per_minute: int?
  - retry_policy: RetryPolicySpec?
  - cache_policy: CachePolicySpec?
  - default_timeout_seconds: int?
  - polling_schedules: [PollingScheduleSpec]? # for pull-based sync
  - webhook_endpoints: [WebhookEndpointSpec]? # for push-based events
```

### RetryPolicySpec

```text
RetryPolicySpec
  - strategy: "none" | "linear" | "exponential"
  - max_attempts: int
  - base_delay_seconds: int?
```

### CachePolicySpec

```text
CachePolicySpec
  - strategy: "none" | "ttl" | "etag" | "last_modified"
  - ttl_seconds: int?
```

### PollingScheduleSpec

```text
PollingScheduleSpec
  - name: string
  - cron: string                 # cron-like expression
  - operation: string            # operation name / path in remote spec
```

### WebhookEndpointSpec

```text
WebhookEndpointSpec
  - name: string
  - event_type: string           # e.g. "invoice.created"
  - target_experience: string    # which experience to invoke
```

---

## Foreign models

A **ForeignModelSpec** represents an external data shape tied to a ServiceSpec.

```text
ForeignModelSpec
  - name: string                 # e.g. "VatRegistration"
  - title: string?
  - description: string?
  - service: string              # ServiceSpec.name
  - key_fields: [string]         # names in fields list
  - fields: [ForeignFieldSpec]
  - constraints: [ForeignModelConstraintSpec]
  - metadata: Metadata?
```

### ForeignFieldSpec

Very similar to FieldSpec, but without ownership semantics.

```text
ForeignFieldSpec
  - name: string
  - title: string?
  - type: FieldType
  - required: bool = true
  - max_length: int?
  - precision: int?
  - scale: int?
  - enum_values: [string]?
  - metadata: Metadata?
```

### ForeignModelConstraintSpec

```text
ForeignModelConstraintSpec
  - kind: "read_only" | "event_driven" | "batch_import"
  - details: Map<string, LiteralValue>?
```

---

## Integrations

An **IntegrationSpec** glues services, foreign models, and internal entities together.

```text
IntegrationSpec
  - name: string
  - title: string?
  - description: string?
  - uses_services: [string]           # service names
  - uses_foreign_models: [string]     # foreign model names
  - actions: [IntegrationActionSpec]
  - syncs: [SyncSpec]
  - metadata: Metadata?
```

### IntegrationActionSpec

Represents an on‑demand action, typically triggered by a surface or experience step.

```text
IntegrationActionSpec
  - name: string
  - trigger: IntegrationTriggerSpec
  - call: ServiceCallSpec
  - mapping: MappingSpec?             # how to map response into internal entities
  - metadata: Metadata?
```

### IntegrationTriggerSpec

```text
IntegrationTriggerSpec
  - kind: "surface_submit" | "experience_step" | "manual"
  - surface: string?                  # if kind == surface_submit
  - experience: string?               # if kind == experience_step
  - step: string?                     # step name
```

### ServiceCallSpec

An abstract description of calling a service operation.

```text
ServiceCallSpec
  - service: string                   # ServiceSpec.name
  - operation: string                 # logical operation name (e.g. "get_vat_registration")
  - input_mapping: MappingSpec        # internal → external request
```

> Note: `operation` should be a human‑meaningful identifier. Backends are responsible for matching this to OpenAPI operations, potentially with LLM assistance.

### MappingSpec

```text
MappingSpec
  - from: string                      # "surface", "entity", "foreign_model"
  - source_name: string               # e.g. "vat_check_surface" or "Invoice"
  - rules: [MappingRule]
```

### MappingRule

```text
MappingRule
  - target: string                    # field path on target
  - expression: Expression            # simple expression or path, e.g. "form.vrn"
```

### SyncSpec

Represents scheduled or event‑driven synchronization between foreign models and internal entities.

```text
SyncSpec
  - name: string
  - mode: "scheduled" | "event_driven"
  - schedule: string?                 # cron-like, if scheduled
  - service: string                   # ServiceSpec.name
  - source_operation: string          # e.g. "list_invoices"
  - foreign_model: string             # ForeignModelSpec.name
  - target_entity: string             # EntitySpec.name
  - match_rules: [MatchRuleSpec]
  - upsert: bool = true               # update-existing or create-only
  - metadata: Metadata?
```

### MatchRuleSpec

```text
MatchRuleSpec
  - foreign_field: string
  - entity_field: string
```

---

## Expressions

To keep DSL and IR small, **Expression** is deliberately lightweight and can be expanded over time.

For DAZZLE 0.1, we model it as:

```text
Expression
  - kind: "path" | "literal"
  - value: string | LiteralValue
```

Where `path` is a dotted string like `"form.vrn"`, `"entity.client_id"`, `"foreign.effective_date"`.

Backends can expand this if needed (e.g. add simple operators) without changing the core IR structure.

---

## Metadata & extensibility

Nearly every spec type carries an optional `metadata: Metadata?` field.

```text
Metadata = Map<string, LiteralValue>
```

This allows:

- Backends to attach hints (e.g. `"ui:component" = "select"`).  
- Modules to extend semantics without altering core types.  
- LLMs to add low‑priority suggestions that don’t affect core correctness.

---

## Summary

- The IR is **framework‑agnostic**, minimal, and intentionally plain.  
- It models the **truth** of an application: domain, surfaces, experiences, services, foreign data, and integrations.  
- Backends use the IR as a meta‑model for model‑driven, schema‑driven generation.  
- LLMs primarily operate at the DSL level; the IR and backends remain deterministic and testable.

DAZZLE 0.1 aims to prove that this IR is expressive enough to support real‑world SaaS patterns while remaining small enough to be LLM‑friendly and human‑comprehensible.
