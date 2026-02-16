# DSL Grammar Specification

Formal EBNF grammar for DAZZLE DSL v0.25.0.

> **Auto-generated** from parser source code by `grammar_gen.py`. Do not edit manually; run `dazzle grammar` to regenerate.

## Overview

This grammar defines the complete syntax for the DAZZLE Domain-Specific Language. The DSL supports the following construct categories:

- **Core**: Field Types and Modifiers, Entity and Archetype Definitions, State Machines, Invariants, Access Rules and Governance, Example Data, Shared Enums
- **Surface**: Surface Definitions, UX Semantic Layer, Workspace Definitions, Experience Definitions, Views
- **Workflow**: Story Definitions, Process Workflows and Schedules, Approvals, SLAs
- **Integration**: Service Definitions, Foreign Model Definitions, Integration Definitions, Webhooks
- **Testing**: E2E Test Flows, API Contract Tests, Scenario and Demo Data
- **Eventing**: Messaging Channels, Event-First Architecture, HLESS Event Semantics
- **Financial**: TigerBeetle Ledgers and Transactions
- **Governance**: Governance Sections
- **LLM**: LLM Jobs

## Anti-Turing Enforcement

DAZZLE intentionally limits computational expressiveness to ensure:

- Aggregate functions only in computed expressions
- `AGGREGATE_FN` explicitly enumerates allowed functions
- Turing-complete logic lives in service stubs (not DSL)

## Keyword Inventory

**Keywords**: `module`, `use`, `as`, `app`, `entity`, `surface`, `experience`, `service`, `foreign_model`, `integration`, `from`, `uses`, `mode`, `section`, `field`, `action`, `step`, `kind`, `start`, `at`, `on`, `when`, `call`, `with`, `map`, `response`, `into`, `match`, `sync`, `schedule`, `spec`, `auth_profile`, `owner`, `key`, `constraint`, `unique`, `index`, `url`, `inline`, `submitted`

**Integration Keywords**: `operation`, `mapping`, `rules`, `scheduled`, `event_driven`, `foreign`

**Test DSL Keywords**: `test`, `setup`, `data`, `expect`, `status`, `created`, `filter`, `search`, `order_by`, `count`, `error_message`, `first`, `last`, `query`, `create`, `update`, `delete`, `get`, `true`, `false`

**Access Control Keywords**: `anonymous`, `permissions`, `access`, `read`, `write`, `permit`, `forbid`, `audit`

**UX Semantic Layer Keywords**: `ux`, `purpose`, `show`, `sort`, `empty`, `attention`, `critical`, `warning`, `notice`, `info`, `message`, `for`, `scope`, `hide`, `show_aggregate`, `action_primary`, `read_only`, `all`, `workspace`, `source`, `limit`, `display`, `aggregate`, `list`, `grid`, `timeline`, `detail`

**Additional v0.2 keywords**: `defaults`, `focus`, `group_by`, `where`

**v0.3.1 keywords**: `engine_hint`, `stage`

**v0.5.0 Domain Service Keywords**: `input`, `output`, `guarantees`, `stub`

**v0.7.0 State Machine Keywords**: `transitions`, `requires`, `auto`, `after`, `role`, `manual`, `days`, `hours`, `minutes`

**v0.10.2 Date Arithmetic Keywords**: `today`, `now`, `weeks`, `months`, `years`

**Computed Field Keywords**: `computed`, `sum`, `avg`, `min`, `max`, `days_until`, `days_since`

**Invariant Keywords**: `invariant`, `code`

**v0.9.5 App Config Keywords**: `description`, `multi_tenant`, `audit_trail`, `security_profile`

**v0.9.5 Field Type Keywords**: `money`, `file`, `via`

**v0.7.1 LLM Cognition Keywords**: `intent`, `examples`, `domain`, `patterns`, `extends`, `archetype`, `has_many`, `has_one`, `embeds`, `belongs_to`, `cascade`, `restrict`, `nullify`, `readonly`, `deny`, `scenarios`, `given`, `then`

**Persona & Scenario Keywords**: `scenario`, `demo`, `persona`, `goals`, `proficiency`, `seed_script`, `start_route`

**v0.22.0 Story DSL Keywords**: `story`, `actor`, `trigger`, `unless`

**v0.24.0 TigerBeetle Ledger Keywords**: `ledger`, `transaction`, `transfer`, `debit`, `credit`, `amount`, `account_code`, `ledger_id`, `account_type`, `currency`, `flags`, `sync_to`, `idempotency_key`, `validation`, `execution`, `priority`, `pending_id`, `user_data`, `tenant_scoped`, `metadata_mapping`

**v0.23.0 Process Workflow Keywords**: `process`, `implements`, `parallel`, `compensations`, `compensate`, `on_success`, `on_failure`, `on_any_failure`, `overlap`, `catch_up`, `goto`, `subprocess`, `human_task`, `assignee`, `assignee_role`, `interval`, `timezone`, `sets`, `confirm`, `inputs`, `condition`, `on_true`, `on_false`

**v0.18.0 Event-First Architecture Keywords**: `event_model`, `publish`, `subscribe`, `project`, `topic`, `retention`

**v0.18.0 Governance Keywords (Issue #25)**: `policies`, `tenancy`, `interfaces`, `data_products`, `classify`, `erasure`, `data_product`

**v0.19.0 HLESS (High-Level Event Semantics) Keywords**: `FACT`, `OBSERVATION`, `DERIVATION`

**Stream specification keywords**: `partition_key`, `ordering_scope`, `idempotency`, `outcomes`, `derives_from`, `emits`, `side_effects`, `allowed`, `schema`, `note`, `t_event`, `t_log`, `t_process`, `hless`, `strict`, `warn`, `off`, `llm_model`, `llm_config`, `llm_intent`, `tier`, `max_tokens`, `model_id`, `artifact_store`, `logging`, `log_prompts`, `log_completions`, `redact_pii`, `rate_limits`, `default_model`, `prompt`, `output_schema`, `timeout`, `retry`, `pii`, `max_attempts`, `backoff`, `initial_delay_ms`, `max_delay_ms`, `scan`

**v0.9.0 Messaging Channel Keywords**: `channel`, `send`, `receive`, `provider`, `config`, `provider_config`, `delivery_mode`, `outbox`, `direct`, `throttle`, `per_recipient`, `per_entity`, `per_channel`, `window`, `max_messages`, `on_exceed`, `drop`, `log`, `queue`, `stream`, `email`, `asset`, `document`, `template`, `subject`, `body`, `html_body`, `attachments`, `asset_ref`, `document_ref`, `entity_arg`, `filename`, `for_entity`, `format`, `layout`, `path`, `changed`, `to`, `succeeded`, `failed`, `every`, `cron`, `upsert`, `regex`

**Flow/E2E Test Keywords (v0.3.2)**: `flow`, `steps`, `navigate`, `click`, `fill`, `wait`, `snapshot`, `preconditions`, `authenticated`, `public`, `user_role`, `fixtures`, `view`, `entity_exists`, `entity_not_exists`, `validation_error`, `visible`, `not_visible`, `text_contains`, `redirects_to`, `field_value`, `tags`, `in`, `not`, `is`, `and`, `or`, `asc`, `desc`

**v0.25.0 Construct Keywords**: `enum`, `webhook`, `approval`, `sla` (top-level keywords). Sub-keywords (`events`, `payload`, `approver_role`, `quorum`, `threshold`, `escalation`, `auto_approve`, `starts_when`, `pauses_when`, `completes_when`, `tiers`, `business_hours`, `on_breach`, `notify`) are matched as identifiers to avoid conflicts with existing DSL usage.

## Field Types

All field types supported by the DSL (from `FieldTypeKind` enum):

- `str`
- `text`
- `int`
- `decimal`
- `bool`
- `date`
- `datetime`
- `uuid`
- `enum`
- `ref`
- `email`
- `json`
- `money`
- `file`
- `url`
- `timezone`
- `has_many`
- `has_one`
- `embeds`
- `belongs_to`

## Full Grammar

```ebnf
(*
  DAZZLE DSL v0.25.0 -- EBNF Grammar
  ======================================
  Auto-generated by grammar_gen.py from parser source code.
  Do not edit manually; run `dazzle grammar` to regenerate.

  Anti-Turing Enforcement:
  - Aggregate functions only in computed expressions
  - AGGREGATE_FN explicitly enumerates allowed functions
  - Turing-complete logic lives in service stubs (not DSL)
*)

(* =============================================================================
   Identifiers and Literals
   ============================================================================= *)

IDENT         ::= /[A-Za-z_][A-Za-z0-9_]*/ ;
STRING        ::= '"' /[^\"]*/ '"' ;
NUMBER        ::= /[0-9]+(\.[0-9]+)?/ ;
BOOLEAN       ::= "true" | "false" ;
NEWLINE       ::= /[\r\n]+/ ;
INDENT        ::= (* indentation increase *) ;
DEDENT        ::= (* indentation decrease *) ;

(* =============================================================================
   Top-level Structure
   ============================================================================= *)

dazzle_spec   ::= module_decl? app_decl? statement* EOF ;

module_decl   ::= "module" MODULE_NAME NEWLINE ;

MODULE_NAME   ::= IDENT ("." IDENT)* ;

app_decl      ::= "app" IDENT STRING? (":" NEWLINE INDENT app_body DEDENT)? NEWLINE ;

app_body      ::= (app_config_line NEWLINE)* ;

app_config_line
              ::= "description" ":" STRING
                | "multi_tenant" ":" BOOLEAN
                | "audit_trail" ":" BOOLEAN
                | "security_profile" ":" IDENT
                | IDENT ":" (STRING | BOOLEAN | IDENT) ;

use_decl      ::= "use" MODULE_NAME ("as" IDENT)? NEWLINE ;

statement     ::= entity_decl
                | archetype_decl
                | surface_decl
                | workspace_decl
                | experience_decl
                | service_decl
                | domain_service_decl
                | foreign_model_decl
                | integration_decl
                | flow_decl
                | test_decl
                | persona_decl
                | scenario_decl
                | story_decl
                | process_decl
                | schedule_decl
                | message_decl
                | channel_decl
                | asset_decl
                | document_decl
                | template_decl
                | event_model_decl
                | subscribe_decl
                | projection_decl
                | stream_decl
                | hless_pragma
                | policies_decl
                | tenancy_decl
                | interfaces_decl
                | data_products_decl
                | llm_model_decl
                | llm_config_decl
                | llm_intent_decl
                | ledger_decl
                | transaction_decl
                | enum_decl
                | view_decl
                | webhook_decl
                | approval_decl
                | sla_decl
                | use_decl
                | comment ;

comment       ::= "#" /[^\n]*/ NEWLINE ;

(* =============================================================================
   Field Types and Modifiers
   ============================================================================= *)

type_spec     ::= scalar_type
                | enum_type
                | reference_type ;

(* Scalar types — generated from FieldTypeKind enum *)
scalar_type   ::= "str" "(" NUMBER ")"
                | "text"
                | "int"
                | "decimal" "(" NUMBER "," NUMBER ")"
                | "bool"
                | "date"
                | "datetime"
                | "uuid"
                | "email"
                | "json"
                | "money" ( "(" CURRENCY_CODE ")" )?
                | "file"
                | "url"
                | "timezone" ;

enum_type     ::= "enum" "[" IDENT ("," IDENT)* "]" ;

reference_type ::= "ref" ENTITY_NAME delete_behavior?
                 | "has_many" ENTITY_NAME delete_behavior?
                 | "has_one" ENTITY_NAME delete_behavior?
                 | "embeds" ENTITY_NAME delete_behavior?
                 | "belongs_to" ENTITY_NAME delete_behavior? ;

delete_behavior ::= "cascade" | "restrict" | "nullify" | "readonly" ;

(* =============================================================================
   Entity and Archetype Definitions
   ============================================================================= *)

archetype_decl ::= "archetype" IDENT STRING? ":" NEWLINE
                   INDENT
                     field_line+
                     invariant_line*
                   DEDENT ;

entity_decl   ::= "entity" IDENT STRING? ":" NEWLINE
                  INDENT
                    entity_metadata*
                    field_line+
                    constraint_line*
                    transitions_block?
                    invariant_line*
                    access_block?
                    permit_block?
                    forbid_block?
                    audit_directive?
                    examples_block?
                    publish_directive*
                  DEDENT ;

entity_metadata ::= "intent" ":" STRING NEWLINE
                  | "domain" ":" IDENT NEWLINE
                  | "patterns" ":" IDENT ("," IDENT)* NEWLINE
                  | "extends" ":" IDENT ("," IDENT)* NEWLINE
                  | "archetype" ":" IDENT NEWLINE ;

field_line    ::= IDENT ":" field_def NEWLINE ;

field_def     ::= type_spec field_modifier*
                | "computed" computed_expr ;

field_modifier ::= "required"
                 | "optional"
                 | "pk"
                 | "unique"
                 | "unique?"
                 | "auto_add"
                 | "auto_update"
                 | "sensitive"
                 | "=" literal ;

literal       ::= STRING | NUMBER | BOOLEAN ;

constraint_line ::= ("unique" | "index") IDENT ("," IDENT)* NEWLINE ;

computed_expr ::= aggregate_call
                | field_path
                | computed_expr ("+" | "-" | "*" | "/") computed_expr
                | "(" computed_expr ")"
                | NUMBER ;

field_path    ::= IDENT ("." IDENT)* ;

AGGREGATE_FN  ::= "count" | "sum" | "avg" | "max" | "min"
                | "days_until" | "days_since" ;

aggregate_call ::= AGGREGATE_FN "(" field_path ")" ;

(* =============================================================================
   State Machines
   ============================================================================= *)

transitions_block ::= "transitions" ":" NEWLINE
                      INDENT
                        transition_rule+
                      DEDENT ;

transition_rule ::= from_state "->" to_state transition_spec? NEWLINE ;

from_state    ::= IDENT | "*" ;

to_state      ::= IDENT ;

transition_spec ::= ":" transition_constraint+ ;

transition_constraint
              ::= "requires" IDENT
                | "role" "(" IDENT ("," IDENT)* ")"
                | "auto" "after" NUMBER time_unit ("or" "manual")?
                | "manual" ;

time_unit     ::= "minutes" | "hours" | "days" ;

(* =============================================================================
   Invariants
   ============================================================================= *)

invariant_line ::= "invariant" ":" invariant_expr invariant_meta? NEWLINE ;

invariant_expr ::= invariant_comparison
                 | invariant_expr ("and" | "or") invariant_expr
                 | "not" invariant_expr
                 | "(" invariant_expr ")" ;

invariant_comparison
              ::= invariant_primary comp_op invariant_primary ;

invariant_primary
              ::= field_path | NUMBER | STRING | BOOLEAN
                | date_expr | duration_expr | "(" invariant_expr ")" ;

date_expr     ::= "today" | "now" | date_expr ("+" | "-") duration_expr ;

duration_expr ::= NUMBER ("days" | "hours" | "minutes" | "weeks" | "months" | "years")
                | DURATION_LITERAL ;

DURATION_LITERAL ::= /[0-9]+(d|h|min|w|mo|y)/ ;

comp_op       ::= "=" | "==" | "!=" | ">" | "<" | ">=" | "<=" ;

invariant_meta ::= NEWLINE INDENT
                     ("message" ":" STRING NEWLINE)?
                     ("code" ":" IDENT NEWLINE)?
                   DEDENT ;

(* =============================================================================
   Access Rules and Governance
   ============================================================================= *)

access_block  ::= "access" ":" NEWLINE
                  INDENT
                    access_rule+
                  DEDENT ;

access_rule   ::= ("read" | "write" | "create" | "delete" | "list") ":" condition_expr NEWLINE ;

permit_block  ::= "permit" ":" NEWLINE
                  INDENT
                    policy_rule+
                  DEDENT ;

forbid_block  ::= "forbid" ":" NEWLINE
                  INDENT
                    policy_rule+
                  DEDENT ;

policy_rule   ::= ("create" | "read" | "update" | "delete" | "list") ":" condition_expr NEWLINE ;

audit_directive
              ::= "audit" ":" ("all" | BOOLEAN | "[" IDENT ("," IDENT)* "]") NEWLINE ;

visible_block ::= "visible" ":" NEWLINE
                  INDENT
                    visibility_rule+
                  DEDENT ;

visibility_rule
              ::= "when" ("anonymous" | "authenticated") ":" condition_expr NEWLINE ;

permissions_block
              ::= "permissions" ":" NEWLINE
                  INDENT
                    permission_rule+
                  DEDENT ;

permission_rule
              ::= ("create" | "update" | "delete") ":" ("authenticated" | "anonymous" | condition_expr) NEWLINE ;

condition_expr
              ::= condition_term (("and" | "or") condition_term)*
                | "(" condition_expr ")" ;

condition_term
              ::= comparison
                | "role" "(" IDENT ("," IDENT)* ")"
                | "owner"
                | "tenant"
                | "authenticated"
                | "anonymous" ;

comparison    ::= field_path comp_op value
                | aggregate_call comp_op value ;

value         ::= STRING | NUMBER | IDENT | "[" value ("," value)* "]" ;

operator      ::= "=" | "!=" | ">" | "<" | ">=" | "<="
                | "in" | "not" "in" | "is" | "is" "not" ;

(* =============================================================================
   Example Data
   ============================================================================= *)

examples_block ::= "examples" ":" NEWLINE
                   INDENT
                     example_entry+
                   DEDENT ;

example_entry ::= "-" key_value_list NEWLINE ;

key_value_list ::= IDENT ":" literal ("," IDENT ":" literal)* ;

(* =============================================================================
   Surface Definitions
   ============================================================================= *)

surface_decl  ::= "surface" IDENT STRING? ":" NEWLINE
                  INDENT
                    surface_body_line+
                    ux_block?
                  DEDENT ;

surface_body_line
              ::= "uses" "entity" IDENT NEWLINE
                | "mode" ":" ("view" | "create" | "edit" | "list" | "custom") NEWLINE
                | "priority" ":" ("critical" | "high" | "medium" | "low") NEWLINE
                | section_decl
                | surface_action_decl ;

section_decl  ::= "section" IDENT STRING? ":" NEWLINE
                  INDENT
                    surface_element_line+
                  DEDENT ;

surface_element_line
              ::= "field" IDENT STRING? surface_element_option* NEWLINE ;

surface_element_option
              ::= IDENT "=" literal ;

surface_action_decl
              ::= "action" IDENT STRING? ":" NEWLINE
                  INDENT
                    "on" surface_trigger "->" outcome NEWLINE
                  DEDENT ;

surface_trigger
              ::= "submit" | "click" | "auto" ;

outcome       ::= "surface" IDENT
                | "experience" IDENT ("step" IDENT)?
                | "integration" IDENT "action" IDENT ;

(* =============================================================================
   UX Semantic Layer
   ============================================================================= *)

ux_block      ::= "ux" ":" NEWLINE
                  INDENT
                    ux_directive+
                  DEDENT ;

ux_directive  ::= "purpose" ":" STRING NEWLINE
                | "show" ":" field_list NEWLINE
                | "sort" ":" sort_expr ("," sort_expr)* NEWLINE
                | "filter" ":" field_list NEWLINE
                | "search" ":" field_list NEWLINE
                | "empty" ":" STRING NEWLINE
                | attention_block
                | persona_block ;

field_list    ::= IDENT ("," IDENT)* ;

sort_expr     ::= IDENT ("asc" | "desc")? ;

attention_block
              ::= "attention" signal_level ":" NEWLINE
                  INDENT
                    "when" ":" condition_expr NEWLINE
                    "message" ":" STRING NEWLINE
                    ("action" ":" IDENT NEWLINE)?
                  DEDENT ;

signal_level  ::= "critical" | "warning" | "notice" | "info" ;

persona_block ::= "for" IDENT ":" NEWLINE
                  INDENT
                    persona_directive+
                  DEDENT ;

persona_directive
              ::= "scope" ":" scope_expr NEWLINE
                | "purpose" ":" STRING NEWLINE
                | "show" ":" field_list NEWLINE
                | "hide" ":" field_list NEWLINE
                | "show_aggregate" ":" IDENT ("," IDENT)* NEWLINE
                | "action_primary" ":" IDENT NEWLINE
                | "read_only" ":" BOOLEAN NEWLINE ;

scope_expr    ::= "all" | comparison (("and" | "or") comparison)* ;

(* =============================================================================
   Workspace Definitions
   ============================================================================= *)

workspace_decl ::= "workspace" IDENT STRING? ":" NEWLINE
                   INDENT
                     ("purpose" ":" STRING NEWLINE)?
                     ("access" ":" IDENT NEWLINE)?
                     workspace_region+
                     ux_block?
                   DEDENT ;

workspace_region
              ::= IDENT ":" NEWLINE
                  INDENT
                    region_directive+
                  DEDENT ;

region_directive
              ::= "source" ":" IDENT NEWLINE
                | "filter" ":" filter_expr NEWLINE
                | "sort" ":" sort_expr ("," sort_expr)* NEWLINE
                | "limit" ":" NUMBER NEWLINE
                | "display" ":" ("list" | "grid" | "timeline" | "map" | "detail") NEWLINE
                | "action" ":" IDENT NEWLINE
                | "empty" ":" STRING NEWLINE
                | "stage" ":" STRING NEWLINE
                | "aggregate" ":" NEWLINE INDENT metric_line+ DEDENT ;

metric_line   ::= IDENT ":" aggregate_expr NEWLINE ;

aggregate_expr ::= aggregate_call | NUMBER | aggregate_expr ("+" | "-" | "*" | "/") aggregate_expr ;

filter_expr   ::= "all" | comparison (("and" | "or") comparison)* ;

(* =============================================================================
   Experience Definitions
   ============================================================================= *)

experience_decl
              ::= "experience" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("access" ":" IDENT NEWLINE)?
                    ("priority" ":" ("critical" | "high" | "medium" | "low") NEWLINE)?
                    "start" "at" "step" IDENT NEWLINE
                    experience_step+
                  DEDENT ;

experience_step
              ::= "step" IDENT ":" NEWLINE
                  INDENT
                    "kind" ":" ("surface" | "process" | "integration") NEWLINE
                    step_kind_body
                    step_transition*
                  DEDENT ;

step_kind_body
              ::= "surface" IDENT NEWLINE
                | "integration" IDENT "action" IDENT NEWLINE ;

step_transition
              ::= "on" ("success" | "failure") "->" "step" IDENT NEWLINE ;

(* =============================================================================
   Story Definitions
   ============================================================================= *)

story_decl    ::= "story" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("actor" ":" IDENT NEWLINE)?
                    ("trigger" ":" IDENT NEWLINE)?
                    ("scope" ":" "[" IDENT ("," IDENT)* "]" NEWLINE)?
                    given_block?
                    then_block?
                    unless_block?
                  DEDENT ;

given_block   ::= "given" ":" NEWLINE
                  INDENT
                    ("-" STRING NEWLINE)+
                  DEDENT ;

then_block    ::= "then" ":" NEWLINE
                  INDENT
                    ("-" STRING NEWLINE)+
                  DEDENT ;

unless_block  ::= "unless" ":" NEWLINE
                  INDENT
                    ("-" STRING NEWLINE)+
                  DEDENT ;

(* =============================================================================
   Process Workflows and Schedules
   ============================================================================= *)

process_decl  ::= "process" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("implements" ":" "[" IDENT ("," IDENT)* "]" NEWLINE)?
                    process_trigger?
                    process_io*
                    process_step+
                    compensations_block?
                  DEDENT ;

process_trigger
              ::= "trigger" ":" NEWLINE
                  INDENT
                    ("when" ":" trigger_expr NEWLINE)?
                    ("schedule" ":" cron_expr NEWLINE)?
                  DEDENT ;

trigger_expr  ::= "entity" IDENT ("status" "->" IDENT)?
                | "event" IDENT
                | "manual" ;

cron_expr     ::= STRING
                | "every" NUMBER ("minutes" | "hours" | "days")
                | "cron" STRING ;

process_io    ::= ("input" | "output") ":" NEWLINE
                  INDENT
                    (IDENT ":" type_spec field_modifier* NEWLINE)+
                  DEDENT ;

process_step  ::= "step" IDENT STRING? ":" NEWLINE
                  INDENT
                    step_body
                  DEDENT ;

step_body     ::= ("service" ":" IDENT NEWLINE)?
                  ("operation" ":" IDENT NEWLINE)?
                  ("channel" ":" IDENT NEWLINE)?
                  ("mapping" ":" NEWLINE INDENT mapping_line+ DEDENT)?
                  ("on_success" ":" IDENT NEWLINE)?
                  ("on_failure" ":" IDENT NEWLINE)?
                  ("retry" ":" NEWLINE INDENT retry_config DEDENT)?
                  ("timeout" ":" NUMBER NEWLINE)?
                  ("parallel" ":" "[" IDENT ("," IDENT)* "]" NEWLINE)?
                  ("subprocess" ":" IDENT NEWLINE)?
                  ("human_task" ":" NEWLINE INDENT human_task_body DEDENT)?
                  ("condition" ":" condition_expr NEWLINE)?
                  ("on_true" ":" IDENT NEWLINE)?
                  ("on_false" ":" IDENT NEWLINE)?
                  ("sets" ":" NEWLINE INDENT (IDENT ":" (literal | field_path) NEWLINE)+ DEDENT)? ;

mapping_line  ::= IDENT ":" (literal | field_path) NEWLINE ;

retry_config  ::= ("max_attempts" ":" NUMBER NEWLINE)?
                  ("backoff" ":" IDENT NEWLINE)?
                  ("initial_delay_ms" ":" NUMBER NEWLINE)?
                  ("max_delay_ms" ":" NUMBER NEWLINE)? ;

human_task_body
              ::= ("assignee" ":" field_path NEWLINE)?
                  ("assignee_role" ":" IDENT NEWLINE)?
                  ("surface" ":" IDENT NEWLINE)?
                  ("confirm" ":" STRING NEWLINE)?
                  ("inputs" ":" NEWLINE INDENT (IDENT ":" type_spec NEWLINE)+ DEDENT)? ;

compensations_block
              ::= "compensations" ":" NEWLINE
                  INDENT
                    ("compensate" IDENT ":" IDENT NEWLINE)+
                  DEDENT ;

schedule_decl ::= "schedule" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("process" ":" IDENT NEWLINE)?
                    ("cron" ":" STRING NEWLINE | "interval" ":" STRING NEWLINE | "every" ":" STRING NEWLINE)?
                    ("timezone" ":" STRING NEWLINE)?
                    ("input" ":" NEWLINE INDENT (IDENT ":" literal NEWLINE)+ DEDENT)?
                    ("overlap" ":" IDENT NEWLINE)?
                    ("catch_up" ":" BOOLEAN NEWLINE)?
                  DEDENT ;

(* =============================================================================
   Service Definitions
   ============================================================================= *)

service_decl  ::= "service" IDENT STRING? ":" NEWLINE
                  INDENT
                    service_body_line+
                  DEDENT ;

service_body_line
              ::= "spec" ":" ("url" STRING | "inline" STRING) NEWLINE
                | "auth_profile" ":" AUTH_KIND auth_option* NEWLINE
                | "owner" ":" STRING NEWLINE ;

AUTH_KIND     ::= "oauth2_legacy" | "oauth2_pkce" | "jwt_static"
                | "api_key_header" | "api_key_query" | "none" ;

auth_option   ::= IDENT "=" literal ;

domain_service_decl
              ::= "service" IDENT STRING? ":" NEWLINE
                  INDENT
                    "kind" ":" ("domain_logic" | "validation" | "integration" | "workflow") NEWLINE
                    service_io_block?
                    service_io_block?
                    guarantees_block?
                    ("stub" ":" ("python" | "typescript") NEWLINE)?
                  DEDENT ;

service_io_block
              ::= ("input" | "output") ":" NEWLINE
                  INDENT
                    (IDENT ":" type_spec field_modifier* NEWLINE)+
                  DEDENT ;

guarantees_block
              ::= "guarantees" ":" NEWLINE
                  INDENT
                    ("-" STRING NEWLINE)+
                  DEDENT ;

(* =============================================================================
   Foreign Model Definitions
   ============================================================================= *)

foreign_model_decl
              ::= "foreign_model" IDENT "from" IDENT STRING? ":" NEWLINE
                  INDENT
                    foreign_model_line+
                  DEDENT ;

foreign_model_line
              ::= "key" ":" IDENT ("," IDENT)* NEWLINE
                | "constraint" ("read_only" | "event_driven" | "batch_import") (IDENT "=" literal)* NEWLINE
                | "field" IDENT ":" type_spec field_modifier* NEWLINE ;

(* =============================================================================
   Integration Definitions
   ============================================================================= *)

integration_decl
              ::= "integration" IDENT STRING? ":" NEWLINE
                  INDENT
                    integration_body+
                  DEDENT ;

integration_body
              ::= "uses" "service" IDENT ("," IDENT)* NEWLINE
                | "uses" "foreign_model" IDENT ("," IDENT)* NEWLINE
                | integration_action_decl
                | sync_decl ;

integration_action_decl
              ::= "action" IDENT ":" NEWLINE
                  INDENT
                    "when" "surface" IDENT "submitted" NEWLINE
                    "call" IDENT "." IDENT "with" ":" NEWLINE
                    INDENT mapping_rule+ DEDENT
                    ("map" "response" IDENT "->" "entity" IDENT ":" NEWLINE
                    INDENT mapping_rule+ DEDENT)?
                  DEDENT ;

mapping_rule  ::= IDENT "<-" (field_path | literal) NEWLINE ;

sync_decl     ::= "sync" IDENT ":" NEWLINE
                  INDENT
                    "mode" ":" ("scheduled" | "event_driven") NEWLINE
                    ("schedule" ":" STRING NEWLINE)?
                    "from" IDENT "." IDENT "as" IDENT NEWLINE
                    "into" "entity" IDENT NEWLINE
                    ("match" "on" ":" NEWLINE INDENT
                      (IDENT "<->" IDENT NEWLINE)+ DEDENT)?
                  DEDENT ;

(* =============================================================================
   E2E Test Flows
   ============================================================================= *)

flow_decl     ::= "flow" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("priority" ":" ("critical" | "high" | "medium" | "low") NEWLINE)?
                    ("tags" ":" IDENT ("," IDENT)* NEWLINE)?
                    preconditions_block?
                    ("steps" ":" NEWLINE INDENT flow_step+ DEDENT)?
                    flow_step*
                  DEDENT ;

preconditions_block
              ::= "preconditions" ":" NEWLINE
                  INDENT
                    precondition_line+
                  DEDENT ;

precondition_line
              ::= "authenticated" ":" BOOLEAN NEWLINE
                | "user_role" ":" IDENT NEWLINE
                | "fixtures" ":" NEWLINE INDENT fixture_line+ DEDENT ;

fixture_line  ::= IDENT ":" NEWLINE INDENT (IDENT ":" literal NEWLINE)+ DEDENT ;

flow_step     ::= step_action target assertion* NEWLINE ;

step_action   ::= "navigate" | "fill" | "click" | "wait" | "assert" | "snapshot" ;

target        ::= "view" ":" IDENT
                | "field" ":" IDENT "." IDENT
                | "action" ":" IDENT "." IDENT
                | "element" ":" STRING ;

assertion     ::= "expect" assertion_check ;

assertion_check
              ::= "visible" | "hidden" | "enabled" | "disabled"
                | "text" "=" STRING
                | "value" "=" literal
                | "count" "=" NUMBER
                | "entity_exists" IDENT
                | "entity_not_exists" IDENT
                | "redirects_to" IDENT ;

(* =============================================================================
   API Contract Tests
   ============================================================================= *)

test_decl     ::= "test" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("setup" ":" NEWLINE INDENT setup_line+ DEDENT)?
                    test_step+
                  DEDENT ;

setup_line    ::= IDENT ":" NEWLINE
                  INDENT
                    (IDENT ":" literal NEWLINE)+
                  DEDENT ;

test_step     ::= ("create" | "update" | "delete" | "get" | "query") IDENT ("with" ":" NEWLINE
                  INDENT (IDENT ":" literal NEWLINE)+ DEDENT)?
                  ("expect" ":" NEWLINE INDENT expect_line+ DEDENT)? NEWLINE ;

expect_line   ::= "status" ":" NUMBER NEWLINE
                | "count" ":" NUMBER NEWLINE
                | "error_message" ":" STRING NEWLINE
                | IDENT ":" literal NEWLINE ;

(* =============================================================================
   Scenario and Demo Data
   ============================================================================= *)

persona_decl  ::= "persona" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("description" ":" STRING NEWLINE)?
                    ("goals" ":" NEWLINE INDENT ("-" STRING NEWLINE)+ DEDENT)?
                    ("proficiency" ":" IDENT NEWLINE)?
                  DEDENT ;

scenario_decl ::= "scenario" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("description" ":" STRING NEWLINE)?
                    ("personas" ":" NEWLINE INDENT persona_entry+ DEDENT)?
                    ("seed_script" ":" STRING NEWLINE)?
                  DEDENT ;

persona_entry ::= IDENT ":" NEWLINE
                  INDENT
                    ("start_route" ":" STRING NEWLINE)?
                    ("goals" ":" NEWLINE INDENT ("-" STRING NEWLINE)+ DEDENT)?
                  DEDENT ;

demo_decl     ::= "demo" IDENT ":" NEWLINE
                  INDENT
                    (IDENT ":" literal NEWLINE)+
                  DEDENT ;

(* =============================================================================
   Messaging Channels
   ============================================================================= *)

message_decl  ::= "message" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("channel" ":" IDENT NEWLINE)?
                    ("trigger" ":" NEWLINE INDENT trigger_body DEDENT)?
                    ("send" ":" NEWLINE INDENT send_body DEDENT)?
                  DEDENT ;

trigger_body  ::= ("when" ":" trigger_when NEWLINE)*
                  ("schedule" ":" STRING NEWLINE)? ;

trigger_when  ::= "entity" IDENT ("created" | "updated" | "deleted" | "status" "changed" "to" IDENT)
                | "event" IDENT ;

send_body     ::= ("to" ":" field_path NEWLINE)?
                  ("subject" ":" STRING NEWLINE)?
                  ("body" ":" STRING NEWLINE)?
                  ("template" ":" IDENT NEWLINE)? ;

channel_decl  ::= "channel" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("provider" ":" IDENT NEWLINE)?
                    ("provider_config" ":" NEWLINE INDENT (IDENT ":" literal NEWLINE)+ DEDENT)?
                    ("delivery_mode" ":" ("outbox" | "direct") NEWLINE)?
                    ("throttle" ":" NEWLINE INDENT throttle_config DEDENT)?
                  DEDENT ;

throttle_config
              ::= ("scope" ":" ("per_recipient" | "per_entity" | "per_channel") NEWLINE)?
                  ("window" ":" STRING NEWLINE)?
                  ("max_messages" ":" NUMBER NEWLINE)?
                  ("on_exceed" ":" ("drop" | "log" | "queue") NEWLINE)? ;

asset_decl    ::= "asset" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("for_entity" ":" IDENT NEWLINE)?
                    ("format" ":" IDENT ("," IDENT)* NEWLINE)?
                    ("path" ":" STRING NEWLINE)?
                  DEDENT ;

document_decl ::= "document" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("for_entity" ":" IDENT NEWLINE)?
                    ("layout" ":" IDENT NEWLINE)?
                    ("format" ":" IDENT NEWLINE)?
                  DEDENT ;

template_decl ::= "template" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("subject" ":" STRING NEWLINE)?
                    ("body" ":" STRING NEWLINE)?
                    ("html_body" ":" STRING NEWLINE)?
                  DEDENT ;

(* =============================================================================
   Event-First Architecture
   ============================================================================= *)

event_model_decl
              ::= "event_model" ":" NEWLINE
                  INDENT
                    event_topic*
                    event_def*
                  DEDENT ;

event_topic   ::= "topic" IDENT ":" NEWLINE
                  INDENT
                    ("retention" ":" (STRING | DURATION_LITERAL) NEWLINE)?
                    ("partition_key" ":" IDENT NEWLINE)?
                  DEDENT ;

event_def     ::= "event" IDENT ":" NEWLINE
                  INDENT
                    ("topic" ":" IDENT NEWLINE)?
                    (IDENT ":" type_spec NEWLINE)*
                  DEDENT ;

subscribe_decl
              ::= "subscribe" IDENT ":" NEWLINE
                  INDENT
                    ("event" ":" IDENT NEWLINE)?
                    ("filter" ":" condition_expr NEWLINE)?
                    ("action" ":" IDENT NEWLINE)?
                    ("service" ":" IDENT NEWLINE)?
                    ("upsert" ":" IDENT NEWLINE)?
                  DEDENT ;

projection_decl
              ::= "project" IDENT ":" NEWLINE
                  INDENT
                    ("from" ":" IDENT NEWLINE)?
                    ("into" ":" IDENT NEWLINE)?
                    ("mapping" ":" NEWLINE INDENT (IDENT ":" field_path NEWLINE)+ DEDENT)?
                  DEDENT ;

publish_directive
              ::= "publish" IDENT (":" NEWLINE
                  INDENT
                    ("topic" ":" IDENT NEWLINE)?
                    ("when" ":" trigger_when NEWLINE)?
                    (IDENT ":" (field_path | literal) NEWLINE)*
                  DEDENT)? NEWLINE ;

(* =============================================================================
   HLESS Event Semantics
   ============================================================================= *)

stream_decl   ::= "stream" IDENT ":" NEWLINE
                  INDENT
                    ("kind" ":" ("INTENT" | "FACT" | "OBSERVATION" | "DERIVATION") NEWLINE)?
                    ("description" ":" STRING NEWLINE)?
                    ("schema" IDENT ":" NEWLINE
                      INDENT (IDENT ":" type_spec field_modifier* NEWLINE)+ DEDENT)?
                    ("partition_key" ":" IDENT NEWLINE)?
                    ("ordering_scope" ":" IDENT NEWLINE)?
                    ("idempotency" ":" IDENT NEWLINE)?
                    ("outcomes" ":" NEWLINE INDENT ("-" STRING NEWLINE)+ DEDENT)?
                    ("derives_from" ":" "[" IDENT ("," IDENT)* "]" NEWLINE)?
                    ("emits" ":" "[" IDENT ("," IDENT)* "]" NEWLINE)?
                    ("side_effects" ":" IDENT NEWLINE)?
                    ("note" ":" STRING NEWLINE)?
                  DEDENT ;

hless_pragma  ::= "hless" ":" ("strict" | "warn" | "off") NEWLINE ;

(* =============================================================================
   TigerBeetle Ledgers and Transactions
   ============================================================================= *)

ledger_decl   ::= "ledger" IDENT STRING? ":" NEWLINE
                  INDENT
                    ledger_body_line+
                  DEDENT ;

ledger_body_line
              ::= "intent" ":" STRING NEWLINE
                | "account_code" ":" NUMBER NEWLINE
                | "ledger_id" ":" NUMBER NEWLINE
                | "account_type" ":" ACCOUNT_TYPE NEWLINE
                | "currency" ":" CURRENCY_CODE NEWLINE
                | "flags" ":" ACCOUNT_FLAG ("," ACCOUNT_FLAG)* NEWLINE
                | "sync_to" ":" IDENT "." IDENT ("trigger" ":" SYNC_TRIGGER)? NEWLINE
                | "tenant_scoped" ":" BOOLEAN NEWLINE
                | metadata_mapping_block ;

ACCOUNT_TYPE  ::= "asset" | "liability" | "equity" | "revenue" | "expense" ;

CURRENCY_CODE ::= /[A-Z]{3}/ ;

ACCOUNT_FLAG  ::= "debits_must_not_exceed_credits"
                | "credits_must_not_exceed_debits"
                | "linked"
                | "history" ;

SYNC_TRIGGER  ::= "after_transfer" | "scheduled" STRING | "on_demand" ;

metadata_mapping_block
              ::= "metadata_mapping" ":" NEWLINE
                  INDENT
                    (IDENT ":" ("ref" IDENT "." IDENT | STRING) NEWLINE)+
                  DEDENT ;

transaction_decl
              ::= "transaction" IDENT STRING? ":" NEWLINE
                  INDENT
                    transaction_body_line+
                  DEDENT ;

transaction_body_line
              ::= "intent" ":" STRING NEWLINE
                | "execution" ":" ("sync" | "async") NEWLINE
                | "priority" ":" ("critical" | "high" | "normal" | "low") NEWLINE
                | "timeout" ":" NUMBER NEWLINE
                | transfer_block
                | "idempotency_key" ":" field_path NEWLINE
                | validation_block ;

transfer_block
              ::= "transfer" IDENT ":" NEWLINE
                  INDENT
                    transfer_line+
                  DEDENT ;

transfer_line ::= "debit" ":" IDENT NEWLINE
                | "credit" ":" IDENT NEWLINE
                | "amount" ":" amount_expr NEWLINE
                | "code" ":" NUMBER NEWLINE
                | "flags" ":" TRANSFER_FLAG ("," TRANSFER_FLAG)* NEWLINE
                | "pending_id" ":" STRING NEWLINE
                | user_data_block ;

TRANSFER_FLAG ::= "linked" | "pending" | "post_pending" | "void_pending" | "balancing" ;

amount_expr   ::= amount_term (("+" | "-" | "*" | "/") amount_term)? ;

amount_term   ::= NUMBER | field_path ;

user_data_block
              ::= "user_data" ":" NEWLINE
                  INDENT
                    (IDENT ":" (STRING | IDENT) NEWLINE)+
                  DEDENT ;

validation_block
              ::= "validation" ":" NEWLINE
                  INDENT
                    ("-" (field_path | STRING) NEWLINE)+
                  DEDENT ;

(* =============================================================================
   Governance Sections
   ============================================================================= *)

policies_decl ::= "policies" ":" NEWLINE
                  INDENT
                    policy_line+
                  DEDENT ;

policy_line   ::= "classify" IDENT "." IDENT "as" IDENT NEWLINE
                | "erasure" IDENT ":" IDENT NEWLINE ;

tenancy_decl  ::= "tenancy" ":" NEWLINE
                  INDENT
                    ("mode" ":" IDENT NEWLINE)?
                    (IDENT ":" (STRING | IDENT | BOOLEAN) NEWLINE)*
                  DEDENT ;

interfaces_decl
              ::= "interfaces" ":" NEWLINE
                  INDENT
                    (IDENT ":" (STRING | IDENT | BOOLEAN) NEWLINE)*
                  DEDENT ;

data_products_decl
              ::= "data_products" ":" NEWLINE
                  INDENT
                    data_product_def+
                  DEDENT ;

data_product_def
              ::= "data_product" IDENT ":" NEWLINE
                  INDENT
                    (IDENT ":" (STRING | IDENT | BOOLEAN) NEWLINE)*
                  DEDENT ;

(* =============================================================================
   LLM Jobs
   ============================================================================= *)

llm_model_decl
              ::= "llm_model" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("tier" ":" IDENT NEWLINE)?
                    ("model_id" ":" STRING NEWLINE)?
                    ("max_tokens" ":" NUMBER NEWLINE)?
                    ("cost_per_1k_input" ":" NUMBER NEWLINE)?
                    ("cost_per_1k_output" ":" NUMBER NEWLINE)?
                  DEDENT ;

llm_config_decl
              ::= "llm_config" ":" NEWLINE
                  INDENT
                    ("default_model" ":" IDENT NEWLINE)?
                    ("artifact_store" ":" STRING NEWLINE)?
                    ("logging" ":" NEWLINE INDENT llm_logging_body DEDENT)?
                    ("rate_limits" ":" NEWLINE INDENT (IDENT ":" NUMBER NEWLINE)+ DEDENT)?
                  DEDENT ;

llm_logging_body
              ::= ("log_prompts" ":" BOOLEAN NEWLINE)?
                  ("log_completions" ":" BOOLEAN NEWLINE)?
                  ("redact_pii" ":" BOOLEAN NEWLINE)? ;

llm_intent_decl
              ::= "llm_intent" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("model" ":" IDENT NEWLINE)?
                    ("prompt" ":" STRING NEWLINE)?
                    ("input" ":" NEWLINE INDENT (IDENT ":" type_spec NEWLINE)+ DEDENT)?
                    ("output_schema" ":" NEWLINE INDENT (IDENT ":" type_spec NEWLINE)+ DEDENT)?
                    ("timeout" ":" NUMBER NEWLINE)?
                    ("retry" ":" NEWLINE INDENT retry_config DEDENT)?
                    ("pii" ":" NEWLINE INDENT pii_config DEDENT)?
                  DEDENT ;

pii_config    ::= ("scan" ":" BOOLEAN NEWLINE)?
                  ("action" ":" IDENT NEWLINE)?
                  ("fields" ":" "[" IDENT ("," IDENT)* "]" NEWLINE)? ;

(* =============================================================================
   v0.25.0 Shared Enums
   ============================================================================= *)

enum_decl     ::= "enum" IDENT STRING? ":" NEWLINE
                  INDENT
                    (IDENT STRING? NEWLINE)+
                  DEDENT ;

(* =============================================================================
   v0.25.0 Views (Read-Only Derived Data)
   ============================================================================= *)

view_decl     ::= "view" IDENT STRING? ":" NEWLINE
                  INDENT
                    view_body_line+
                  DEDENT ;

view_body_line
              ::= "source" ":" IDENT NEWLINE
                | "filter" ":" condition_expr NEWLINE
                | "group_by" ":" "[" view_group_item ("," view_group_item)* "]" NEWLINE
                | view_fields_block ;

view_group_item
              ::= IDENT
                | IDENT "(" IDENT ")" ;

view_fields_block
              ::= "fields" ":" NEWLINE
                  INDENT
                    (IDENT ":" (type_spec | AGGREGATE_FN "(" field_path? ")") NEWLINE)+
                  DEDENT ;

(* =============================================================================
   v0.25.0 Webhooks (Outbound HTTP Notifications)
   ============================================================================= *)

webhook_decl  ::= "webhook" IDENT STRING? ":" NEWLINE
                  INDENT
                    webhook_body_line+
                  DEDENT ;

webhook_body_line
              ::= "entity" ":" IDENT NEWLINE
                | "events" ":" "[" WEBHOOK_EVENT ("," WEBHOOK_EVENT)* "]" NEWLINE
                | "url" ":" (STRING | config_ref) NEWLINE
                | webhook_auth_block
                | webhook_payload_block
                | webhook_retry_block ;

WEBHOOK_EVENT ::= "created" | "updated" | "deleted" ;

config_ref    ::= "config" "(" STRING ")" ;

webhook_auth_block
              ::= "auth" ":" NEWLINE
                  INDENT
                    ("method" ":" WEBHOOK_AUTH_METHOD NEWLINE)?
                    ("secret" ":" (STRING | config_ref) NEWLINE)?
                  DEDENT ;

WEBHOOK_AUTH_METHOD
              ::= "hmac_sha256" | "bearer" | "basic" ;

webhook_payload_block
              ::= "payload" ":" NEWLINE
                  INDENT
                    ("include" ":" "[" dotted_ident ("," dotted_ident)* "]" NEWLINE)?
                    ("format" ":" IDENT NEWLINE)?
                  DEDENT ;

dotted_ident  ::= IDENT ("." IDENT)* ;

webhook_retry_block
              ::= "retry" ":" NEWLINE
                  INDENT
                    ("max_attempts" ":" NUMBER NEWLINE)?
                    ("backoff" ":" IDENT NEWLINE)?
                  DEDENT ;

(* =============================================================================
   v0.25.0 Approvals (First-Class Approval Gates)
   ============================================================================= *)

approval_decl ::= "approval" IDENT STRING? ":" NEWLINE
                  INDENT
                    approval_body_line+
                  DEDENT ;

approval_body_line
              ::= "entity" ":" IDENT NEWLINE
                | "trigger" ":" IDENT "->" IDENT NEWLINE
                | "approver_role" ":" IDENT NEWLINE
                | "quorum" ":" NUMBER NEWLINE
                | "threshold" ":" condition_expr NEWLINE
                | approval_escalation_block
                | approval_auto_block
                | approval_outcomes_block ;

approval_escalation_block
              ::= "escalation" ":" NEWLINE
                  INDENT
                    ("after" ":" NUMBER TIME_UNIT NEWLINE)?
                    ("to" ":" IDENT NEWLINE)?
                  DEDENT ;

approval_auto_block
              ::= "auto_approve" ":" NEWLINE
                  INDENT
                    "when" ":" condition_expr NEWLINE
                  DEDENT ;

approval_outcomes_block
              ::= "outcomes" ":" NEWLINE
                  INDENT
                    (IDENT "->" IDENT NEWLINE)+
                  DEDENT ;

(* =============================================================================
   v0.25.0 SLAs (Deadline Escalation)
   ============================================================================= *)

sla_decl      ::= "sla" IDENT STRING? ":" NEWLINE
                  INDENT
                    sla_body_line+
                  DEDENT ;

sla_body_line ::= "entity" ":" IDENT NEWLINE
                | "starts_when" ":" sla_condition NEWLINE
                | "pauses_when" ":" sla_condition NEWLINE
                | "completes_when" ":" sla_condition NEWLINE
                | sla_tiers_block
                | sla_business_hours_block
                | sla_breach_block ;

sla_condition ::= IDENT ("->" | "=") IDENT ;

TIME_UNIT     ::= "minutes" | "hours" | "days" ;

sla_tiers_block
              ::= "tiers" ":" NEWLINE
                  INDENT
                    (IDENT ":" NUMBER TIME_UNIT NEWLINE)+
                  DEDENT ;

sla_business_hours_block
              ::= "business_hours" ":" NEWLINE
                  INDENT
                    ("schedule" ":" STRING NEWLINE)?
                    ("timezone" ":" STRING NEWLINE)?
                  DEDENT ;

sla_breach_block
              ::= "on_breach" ":" NEWLINE
                  INDENT
                    ("notify" ":" IDENT NEWLINE)?
                    ("set" ":" IDENT "=" IDENT NEWLINE)*
                  DEDENT ;

```

## DSL Examples

### Core

```dsl
module my_app
app todo "Todo App":
  description: "A simple todo application"
  multi_tenant: false

entity Task "Task":
  intent: "Tracks work items for users"
  domain: productivity
  patterns: crud, status_tracking
  id: uuid pk
  title: str(200) required
  completed: bool=false
  status: enum[open, in_progress, done]
  due_date: date optional
  assigned_to: ref User
  items: has_many TaskItem cascade
  days_remaining: computed days_until(due_date)

  transitions:
    open -> in_progress: requires assigned_to
    in_progress -> done: manual
    * -> open: role(admin)

  invariant: due_date > today
    message: "Due date must be in the future"
    code: INVALID_DUE_DATE

  access:
    read: role(viewer) or owner
    write: role(editor) or owner
    delete: role(admin)

  audit: all

  examples:
    - title: "Write docs", completed: false, status: open
```

### Surface

```dsl
surface task_list "Tasks":
  uses entity Task
  mode: list
  priority: high
  section main:
    field title "Title"
    field status "Status"
    field due_date "Due"

  action create_task "New Task":
    on submit -> surface task_form

  ux:
    purpose: "View and manage tasks"
    show: title, status, due_date
    sort: due_date asc
    filter: status, assigned_to
    search: title
    empty: "No tasks yet"

    attention warning:
      when: days_until(due_date) < 3
      message: "Task due soon"
      action: task_detail

    for manager:
      scope: all
      show: title, status, assigned_to
      action_primary: task_detail

workspace dashboard "Dashboard":
  purpose: "Overview of all work"
  urgent_tasks:
    source: task_list
    filter: status = open and days_until(due_date) < 7
    sort: due_date asc
    limit: 10
    display: list
```

### Workflow

```dsl
story ST-001 "User completes task":
  actor: StaffUser
  trigger: status_changed
  scope: [Task]

  given:
    - Task.status is 'in_progress'
    - Task.assigned_to is set

  then:
    - Task.status becomes 'done'
    - Task.completed_at is recorded

process order_fulfillment "Order Fulfillment":
  implements: [ST-001]

  trigger:
    when: entity Order status -> confirmed

  input:
    order_id: uuid required

  step validate "Validate Order":
    service: OrderService
    operation: validate
    on_success: pick
    on_failure: cancel

  step pick "Pick Items":
    human_task:
      assignee_role: warehouse
      surface: pick_list
      confirm: "All items picked?"
    on_success: ship

schedule daily_report "Daily Report":
  process: generate_report
  cron: "0 9 * * *"
  timezone: "Europe/London"
```

### Integration

```dsl
service companies_house "Companies House API":
  spec: url "https://api.company-information.service.gov.uk"
  auth_profile: api_key_header key=CH_API_KEY
  owner: "GOV.UK"

service PricingEngine "Pricing Engine":
  kind: domain_logic
  input:
    product_id: uuid required
    quantity: int required
  output:
    unit_price: decimal(10,2)
    total: decimal(10,2)
  guarantees:
    - "Total = unit_price * quantity"
  stub: python

foreign_model CompanyProfile from companies_house:
  key: company_number
  constraint read_only
  field company_number: str(8) required
  field company_name: str(200)

integration ch_integration "CH Integration":
  uses service companies_house
  uses foreign_model CompanyProfile

  action lookup_company:
    when surface company_form submitted
    call companies_house.search with:
      q <- company_name
    map response CompanyProfile -> entity Company:
      name <- company_name
      reg_number <- company_number
```

### Testing

```dsl
flow happy_path_task "Create and complete a task":
  priority: critical
  tags: smoke, regression

  preconditions:
    authenticated: true
    user_role: editor

  steps:
    navigate view: task_list
    click action: Task.create
    fill field: Task.title "My Task"
    click action: Task.save
    assert expect entity_exists Task
    assert expect visible

test create_task "Create Task API":
  setup:
    user:
      role: editor

  create Task with:
    title: "Test Task"
    status: open
  expect:
    status: 201
```

### Eventing

```dsl
event_model:
  topic orders:
    retention: 7d
    partition_key: order_id

  event OrderCreated:
    topic: orders
    order_id: uuid
    customer_id: uuid
    total: decimal(10,2)

subscribe notify_customer:
  event: OrderCreated
  action: send_confirmation
  service: NotificationService

channel email_channel "Email":
  provider: smtp
  provider_config:
    host: "smtp.example.com"
    port: 587
  delivery_mode: outbox

stream order_placement_requests:
  kind: INTENT
  description: "Captures requests to place orders"
  schema OrderPlacementRequested:
    order_id: uuid required
    customer_id: uuid required
  partition_key: customer_id
  idempotency: order_id
```

### Financial

```dsl
ledger CustomerWallet "Customer Wallet":
  intent: "Track customer prepaid balances"
  account_code: 1001
  ledger_id: 1
  account_type: asset
  currency: GBP
  flags: debits_must_not_exceed_credits
  sync_to: Customer.balance_cache

transaction RecordPayment "Record Payment":
  execution: async
  priority: high

  transfer revenue:
    debit: CustomerWallet
    credit: Revenue
    amount: payment.amount
    code: 1
    flags: linked

  idempotency_key: payment.id
```

### Governance

```dsl
policies:
  classify Customer.email as PII_DIRECT
  classify Order.total as FINANCIAL_TXN
  erasure Customer: anonymize

tenancy:
  mode: shared_schema
```

### LLM

```dsl
llm_model gpt4 "GPT-4":
  tier: premium
  model_id: "gpt-4-turbo"
  max_tokens: 4096

llm_config:
  default_model: gpt4
  artifact_store: ".dazzle/llm_artifacts"
  logging:
    log_prompts: true
    log_completions: true
    redact_pii: true

llm_intent classify_ticket "Classify Support Ticket":
  model: gpt4
  prompt: "Classify the following support ticket..."
  input:
    ticket_text: text required
  output_schema:
    category: enum[bug, feature, question]
    confidence: decimal(3,2)
  timeout: 30000
  retry:
    max_attempts: 3
    backoff: exponential
```

### v0.25.0 Constructs

```dsl
enum OrderStatus "Order Status":
  draft "Draft"
  pending_review "Pending Review"
  approved "Approved"
  rejected "Rejected"

view MonthlySales "Monthly Sales Summary":
  source: Order
  filter: status = completed
  group_by: [customer, month(created_at)]
  fields:
    total_amount: sum(amount)
    order_count: count()

webhook OrderNotification "Order Status Webhook":
  entity: Order
  events: [created, updated, deleted]
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

approval PurchaseApproval "Purchase Order Approval":
  entity: PurchaseOrder
  trigger: status -> pending_approval
  approver_role: finance_manager
  quorum: 1
  threshold: amount > 1000
  escalation:
    after: 48 hours
    to: finance_director
  auto_approve:
    when: amount <= 100
  outcomes:
    approved -> approved
    rejected -> rejected

sla TicketResponse "Ticket Response SLA":
  entity: SupportTicket
  starts_when: status -> open
  pauses_when: status = on_hold
  completes_when: status -> resolved
  tiers:
    warning: 4 hours
    breach: 8 hours
    critical: 24 hours
  business_hours:
    schedule: "Mon-Fri 09:00-17:00"
    timezone: "Europe/London"
  on_breach:
    notify: support_lead
    set: escalated = true
```

## Parser Mixin Coverage

The grammar above is derived from these parser mixin modules:

| Module | Class | Category |
|--------|-------|----------|
| `base.py` | `BaseParser` | Core |
| `types.py` | `TypeParserMixin` | Core |
| `conditions.py` | `ConditionParserMixin` | Core |
| `entity.py` | `EntityParserMixin` | Core |
| `enum.py` | `EnumParserMixin` | Core |
| `surface.py` | `SurfaceParserMixin` | Surface |
| `ux.py` | `UXParserMixin` | Surface |
| `workspace.py` | `WorkspaceParserMixin` | Surface |
| `view.py` | `ViewParserMixin` | Surface |
| `service.py` | `ServiceParserMixin` | Integration |
| `integration.py` | `IntegrationParserMixin` | Integration |
| `webhook.py` | `WebhookParserMixin` | Integration |
| `flow.py` | `FlowParserMixin` | Testing |
| `test.py` | `TestParserMixin` | Testing |
| `scenario.py` | `ScenarioParserMixin` | Testing |
| `story.py` | `StoryParserMixin` | Workflow |
| `process.py` | `ProcessParserMixin` | Workflow |
| `approval.py` | `ApprovalParserMixin` | Workflow |
| `sla.py` | `SLAParserMixin` | Workflow |
| `messaging.py` | `MessagingParserMixin` | Eventing |
| `eventing.py` | `EventingParserMixin` | Eventing |
| `hless.py` | `HLESSParserMixin` | Eventing |
| `ledger.py` | `LedgerParserMixin` | Financial |
| `governance.py` | `GovernanceParserMixin` | Governance |
| `llm.py` | `LLMParserMixin` | LLM |
