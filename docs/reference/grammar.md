# DSL Grammar Specification

Formal EBNF grammar for DAZZLE DSL v0.24.

## Overview

This grammar defines the complete syntax for the DAZZLE Domain-Specific Language. It extends the base DSL with:

- State machines (`transitions` block) for entity lifecycle
- Computed fields with aggregate expressions
- Entity invariants for data integrity rules
- Access rules (inline read/write permissions)
- Intent declarations for semantic documentation
- Domain and patterns tags for LLM guidance
- Archetypes with `extends` inheritance
- Relationship semantics (`has_many`, `has_one`, `embeds`, `belongs_to`)
- TigerBeetle ledgers and transactions for double-entry accounting (v0.24)

## Anti-Turing Enforcement

DAZZLE intentionally limits computational expressiveness to ensure:

- Aggregate functions only in computed expressions
- `AGGREGATE_FN` explicitly enumerates allowed functions
- Turing-complete logic lives in service stubs (not DSL)

## Full Grammar

```ebnf
(*
  DAZZLE DSL 0.7 – Informal EBNF Grammar
  --------------------------------------
  This grammar extends DAZZLE 0.2 with business logic extraction features
  and LLM cognition enhancements for better semantic understanding.

  Changes from v0.2/v0.5:
  - State machines (transitions block) for entity lifecycle
  - Computed fields with aggregate expressions
  - Entity invariants for data integrity rules
  - Access rules (inline read/write permissions)
  - Intent declarations for semantic documentation
  - Domain and patterns tags for LLM guidance
  - Archetypes with extends inheritance
  - Example data blocks
  - Relationship semantics (has_many, has_one, embeds, belongs_to)
  - Delete behaviors (cascade, restrict, nullify, readonly)
  - Invariant messages and error codes

  Anti-Turing Enforcement (from v0.5.0):
  - Aggregate functions only in computed expressions
  - AGGREGATE_FN explicitly enumerates allowed functions
  - Turing-complete logic lives in service stubs
*)

dazzle_spec   ::= module_decl? app_decl statement* EOF ;

statement     ::= entity_decl
                | archetype_decl         (* NEW in v0.7.1 *)
                | surface_decl
                | workspace_decl
                | experience_decl
                | service_decl
                | domain_service_decl    (* NEW in v0.5.0 *)
                | foreign_model_decl
                | integration_decl
                | flow_decl              (* NEW in v0.3.2 - E2E testing *)
                | ledger_decl            (* NEW in v0.24.0 - TigerBeetle *)
                | transaction_decl       (* NEW in v0.24.0 - TigerBeetle *)
                | use_decl
                | comment ;

comment       ::= "#" /[^\n]*/ "\n" ;

(* =============================================================================
   Identifiers and Literals
   ============================================================================= *)

IDENT         ::= /[A-Za-z_][A-Za-z0-9_]*/ ;
STRING        ::= '"' (/[^\"]*/)? '"' ;
NUMBER        ::= /[0-9]+(\.[0-9]+)?/ ;
BOOLEAN       ::= "true" | "false" ;

APP_NAME      ::= IDENT ;
ENTITY_NAME   ::= IDENT ;
SURFACE_NAME  ::= IDENT ;
WORKSPACE_NAME ::= IDENT ;
EXPERIENCE_NAME ::= IDENT ;
SERVICE_NAME  ::= IDENT ;
FOREIGN_NAME  ::= IDENT ;
INTEGRATION_NAME ::= IDENT ;
FIELD_NAME    ::= IDENT ;
SECTION_NAME  ::= IDENT ;
STEP_NAME     ::= IDENT ;
PERSONA_NAME  ::= IDENT ;
ARCHETYPE_NAME ::= IDENT ;              (* NEW in v0.7.1 *)
STATE_NAME    ::= IDENT ;               (* NEW in v0.7.0 *)

MODULE_NAME   ::= IDENT ("." IDENT)* ;

(* =============================================================================
   Top-level Declarations
   ============================================================================= *)

module_decl   ::= "module" MODULE_NAME NEWLINE ;

app_decl      ::= "app" APP_NAME STRING? NEWLINE ;

use_decl      ::= "use" MODULE_NAME ("as" IDENT)? NEWLINE ;

NEWLINE       ::= /[\r\n]+/ ;
INDENT        ::= /* implementation-dependent indentation token */ ;
DEDENT        ::= /* implementation-dependent indentation token */ ;

(* =============================================================================
   Archetype Definitions (NEW in v0.7.1)
   ============================================================================= *)

archetype_decl ::= "archetype" ARCHETYPE_NAME STRING? ":" NEWLINE
                   INDENT
                     field_line+
                   DEDENT ;

(* =============================================================================
   Entity Definitions (Extended in v0.7.x)
   ============================================================================= *)

entity_decl   ::= "entity" ENTITY_NAME STRING? ":" NEWLINE
                  INDENT
                    entity_metadata*        (* NEW: intent, domain, patterns, extends *)
                    field_line+
                    constraint_line*
                    transitions_block?      (* NEW in v0.7.0 *)
                    invariant_block*        (* NEW in v0.7.0 *)
                    access_block?           (* NEW in v0.5.0 *)
                    examples_block?         (* NEW in v0.7.1 *)
                  DEDENT ;

(* Entity metadata for LLM cognition *)
entity_metadata ::= intent_line
                  | domain_line
                  | patterns_line
                  | extends_line ;

intent_line   ::= "intent" ":" STRING NEWLINE ;

domain_line   ::= "domain" ":" IDENT NEWLINE ;

patterns_line ::= "patterns" ":" IDENT ("," IDENT)* NEWLINE ;

extends_line  ::= "extends" ":" ARCHETYPE_NAME ("," ARCHETYPE_NAME)* NEWLINE ;

(* Field definitions *)
field_line    ::= FIELD_NAME ":" field_def NEWLINE ;

field_def     ::= type_spec field_modifier*     (* Regular field *)
                | "computed" computed_expr ;     (* Computed field *)

(* Computed field expressions - restricted to aggregate functions *)
computed_expr ::= aggregate_call
                | field_path
                | computed_expr ("+" | "-" | "*" | "/") computed_expr
                | "(" computed_expr ")" ;

field_path    ::= FIELD_NAME ("." FIELD_NAME)* ;

type_spec     ::= scalar_type
                | enum_type
                | reference_type ;

scalar_type   ::= "str" "(" NUMBER ")"
                | "text"
                | "int"
                | "decimal" "(" NUMBER "," NUMBER ")"
                | "bool"
                | "date"
                | "datetime"
                | "uuid"
                | "json"
                | "email" ;

enum_type     ::= "enum" "[" IDENT ("," IDENT)* "]" ;

(* Reference types with relationship semantics (Extended in v0.7.1) *)
reference_type ::= "ref" ENTITY_NAME delete_behavior?
                 | "has_many" ENTITY_NAME delete_behavior?
                 | "has_one" ENTITY_NAME delete_behavior?
                 | "belongs_to" ENTITY_NAME delete_behavior?
                 | "embeds" ENTITY_NAME ;

delete_behavior ::= "cascade" | "restrict" | "nullify" | "readonly" ;

field_modifier ::= "required"
                 | "optional"
                 | "pk"
                 | "unique"
                 | "unique?"
                 | "auto_add"
                 | "auto_update"
                 | "default" "=" literal ;

literal       ::= STRING | NUMBER | BOOLEAN ;

constraint_line ::= ("unique" | "index") FIELD_NAME ("," FIELD_NAME)* NEWLINE ;

(* =============================================================================
   State Machines (NEW in v0.7.0)
   ============================================================================= *)

transitions_block ::= "transitions" ":" NEWLINE
                      INDENT
                        transition_rule+
                      DEDENT ;

transition_rule ::= from_state "->" to_state transition_spec? NEWLINE ;

from_state    ::= STATE_NAME | "*" ;        (* "*" means any state *)

to_state      ::= STATE_NAME ;

transition_spec ::= ":" transition_constraint+ ;

transition_constraint ::= "requires" FIELD_NAME
                        | "role" "(" IDENT ("," IDENT)* ")"
                        | "auto" "after" NUMBER time_unit
                        | "manual" ;

time_unit     ::= "minutes" | "hours" | "days" ;

(* =============================================================================
   Invariants (NEW in v0.7.0)
   ============================================================================= *)

invariant_block ::= "invariant" ":" invariant_expr invariant_metadata? NEWLINE ;

invariant_expr ::= comparison
                 | comparison ("and" | "or") invariant_expr
                 | "(" invariant_expr ")" ;

invariant_metadata ::= NEWLINE INDENT
                         ("message" ":" STRING NEWLINE)?
                         ("code" ":" IDENT NEWLINE)?
                       DEDENT ;

(* =============================================================================
   Access Rules (NEW in v0.5.0)
   ============================================================================= *)

access_block  ::= "access" ":" NEWLINE
                  INDENT
                    access_rule+
                  DEDENT ;

access_rule   ::= ("read" | "write") ":" access_expr NEWLINE ;

access_expr   ::= access_term (("or" | "and") access_term)*
                | "(" access_expr ")" ;

access_term   ::= comparison
                | "role" "(" IDENT ("," IDENT)* ")"
                | "owner"
                | "tenant" ;

(* =============================================================================
   Example Data (NEW in v0.7.1)
   ============================================================================= *)

examples_block ::= "examples" ":" NEWLINE
                   INDENT
                     example_entry+
                   DEDENT ;

example_entry ::= "-" json_object NEWLINE ;

json_object   ::= "{" (json_pair ("," json_pair)*)? "}" ;

json_pair     ::= (IDENT | STRING) ":" json_value ;

json_value    ::= STRING | NUMBER | BOOLEAN | json_object | json_array ;

json_array    ::= "[" (json_value ("," json_value)*)? "]" ;

(* =============================================================================
   Domain Services (NEW in v0.5.0)
   ============================================================================= *)

domain_service_decl ::= "service" SERVICE_NAME STRING? ":" NEWLINE
                        INDENT
                          "kind" ":" service_kind NEWLINE
                          service_input_block?
                          service_output_block?
                          service_guarantees_block?
                          ("stub" ":" stub_language NEWLINE)?
                        DEDENT ;

service_kind  ::= "domain_logic" | "validation" | "integration" | "workflow" ;

service_input_block ::= "input" ":" NEWLINE
                        INDENT
                          service_field_line+
                        DEDENT ;

service_output_block ::= "output" ":" NEWLINE
                         INDENT
                           service_field_line+
                         DEDENT ;

service_field_line ::= FIELD_NAME ":" type_spec field_modifier* NEWLINE ;

service_guarantees_block ::= "guarantees" ":" NEWLINE
                             INDENT
                               guarantee_line+
                             DEDENT ;

guarantee_line ::= "-" STRING NEWLINE ;

stub_language ::= "python" | "typescript" ;

(* =============================================================================
   Surfaces (Extended with UX block)
   ============================================================================= *)

surface_decl  ::= "surface" SURFACE_NAME STRING? ":" NEWLINE
                  INDENT
                    surface_body_line+
                    ux_block?
                  DEDENT ;

surface_body_line
              ::= uses_entity_line
                | mode_line
                | priority_line
                | section_decl
                | surface_action_decl ;

uses_entity_line
              ::= "uses" "entity" ENTITY_NAME NEWLINE ;

mode_line     ::= "mode" ":" ("view" | "create" | "edit" | "list" | "custom") NEWLINE ;

priority_line ::= "priority" ":" ("critical" | "high" | "medium" | "low") NEWLINE ;

section_decl  ::= "section" SECTION_NAME STRING? ":" NEWLINE
                  INDENT
                    surface_element_line+
                  DEDENT ;

surface_element_line
              ::= "field" FIELD_NAME STRING? surface_element_option* NEWLINE ;

surface_element_option
              ::= IDENT "=" literal ;
              (* e.g. source=companies_house_lookup.search_companies
                 Binds the field to an API pack search operation,
                 rendering it as a search_select widget. *)

surface_action_decl
              ::= "action" IDENT STRING? ":" NEWLINE
                  INDENT
                    "on" surface_trigger "->" outcome NEWLINE
                  DEDENT ;

surface_trigger
              ::= "submit" | "click" | "auto" ;

outcome       ::= "surface" SURFACE_NAME
                | "experience" EXPERIENCE_NAME ("step" STEP_NAME)?
                | "integration" INTEGRATION_NAME "action" IDENT ;

(* =============================================================================
   UX Semantic Layer
   ============================================================================= *)

ux_block      ::= "ux" ":" NEWLINE
                  INDENT
                    ux_directive+
                  DEDENT ;

ux_directive  ::= purpose_line
                | show_line
                | sort_line
                | filter_line
                | search_line
                | empty_line
                | attention_block
                | persona_block ;

purpose_line  ::= "purpose" ":" STRING NEWLINE ;

show_line     ::= "show" ":" field_list NEWLINE ;

sort_line     ::= "sort" ":" sort_expr ("," sort_expr)* NEWLINE ;

filter_line   ::= "filter" ":" field_list NEWLINE ;

search_line   ::= "search" ":" field_list NEWLINE ;

empty_line    ::= "empty" ":" STRING NEWLINE ;

field_list    ::= FIELD_NAME ("," FIELD_NAME)* ;

sort_expr     ::= FIELD_NAME ("asc" | "desc")? ;

(* Attention Signals *)

attention_block ::= "attention" signal_level ":" NEWLINE
                    INDENT
                      "when" ":" condition_expr NEWLINE
                      "message" ":" STRING NEWLINE
                      ("action" ":" SURFACE_NAME NEWLINE)?
                    DEDENT ;

signal_level  ::= "critical" | "warning" | "notice" | "info" ;

condition_expr ::= comparison
                 | comparison ("and" | "or") condition_expr
                 | "(" condition_expr ")" ;

comparison    ::= FIELD_NAME operator value
                | aggregate_call operator value ;

operator      ::= "=" | "!=" | ">" | "<" | ">=" | "<="
                | "in" | "not" "in" | "is" | "is" "not" ;

(* Aggregate functions - restricted set for Anti-Turing compliance *)
aggregate_call ::= AGGREGATE_FN "(" FIELD_NAME ")" ;

AGGREGATE_FN  ::= "count" | "sum" | "avg" | "max" | "min"
                | "days_until" | "days_since" ;

value         ::= STRING | NUMBER | IDENT | value_list ;

value_list    ::= "[" value ("," value)* "]" ;

(* Persona Variants *)

persona_block ::= "for" PERSONA_NAME ":" NEWLINE
                  INDENT
                    persona_directive+
                  DEDENT ;

persona_directive ::= "scope" ":" scope_expr NEWLINE
                    | "purpose" ":" STRING NEWLINE
                    | "show" ":" field_list NEWLINE
                    | "hide" ":" field_list NEWLINE
                    | "show_aggregate" ":" IDENT ("," IDENT)* NEWLINE
                    | "action_primary" ":" SURFACE_NAME NEWLINE
                    | "read_only" ":" BOOLEAN NEWLINE ;

scope_expr    ::= "all"
                | comparison
                | comparison ("and" | "or") scope_expr ;

(* =============================================================================
   Workspace Construct
   ============================================================================= *)

workspace_decl ::= "workspace" WORKSPACE_NAME STRING? ":" NEWLINE
                   INDENT
                     purpose_line?
                     workspace_region+
                     ux_block?
                   DEDENT ;

workspace_region ::= IDENT ":" NEWLINE
                     INDENT
                       region_directive+
                     DEDENT ;

region_directive ::= "source" ":" (ENTITY_NAME | SURFACE_NAME) NEWLINE
                   | "filter" ":" filter_expr NEWLINE
                   | "sort" ":" sort_expr ("," sort_expr)* NEWLINE
                   | "limit" ":" NUMBER NEWLINE
                   | "display" ":" display_mode NEWLINE
                   | "action" ":" SURFACE_NAME NEWLINE
                   | "empty" ":" STRING NEWLINE
                   | "aggregate" ":" aggregate_block ;

display_mode  ::= "list" | "grid" | "timeline" | "map" ;

aggregate_block ::= NEWLINE INDENT metric_line+ DEDENT ;

metric_line   ::= IDENT ":" aggregate_expr NEWLINE ;

aggregate_expr ::= aggregate_call
                 | arithmetic_expr
                 | NUMBER ;

arithmetic_expr ::= aggregate_expr ("+" | "-" | "*" | "/") aggregate_expr
                  | "(" aggregate_expr ")" ;

filter_expr   ::= "all"
                | comparison
                | comparison ("and" | "or") filter_expr ;

(* =============================================================================
   Experiences
   ============================================================================= *)

experience_decl
              ::= "experience" EXPERIENCE_NAME STRING? ":" NEWLINE
                  INDENT
                    access_line?
                    priority_line?
                    "start" "at" "step" STEP_NAME NEWLINE
                    experience_step_decl+
                  DEDENT ;

experience_step_decl
              ::= "step" STEP_NAME ":" NEWLINE
                  INDENT
                    "kind" ":" ("surface" | "process" | "integration") NEWLINE
                    step_kind_body
                    step_transition_line*
                  DEDENT ;

step_kind_body
              ::= "surface" SURFACE_NAME NEWLINE
                | "integration" INTEGRATION_NAME "action" IDENT NEWLINE
                | /* process variant reserved for future */ ;

step_transition_line
              ::= "on" ("success" | "failure") "->" "step" STEP_NAME NEWLINE ;

(* =============================================================================
   Legacy Services (for external API integration)
   ============================================================================= *)

service_decl  ::= "service" SERVICE_NAME STRING? ":" NEWLINE
                  INDENT
                    service_body_line+
                  DEDENT ;

service_body_line
              ::= spec_line
                | auth_profile_line
                | owner_line ;

spec_line     ::= "spec" ":" ("url" STRING | "inline" STRING) NEWLINE ;

auth_profile_line
              ::= "auth_profile" ":" AUTH_KIND auth_option* NEWLINE ;

AUTH_KIND     ::= "oauth2_legacy" | "oauth2_pkce" | "jwt_static"
                | "api_key_header" | "api_key_query" | "none" ;

auth_option   ::= IDENT "=" literal ;

owner_line    ::= "owner" ":" STRING NEWLINE ;

(* =============================================================================
   Foreign Models
   ============================================================================= *)

foreign_model_decl
              ::= "foreign_model" FOREIGN_NAME "from" SERVICE_NAME STRING? ":" NEWLINE
                  INDENT
                    foreign_model_line+
                  DEDENT ;

foreign_model_line
              ::= key_line
                | foreign_constraint_line
                | foreign_field_line ;

key_line      ::= "key" ":" FIELD_NAME ("," FIELD_NAME)* NEWLINE ;

foreign_constraint_line
              ::= "constraint" FOREIGN_CONSTRAINT foreign_constraint_option* NEWLINE ;

FOREIGN_CONSTRAINT
              ::= "read_only" | "event_driven" | "batch_import" ;

foreign_constraint_option
              ::= IDENT "=" literal ;

foreign_field_line
              ::= "field" FIELD_NAME ":" type_spec field_modifier* NEWLINE ;

(* =============================================================================
   Integrations
   ============================================================================= *)

integration_decl
              ::= "integration" INTEGRATION_NAME STRING? ":" NEWLINE
                  INDENT
                    integration_body_line+
                  DEDENT ;

integration_body_line
              ::= uses_service_line
                | uses_foreign_model_line
                | integration_action_decl
                | sync_decl ;

uses_service_line
              ::= "uses" "service" SERVICE_NAME ("," SERVICE_NAME)* NEWLINE ;

uses_foreign_model_line
              ::= "uses" "foreign_model" FOREIGN_NAME ("," FOREIGN_NAME)* NEWLINE ;

integration_action_decl
              ::= "action" IDENT ":" NEWLINE
                  INDENT
                    action_when_line
                    action_call_line
                    action_map_line?
                  DEDENT ;

action_when_line
              ::= "when" "surface" SURFACE_NAME "submitted" NEWLINE ;

action_call_line
              ::= "call" SERVICE_NAME "." IDENT "with" ":" NEWLINE
                  INDENT
                    mapping_rule_line+
                  DEDENT ;

action_map_line
              ::= "map" "response" FOREIGN_NAME "->" "entity" ENTITY_NAME ":" NEWLINE
                  INDENT
                    mapping_rule_line+
                  DEDENT ;

mapping_rule_line
              ::= FIELD_NAME "<-" expression NEWLINE ;

expression    ::= PATH | literal ;

PATH          ::= /[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*/ ;

sync_decl     ::= "sync" IDENT ":" NEWLINE
                  INDENT
                    sync_mode_line
                    sync_schedule_line?
                    sync_from_line
                    sync_into_line
                    sync_match_line?
                  DEDENT ;

sync_mode_line
              ::= "mode" ":" ("scheduled" | "event_driven") NEWLINE ;

sync_schedule_line
              ::= "schedule" ":" STRING NEWLINE ;

sync_from_line
              ::= "from" SERVICE_NAME "." IDENT "as" FOREIGN_NAME NEWLINE ;

sync_into_line
              ::= "into" "entity" ENTITY_NAME NEWLINE ;

sync_match_line
              ::= "match" "on" ":" NEWLINE
                  INDENT
                    sync_match_rule_line+
                  DEDENT ;

sync_match_rule_line
              ::= FIELD_NAME "<->" FIELD_NAME NEWLINE ;

(* =============================================================================
   E2E Test Flows (NEW in v0.3.2)
   ============================================================================= *)

flow_decl     ::= "flow" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("priority" ":" flow_priority NEWLINE)?
                    flow_step+
                  DEDENT ;

flow_priority ::= "critical" | "high" | "medium" | "low" ;

flow_step     ::= step_action target assertion* NEWLINE ;

step_action   ::= "navigate" | "fill" | "click" | "wait" | "assert" | "snapshot" ;

target        ::= "view" ":" SURFACE_NAME
                | "field" ":" ENTITY_NAME "." FIELD_NAME
                | "action" ":" ENTITY_NAME "." IDENT
                | "element" ":" STRING ;

assertion     ::= "expect" assertion_check ;

assertion_check ::= "visible" | "hidden" | "enabled" | "disabled"
                  | "text" "=" STRING
                  | "value" "=" literal
                  | "count" "=" NUMBER ;

(* =============================================================================
   TigerBeetle Ledgers (NEW in v0.24.0)
   ============================================================================= *)

ledger_decl   ::= "ledger" LEDGER_NAME STRING? ":" NEWLINE
                  INDENT
                    ledger_body_line+
                  DEDENT ;

LEDGER_NAME   ::= IDENT ;

ledger_body_line
              ::= intent_line
                | account_code_line
                | ledger_id_line
                | account_type_line
                | currency_line
                | flags_line
                | sync_to_line
                | tenant_scoped_line
                | metadata_mapping_block ;

account_code_line
              ::= "account_code" ":" NUMBER NEWLINE ;

ledger_id_line
              ::= "ledger_id" ":" NUMBER NEWLINE ;

account_type_line
              ::= "account_type" ":" ACCOUNT_TYPE NEWLINE ;

ACCOUNT_TYPE  ::= "asset" | "liability" | "equity" | "revenue" | "expense" ;

currency_line ::= "currency" ":" CURRENCY_CODE NEWLINE ;

CURRENCY_CODE ::= /[A-Z]{3}/ ;       (* ISO 4217 currency code *)

flags_line    ::= "flags" ":" ACCOUNT_FLAG ("," ACCOUNT_FLAG)* NEWLINE ;

ACCOUNT_FLAG  ::= "debits_must_not_exceed_credits"
                | "credits_must_not_exceed_debits"
                | "linked"
                | "history" ;

sync_to_line  ::= "sync_to" ":" ENTITY_NAME "." FIELD_NAME
                  ("trigger" ":" SYNC_TRIGGER)? NEWLINE ;

SYNC_TRIGGER  ::= "after_transfer" | "scheduled" STRING | "on_demand" ;

tenant_scoped_line
              ::= "tenant_scoped" ":" BOOLEAN NEWLINE ;

metadata_mapping_block
              ::= "metadata_mapping" ":" NEWLINE
                  INDENT
                    metadata_mapping_line+
                  DEDENT ;

metadata_mapping_line
              ::= IDENT ":" ("ref" ENTITY_NAME "." FIELD_NAME | STRING) NEWLINE ;

(* =============================================================================
   TigerBeetle Transactions (NEW in v0.24.0)
   ============================================================================= *)

transaction_decl
              ::= "transaction" TRANSACTION_NAME STRING? ":" NEWLINE
                  INDENT
                    transaction_body_line+
                  DEDENT ;

TRANSACTION_NAME ::= IDENT ;

transaction_body_line
              ::= intent_line
                | execution_line
                | priority_line
                | timeout_line
                | transfer_block
                | idempotency_key_line
                | validation_block ;

execution_line
              ::= "execution" ":" EXECUTION_MODE NEWLINE ;

EXECUTION_MODE ::= "sync" | "async" ;

priority_line ::= "priority" ":" PRIORITY_LEVEL NEWLINE ;

PRIORITY_LEVEL ::= "critical" | "high" | "normal" | "low" ;

timeout_line  ::= "timeout" ":" NUMBER NEWLINE ;     (* milliseconds *)

transfer_block
              ::= "transfer" TRANSFER_NAME ":" NEWLINE
                  INDENT
                    transfer_line+
                  DEDENT ;

TRANSFER_NAME ::= IDENT ;

transfer_line ::= debit_line
                | credit_line
                | amount_line
                | code_line
                | transfer_flags_line
                | pending_id_line
                | user_data_block ;

debit_line    ::= "debit" ":" LEDGER_NAME NEWLINE ;

credit_line   ::= "credit" ":" LEDGER_NAME NEWLINE ;

amount_line   ::= "amount" ":" amount_expr NEWLINE ;

amount_expr   ::= amount_term (("+" | "-" | "*" | "/") amount_term)? ;

amount_term   ::= NUMBER
                | field_path ;

code_line     ::= "code" ":" NUMBER NEWLINE ;

transfer_flags_line
              ::= "flags" ":" TRANSFER_FLAG ("," TRANSFER_FLAG)* NEWLINE ;

TRANSFER_FLAG ::= "linked" | "pending" | "post_pending" | "void_pending" | "balancing" ;

pending_id_line
              ::= "pending_id" ":" STRING NEWLINE ;

user_data_block
              ::= "user_data" ":" NEWLINE
                  INDENT
                    user_data_line+
                  DEDENT ;

user_data_line
              ::= IDENT ":" (STRING | IDENT) NEWLINE ;

idempotency_key_line
              ::= "idempotency_key" ":" expression NEWLINE ;

validation_block
              ::= "validation" ":" NEWLINE
                  INDENT
                    validation_rule_line+
                  DEDENT ;

validation_rule_line
              ::= "-" expression NEWLINE ;
```
