"""
Grammar documentation generator for the DAZZLE DSL.

Introspects the parser source code (mixin docstrings, lexer keywords,
IR field types) to produce an authoritative EBNF grammar specification.

Usage:
    python -m dazzle.core.grammar_gen           # print to stdout
    dazzle grammar                              # write docs/reference/grammar.md
"""

import importlib
import inspect
import re
from pathlib import Path

from dazzle.core.ir.fields import FieldTypeKind

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PARSER_IMPL_DIR = Path(__file__).parent / "dsl_parser_impl"

# Ordered list of parser mixin modules and their section metadata.
# (module_name, section_title, category)
_MIXIN_SECTIONS: list[tuple[str, str, str]] = [
    ("base", "Top-level Declarations", "Core"),
    ("types", "Field Types and Modifiers", "Core"),
    ("conditions", "Condition Expressions", "Core"),
    ("entity", "Entity and Archetype Definitions", "Core"),
    ("surface", "Surface Definitions", "Surface"),
    ("ux", "UX Semantic Layer", "Surface"),
    ("workspace", "Workspace Definitions", "Surface"),
    ("service", "Service Definitions", "Integration"),
    ("integration", "Integration Definitions", "Integration"),
    ("scenario", "Scenario and Demo Data", "Testing"),
    ("story", "Story Definitions", "Workflow"),
    ("process", "Process Workflows", "Workflow"),
    ("governance", "Governance Sections", "Governance"),
    ("llm", "LLM Jobs", "LLM"),
]

# Categories in presentation order.
_CATEGORY_ORDER = (
    "Core",
    "Surface",
    "Workflow",
    "Integration",
    "Testing",
    "Governance",
    "LLM",
)


# ---------------------------------------------------------------------------
# Helpers — introspection
# ---------------------------------------------------------------------------


def get_version() -> str:
    """Read version from pyproject.toml."""
    import tomllib

    toml_path = Path(__file__).resolve().parents[3] / "pyproject.toml"
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    return str(data["project"]["version"])


def _load_mixin_module(name: str) -> object:
    """Import a parser mixin module by short name."""
    return importlib.import_module(f"dazzle.core.dsl_parser_impl.{name}")


def get_mixin_class_names() -> dict[str, str]:
    """Return mapping of module name -> class name for every mixin."""
    result: dict[str, str] = {}
    for mod_name, _, _ in _MIXIN_SECTIONS:
        mod = _load_mixin_module(mod_name)
        for name, _obj in inspect.getmembers(mod, inspect.isclass):
            if name.endswith("Mixin") or name == "BaseParser":
                result[mod_name] = name
                break
    return result


# ---------------------------------------------------------------------------
# Helpers — keyword inventory
# ---------------------------------------------------------------------------


def get_keyword_groups() -> dict[str, list[str]]:
    """
    Extract keywords from TokenType, grouped by version/feature comment blocks.

    Returns a dict of group_label -> list[keyword_value].
    """
    source_path = Path(__file__).parent / "lexer.py"
    source = source_path.read_text(encoding="utf-8")

    groups: dict[str, list[str]] = {}
    current_group = "Core Keywords"
    # Pattern for comment headers like "# v0.7.0 State Machine Keywords"
    header_re = re.compile(r"^\s*#\s*(.+?)\s*$")
    # Pattern for enum member assignment like ENTITY = "entity"
    member_re = re.compile(r'^\s+([A-Z_]+)\s*=\s*"([^"]+)"')

    in_enum = False
    for line in source.splitlines():
        if "class TokenType" in line:
            in_enum = True
            continue
        if in_enum and line.strip() and not line.startswith(" ") and not line.startswith("\t"):
            if not line.strip().startswith("#") and not line.strip().startswith("class"):
                break

        if not in_enum:
            continue

        header_match = header_re.match(line)
        if header_match:
            label = header_match.group(1).strip()
            # Only treat as a group header if it's a proper section
            # header.  Lexer headers follow patterns like:
            #   "# Keywords"
            #   "# Integration Keywords"
            #   "# v0.7.0 State Machine Keywords"
            #   "# Literals"
            # Skip inline notes and explanatory comments.
            if label.startswith("Note:") or label.startswith("Words "):
                continue
            is_section = bool(
                re.search(r"[Kk]eywords(\s*\(.*\))?\s*$", label)
                or re.search(r"[Ll]iterals\s*$", label)
            )
            if not is_section:
                continue
            current_group = label
            continue

        member_match = member_re.match(line)
        if member_match:
            _member_name = member_match.group(1)
            value = member_match.group(2)
            # Skip non-keyword tokens (operators, special tokens, all-caps values)
            if value in (
                "IDENTIFIER",
                "STRING",
                "NUMBER",
                "DURATION_LITERAL",
                "NEWLINE",
                "INDENT",
                "DEDENT",
                "EOF",
            ):
                continue
            if value in (
                "==",
                "!=",
                ">",
                "<",
                ">=",
                "<=",
                ":",
                "->",
                "<-",
                "<->",
                ",",
                "(",
                ")",
                "[",
                "]",
                "=",
                ".",
                "/",
                "?",
                "+",
                "-",
                "*",
                "%",
            ):
                continue
            # Skip all-caps non-keyword values (FACT, OBSERVATION, etc. are valid keywords)
            groups.setdefault(current_group, []).append(value)

    return groups


# ---------------------------------------------------------------------------
# Helpers — type_spec production rule
# ---------------------------------------------------------------------------


def build_type_spec_rule() -> str:
    """Generate the type_spec EBNF production from FieldTypeKind enum."""
    scalar_types = []
    ref_types = []

    for kind in FieldTypeKind:
        if kind in (FieldTypeKind.ENUM, FieldTypeKind.REF):
            continue
        if kind in (
            FieldTypeKind.HAS_MANY,
            FieldTypeKind.HAS_ONE,
            FieldTypeKind.EMBEDS,
            FieldTypeKind.BELONGS_TO,
        ):
            ref_types.append(kind.value)
            continue
        scalar_types.append(kind.value)

    lines = [
        "type_spec     ::= scalar_type",
        "                | enum_type",
        "                | reference_type ;",
        "",
        "(* Scalar types — generated from FieldTypeKind enum *)",
    ]

    # Build scalar_type with parameterised types
    scalar_lines = []
    for st in scalar_types:
        if st == "str":
            scalar_lines.append('"str" "(" NUMBER ")"')
        elif st == "decimal":
            scalar_lines.append('"decimal" "(" NUMBER "," NUMBER ")"')
        elif st == "money":
            scalar_lines.append('"money" ( "(" CURRENCY_CODE ")" )?')
        else:
            scalar_lines.append(f'"{st}"')

    lines.append(f"scalar_type   ::= {scalar_lines[0]}")
    for sl in scalar_lines[1:]:
        lines.append(f"                | {sl}")
    lines[-1] += " ;"
    lines.append("")

    lines.append('enum_type     ::= "enum" "[" IDENT ("," IDENT)* "]" ;')
    lines.append("")

    # Reference types
    ref_lines = ['"ref" ENTITY_NAME delete_behavior?']
    for rt in ref_types:
        ref_lines.append(f'"{rt}" ENTITY_NAME delete_behavior?')
    lines.append(f"reference_type ::= {ref_lines[0]}")
    for rl in ref_lines[1:]:
        lines.append(f"                 | {rl}")
    lines[-1] += " ;"

    lines.append("")
    lines.append('delete_behavior ::= "cascade" | "restrict" | "nullify" | "readonly" ;')

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

_EBNF_HEADER = """\
(*
  DAZZLE DSL v{version} -- EBNF Grammar
  ======================================
  Auto-generated by grammar_gen.py from parser source code.
  Do not edit manually; run `dazzle grammar` to regenerate.

  Anti-Turing Enforcement:
  - Aggregate functions only in computed expressions
  - AGGREGATE_FN explicitly enumerates allowed functions
  - Turing-complete logic lives in service stubs (not DSL)
*)
"""

_IDENTIFIERS_SECTION = """\
(* =============================================================================
   Identifiers and Literals
   ============================================================================= *)

IDENT         ::= /[A-Za-z_][A-Za-z0-9_]*/ ;
STRING        ::= '"' /[^\\"]*/ '"' ;
NUMBER        ::= /[0-9]+(\\.[0-9]+)?/ ;
BOOLEAN       ::= "true" | "false" ;
NEWLINE       ::= /[\\r\\n]+/ ;
INDENT        ::= (* indentation increase *) ;
DEDENT        ::= (* indentation decrease *) ;
"""

_TOP_LEVEL_RULES = """\
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
                | persona_decl
                | scenario_decl
                | story_decl
                | process_decl
                | schedule_decl
                | policies_decl
                | tenancy_decl
                | llm_model_decl
                | llm_config_decl
                | llm_intent_decl
                | use_decl
                | comment ;

comment       ::= "#" /[^\\n]*/ NEWLINE ;
"""


def _section_separator(title: str) -> str:
    """Generate an EBNF section comment."""
    bar = "=" * 77
    return f"(* {bar}\n   {title}\n   {bar} *)\n"


def _build_entity_section() -> str:
    """Generate entity and archetype grammar rules."""
    return """\
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
                    scope_block?
                    audit_directive?
                    examples_block?
                    publish_directive*
                  DEDENT ;

entity_metadata ::= "intent" ":" STRING NEWLINE
                  | "domain" ":" IDENT NEWLINE
                  | "patterns" ":" IDENT ("," IDENT)* NEWLINE
                  | "extends" ":" IDENT ("," IDENT)* NEWLINE
                  | "subtype_of" ":" IDENT NEWLINE
                  | "archetype" ":" IDENT NEWLINE
                  | "legal_entity" NEWLINE ;

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

aggregate_call ::= AGGREGATE_FN "(" field_path ("where" condition_expr)? ("window" window_kind "on" IDENT)? ")" ;

window_kind   ::= "last_complete_day" | "week_from_monday" | "previous_week" ;
"""


def _build_state_machine_section() -> str:
    return """\
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
                | role_guard
                | "auto" "after" NUMBER time_unit ("or" "manual")?
                | "manual" ;

role_guard    ::= "role" "(" IDENT ("," IDENT)* ")" ("or" "role" "(" IDENT ")")* ;
                  (* one guard; the user must hold ANY listed role (#1797) *)

time_unit     ::= "minutes" | "hours" | "days" ;
"""


def _build_invariant_section() -> str:
    return """\
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
"""


def _build_access_section() -> str:
    return """\
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

scope_block   ::= "scope" ":" NEWLINE
                  INDENT
                    scope_rule+
                  DEDENT ;

scope_rule    ::= ("create" | "read" | "update" | "delete" | "list") ":" scope_filter NEWLINE
                  INDENT
                    "as" ":" ("*" | IDENT ("," IDENT)*) NEWLINE
                  DEDENT ;

scope_filter  ::= "all"
                | "via" IDENT "(" via_binding ("," via_binding)* ")"
                | "not" "via" IDENT "(" via_binding ("," via_binding)* ")"
                | condition_expr ;

via_binding   ::= IDENT "=" (IDENT ("." IDENT)* | "id") ;

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

value         ::= STRING | NUMBER | IDENT | date_expr | calendar_anchor
                | "[" value ("," value)* "]" ;

calendar_anchor
              ::= "start_of" "(" calendar_period ")" (("+" | "-") duration_expr)? ;

calendar_period
              ::= "week" | "month" | "quarter" | "year" ;

operator      ::= "=" | "!=" | ">" | "<" | ">=" | "<="
                | "in" | "not" "in" | "is" | "is" "not" ;
"""


def _build_examples_section() -> str:
    return """\
examples_block ::= "examples" ":" NEWLINE
                   INDENT
                     example_entry+
                   DEDENT ;

example_entry ::= "-" key_value_list NEWLINE ;

key_value_list ::= IDENT ":" literal ("," IDENT ":" literal)* ;
"""


def _build_surface_section() -> str:
    return """\
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
                    ("visible" ":" condition_expr NEWLINE)?
                    surface_element_line+
                  DEDENT ;

surface_element_line
              ::= "field" IDENT STRING? surface_element_option* NEWLINE ;

surface_element_option
              ::= IDENT "=" literal
                | "visible" ":" condition_expr
                | "when" ":" invariant_expr   (* typed expression, as in invariants *)
                | "help" ":" STRING
                | "format" ":" IDENT (":" IDENT)? ;

(* #1787: one "on" line (required) and an optional "visible:" line, either order. *)
surface_action_decl
              ::= "action" IDENT STRING? ":" NEWLINE
                  INDENT
                    surface_action_line+
                  DEDENT ;

surface_action_line
              ::= "on" surface_trigger "->" outcome NEWLINE
                | "visible" ":" condition_expr NEWLINE ;

surface_trigger
              ::= "submit" | "click" | "auto" ;

outcome       ::= STRING "external"
                | "surface" IDENT
                | "experience" IDENT ("step" IDENT)?
                | "integration" IDENT "action" IDENT ;
"""


def _build_ux_section() -> str:
    return """\
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

persona_block ::= "as" IDENT ":" NEWLINE
                  INDENT
                    persona_directive+
                  DEDENT ;

persona_directive
              ::= "scope" ":" scope_expr NEWLINE
                | "purpose" ":" STRING NEWLINE
                | "show" ":" field_list NEWLINE
                | "hide" ":" field_list NEWLINE
                | "action_primary" ":" IDENT NEWLINE
                | "read_only" ":" BOOLEAN NEWLINE
                | "focus" ":" field_list NEWLINE
                | "empty" ":" STRING NEWLINE
                | defaults_block ;

defaults_block
              ::= "defaults" ":" NEWLINE
                  INDENT
                    (IDENT ":" (STRING | IDENT ("." IDENT)*) NEWLINE)+
                  DEDENT ;

scope_expr    ::= "all" | comparison (("and" | "or") comparison)* ;
"""


def _build_workspace_section() -> str:
    return """\
workspace_decl ::= "workspace" IDENT STRING? ":" NEWLINE
                   INDENT
                     ("purpose" ":" STRING NEWLINE)?
                     ("access" ":" IDENT NEWLINE)?
                     ("live" ":" IDENT NEWLINE)?  (* parked in DD-006: W_DECLARED_NOT_READ *)
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

metric_line   ::= IDENT ":" (aggregate_call | derived_metric_expr) NEWLINE ;

derived_metric_expr
              ::= derived_term (("+" | "-" | "*" | "/") derived_term)* ;

derived_term  ::= IDENT                          (* metric declared earlier in the block *)
                | NUMBER
                | ("round" | "abs" | "nullif" | "coalesce") "(" derived_metric_expr ("," derived_metric_expr)* ")"
                | "(" derived_metric_expr ")" ;

filter_expr   ::= "all" | comparison (("and" | "or") comparison)* ;
"""


def _build_experience_section() -> str:
    return """\
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
"""


def _build_service_section() -> str:
    return """\
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
                    ("stub" ":" ("python" | "typescript") NEWLINE)?  (* accepted, not read: W_DECLARED_NOT_READ *)
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
"""


def _build_foreign_model_section() -> str:
    return """\
foreign_model_decl
              ::= "foreign_model" IDENT "from" IDENT STRING? ":" NEWLINE
                  INDENT
                    foreign_model_line+
                  DEDENT ;

foreign_model_line
              ::= "key" ":" IDENT ("," IDENT)* NEWLINE
                | "constraint" ("read_only" | "event_driven" | "batch_import") (IDENT "=" literal)* NEWLINE
                | "field" IDENT ":" type_spec field_modifier* NEWLINE ;
"""


def _build_integration_section() -> str:
    return """\
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

mapping_rule  ::= IDENT "<-" (mapping_path | literal) NEWLINE ;

(* A quoted segment carries a name an identifier cannot, e.g. a response
   header: response.headers."X-CorrelationId" (#1776) *)
mapping_path  ::= IDENT ("." (IDENT | STRING))* ;

sync_decl     ::= "sync" IDENT ":" NEWLINE
                  INDENT
                    "mode" ":" ("scheduled" | "event_driven") NEWLINE
                    ("schedule" ":" STRING NEWLINE)?
                    "into" "entity" IDENT NEWLINE
                    ("match" "on" ":" NEWLINE INDENT
                      (IDENT "<->" IDENT NEWLINE)+ DEDENT)?
                  DEDENT ;
"""


def _build_scenario_section() -> str:
    return """\
persona_decl  ::= "persona" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("description" ":" STRING NEWLINE)?
                    ("goals" ":" NEWLINE INDENT ("-" STRING NEWLINE)+ DEDENT)?
                    ("proficiency" ":" IDENT NEWLINE)?
                  DEDENT ;

scenario_decl ::= "scenario" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("description" ":" STRING NEWLINE)?
                    ("seed_script" ":" STRING NEWLINE)?
                    persona_scenario_entry*
                    demo_block?
                  DEDENT ;

persona_scenario_entry
              ::= "as" "persona" IDENT ":" NEWLINE
                  INDENT
                    ("start_route" ":" STRING NEWLINE)?
                    ("seed_script" ":" STRING NEWLINE)?
                  DEDENT ;

demo_block    ::= "demo" IDENT ":" NEWLINE
                  INDENT
                    (IDENT ":" literal NEWLINE)+
                  DEDENT ;
"""


def _build_story_section() -> str:
    return """\
story_decl    ::= "story" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("persona" ":" IDENT NEWLINE)?
                    ("trigger" ":" IDENT NEWLINE)?
                    ("entities" ":" "[" IDENT ("," IDENT)* "]" NEWLINE)?
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
"""


def _build_process_section() -> str:
    # Keep each production's keywords in step with the dispatch in
    # dsl_parser_impl/process.py (pinned by tests/unit/test_grammar_gen.py).
    return """\
process_decl  ::= "process" IDENT STRING? ":" NEWLINE
                  INDENT
                    (STRING NEWLINE)?
                    ("implements" ":" id_list NEWLINE)?
                    ("trigger" ":" (trigger_expr NEWLINE | NEWLINE process_trigger))?
                    ("input" ":" NEWLINE INDENT process_input+ DEDENT)?
                    ("output" ":" NEWLINE INDENT process_output+ DEDENT)?
                    ("steps" ":" NEWLINE INDENT step_item+ DEDENT)?
                    ("compensations" ":" NEWLINE INDENT compensation+ DEDENT)?
                    ("timeout" ":" PROCESS_DURATION NEWLINE)?
                    ("overlap" ":" overlap_policy NEWLINE)?
                  DEDENT ;

id_list       ::= "[" COMPOUND_ID ("," COMPOUND_ID)* "]" | COMPOUND_ID ;

COMPOUND_ID   ::= /[A-Za-z0-9_-]+/ ;  (* e.g. ST-001 *)

process_trigger
              ::= INDENT
                    "when" ":" trigger_expr NEWLINE
                  DEDENT ;

trigger_expr  ::= "entity" IDENT ("created" | "updated" | "deleted")
                | "entity" IDENT "status" (IDENT)? "->" IDENT
                | "manual"
                | "signal" IDENT
                | "process" IDENT "completed" ;

process_input ::= IDENT ":" IDENT ("required" | "=" STRING | STRING)* NEWLINE ;

process_output
              ::= IDENT ":" IDENT STRING? NEWLINE ;

overlap_policy
              ::= "skip" | "queue" | "cancel_previous" | "allow" ;

PROCESS_DURATION ::= /[0-9]+(s|m|h|d)/ ;

step_item     ::= "-" process_step
                | "-" parallel_step ;

process_step  ::= "step" IDENT ":" NEWLINE
                  INDENT
                    step_body
                  DEDENT ;

parallel_step ::= "parallel" IDENT ":" NEWLINE
                  INDENT
                    ("-" process_step)+
                  DEDENT ;

step_body     ::= ("service" ":" IDENT NEWLINE)?
                  ("llm_intent" ":" IDENT NEWLINE)?
                  ("input_map" ":" NEWLINE INDENT (IDENT ":" field_path NEWLINE)+ DEDENT)?
                  ("channel" ":" IDENT NEWLINE)?
                  ("message" ":" IDENT NEWLINE)?
                  ("wait" ":" PROCESS_DURATION NEWLINE)?
                  ("human_task" ":" NEWLINE INDENT human_task_body DEDENT)?
                  ("subprocess" ":" IDENT NEWLINE)?
                  ("condition" ":" (STRING | condition_text) NEWLINE)?
                  ("on_true" ":" IDENT NEWLINE)?
                  ("on_false" ":" IDENT NEWLINE)?
                  ("goto" ":" IDENT NEWLINE)?  (* same as on_success *)
                  ("on_success" ":" IDENT NEWLINE)?
                  ("on_failure" ":" IDENT NEWLINE)?
                  ("compensate" ":" IDENT NEWLINE)?
                  ("timeout" ":" PROCESS_DURATION NEWLINE)?
                  ("retry" ":" NEWLINE INDENT step_retry_config DEDENT)?
                  ("inputs" ":" NEWLINE INDENT input_mapping+ DEDENT)?
                  ("effects" ":" NEWLINE INDENT step_effect+ DEDENT)? ;

condition_text
              ::= /[^\\n]+/ ;  (* the rest of the line, verbatim *)

step_retry_config
              ::= ("max_attempts" ":" NUMBER NEWLINE)?
                  ("backoff" ":" ("fixed" | "exponential" | "linear") NEWLINE)?
                  ("interval" ":" PROCESS_DURATION NEWLINE)? ;

retry_config  ::= ("max_attempts" ":" NUMBER NEWLINE)?
                  ("backoff" ":" IDENT NEWLINE)?
                  ("initial_delay_ms" ":" NUMBER NEWLINE)?
                  ("max_delay_ms" ":" NUMBER NEWLINE)? ;

input_mapping ::= "-" field_path "->" IDENT NEWLINE ;

step_effect   ::= "-" ("create" | "update") IDENT ":" NEWLINE
                  INDENT
                    ("where" ":" (STRING | condition_text) NEWLINE)?
                    ("set" ":" NEWLINE INDENT field_assignment+ DEDENT)?
                  DEDENT ;

field_assignment
              ::= "-" field_path "->" (literal | field_path | IDENT "(" ")") NEWLINE ;

human_task_body
              ::= ("surface" ":" IDENT NEWLINE)?
                  ("entity" ":" IDENT NEWLINE)?
                  ("assignee_role" ":" IDENT NEWLINE)?
                  ("assignee" ":" (STRING | condition_text) NEWLINE)?
                  ("timeout" ":" PROCESS_DURATION NEWLINE)?
                  ("outcomes" ":" NEWLINE INDENT task_outcome+ DEDENT)? ;

task_outcome  ::= "-" IDENT STRING? ":" NEWLINE
                  (INDENT
                    ("label" ":" STRING NEWLINE)?
                    ("goto" ":" IDENT NEWLINE)?
                    ("confirm" ":" STRING NEWLINE)?
                    ("style" ":" IDENT NEWLINE)?
                  DEDENT)? ;

compensation  ::= "-" IDENT ":" NEWLINE
                  (INDENT
                    ("service" ":" IDENT NEWLINE)?
                    ("timeout" ":" PROCESS_DURATION NEWLINE)?
                    ("inputs" ":" NEWLINE INDENT input_mapping+ DEDENT)?
                  DEDENT)? ;

schedule_decl ::= "schedule" IDENT STRING? ":" NEWLINE
                  INDENT
                    (STRING NEWLINE)?
                    ("implements" ":" id_list NEWLINE)?
                    ("cron" ":" (STRING | param_ref) NEWLINE | "interval" ":" PROCESS_DURATION NEWLINE)?
                    ("timezone" ":" (STRING | param_ref) NEWLINE)?
                    ("timeout" ":" (PROCESS_DURATION | param_ref) NEWLINE)?
                    ("steps" ":" NEWLINE INDENT step_item+ DEDENT)?
                    ("overlap" ":" overlap_policy NEWLINE)?  (* accepted, not read: W_DECLARED_NOT_READ *)
                    ("catch_up" ":" BOOLEAN NEWLINE)?  (* accepted, not read: W_DECLARED_NOT_READ *)
                  DEDENT ;

param_ref     ::= "param" "(" STRING ")" ;
"""


def _build_governance_section() -> str:
    return """\
policies_decl ::= "policies" ":" NEWLINE
                  INDENT
                    policy_line+
                  DEDENT ;

policy_line   ::= "classify" IDENT "." IDENT "as" IDENT NEWLINE
                | "erasure" IDENT ":" IDENT NEWLINE ;

tenancy_decl  ::= "tenancy" ":" NEWLINE
                  INDENT
                    ("mode" ":" tenancy_mode NEWLINE)?
                    ("topics" ":" tenancy_topics NEWLINE)?
                    (IDENT ":" (STRING | IDENT | BOOLEAN) NEWLINE)*
                  DEDENT ;

tenancy_mode  ::= "single" | "shared_schema" | "schema_per_tenant"
                | "database_per_tenant" ;

tenancy_topics ::= "shared" | "namespace_per_tenant" ;
"""


def _build_llm_section() -> str:
    return """\
llm_model_decl
              ::= "llm_model" IDENT STRING? ":" NEWLINE
                  INDENT
                    ("tier" ":" IDENT NEWLINE)?
                    ("model_id" ":" STRING NEWLINE)?
                    ("max_tokens" ":" NUMBER NEWLINE)?
                  DEDENT ;

llm_config_decl
              ::= "llm_config" ":" NEWLINE
                  INDENT
                    ("default_model" ":" IDENT NEWLINE)?
                    ("artifact_store" ":" IDENT NEWLINE)?  (* accepted, not read: W_DECLARED_NOT_READ *)
                    ("logging" ":" NEWLINE INDENT llm_logging_body DEDENT)?
                    ("rate_limits" ":" NEWLINE INDENT (IDENT ":" NUMBER NEWLINE)+ DEDENT)?
                    ("concurrency" ":" NEWLINE INDENT (IDENT ":" NUMBER NEWLINE)+ DEDENT)?
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
"""


# Mapping from category -> list of (section_title, grammar_builder_fn)
_GRAMMAR_SECTIONS: dict[str, list[tuple[str | None, object]]] = {
    "Core": [
        (None, lambda: _IDENTIFIERS_SECTION),
        (None, lambda: _TOP_LEVEL_RULES),
        ("Field Types and Modifiers", build_type_spec_rule),
        ("Entity and Archetype Definitions", _build_entity_section),
        ("State Machines", _build_state_machine_section),
        ("Invariants", _build_invariant_section),
        ("Access Rules and Governance", _build_access_section),
        ("Example Data", _build_examples_section),
    ],
    "Surface": [
        ("Surface Definitions", _build_surface_section),
        ("UX Semantic Layer", _build_ux_section),
        ("Workspace Definitions", _build_workspace_section),
        ("Experience Definitions", _build_experience_section),
    ],
    "Workflow": [
        ("Story Definitions", _build_story_section),
        ("Process Workflows and Schedules", _build_process_section),
    ],
    "Integration": [
        ("Service Definitions", _build_service_section),
        ("Foreign Model Definitions", _build_foreign_model_section),
        ("Integration Definitions", _build_integration_section),
    ],
    "Testing": [
        ("Scenario and Demo Data", _build_scenario_section),
    ],
    "Governance": [
        ("Governance Sections", _build_governance_section),
    ],
    "LLM": [
        ("LLM Jobs", _build_llm_section),
    ],
}


# ---------------------------------------------------------------------------
# DSL examples for each category
# ---------------------------------------------------------------------------

_CATEGORY_EXAMPLES: dict[str, str] = {
    "Core": """\
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
""",
    "Surface": """\
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

    as manager:
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
""",
    "Workflow": """\
```dsl
story ST-001 "Staff user completes task":
  persona: staff
  trigger: status_changed
  entities: [Task]
  given:
    - "Task is in progress and assigned"
  then:
    - "Task status becomes done"
    - "Completion time is recorded"

process order_fulfillment "Order Fulfillment":
  implements: [ST-001]

  trigger:
    when: entity Order status -> confirmed

  input:
    order_id: uuid required

  steps:
    - step validate:
        service: validate_order
        on_success: pick
        on_failure: cancel
        retry:
          max_attempts: 3
          backoff: exponential

    - step pick:
        human_task:
          surface: pick_list
          entity: Order
          assignee_role: warehouse
          timeout: 4h
          outcomes:
            - picked "All items picked":
                goto: complete
            - short "Items missing":
                goto: cancel
                style: danger

    - step cancel:
        effects:
          - update Order:
              set:
                - Order.status -> cancelled

schedule daily_report "Daily Report":
  cron: "0 9 * * *"
  timezone: "Europe/London"
  steps:
    - step generate:
        service: generate_report
```
""",
    "Integration": """\
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
""",
    "Testing": """\
```dsl
scenario happy_path "Happy Path":
  description: "Customer submits, agent resolves"
  as persona customer:
    start_route: "/tickets/new"
  as persona agent:
    start_route: "/queue"
```
""",
    "Governance": """\
```dsl
policies:
  classify Customer.email as PII_DIRECT
  classify Order.total as FINANCIAL_TXN
  erasure Customer: anonymize

tenancy:
  mode: shared_schema
```
""",
    "LLM": """\
```dsl
llm_model gpt4 "GPT-4":
  tier: premium
  model_id: "gpt-4-turbo"
  max_tokens: 4096

llm_config:
  default_model: gpt4
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
""",
}


# ---------------------------------------------------------------------------
# Hand-authored documentation sections (#1350)
#
# grammar.md is auto-generated and says "do not edit manually" — but these
# construct guides were hand-appended to the output file over time, so any
# regeneration silently destroyed them. They live here now: edit THESE
# constants, then run `dazzle grammar`.
# ---------------------------------------------------------------------------

_ENTITY_CONSTRUCTS_SECTION = """\
## Entity Constructs

### `subtype_of:` (v0.71.180, #1217 Phase 3e)

Declares an IS-A relationship to a base entity (table-per-type polymorphism).
The child shares the base's primary key via a shared-PK FK; the framework
auto-adds a `kind` enum on the base. **Escape hatch — see ADR-0026 and the
inference KB for guidance on when NOT to reach for this.**

```dsl
entity Vehicle "Vehicle":
  subtype_of: Asset
  wheels: int required
```

Multiple inheritance is not supported (one identifier only). Multi-level
hierarchies (A subtype_of B subtype_of C) are rejected at linker time.

### `managed_by:` (#1333)

Marks an entity whose lifecycle is owned **outside** the workspace/nav
graph — reachable only via a custom route, a pipeline/job, a multi-step
wizard, or an external system. One of `route | pipeline | wizard | external`.

```dsl
entity OnboardingProgress "Onboarding Progress":
  managed_by: route
  id: uuid pk
  stage: str(40) required
```

Its sole effect is to **exempt the entity and its CRUD surfaces from the
dead-construct lint** — they are intentionally absent from any workspace or
`nav` reference, but are not dead code. It is deliberately orthogonal to
`domain:`: unlike `domain: platform`, `managed_by:` does **not** reclassify
the entity's business domain, mark it framework-injected, or skip
modeling/fitness rules. Use `domain: platform` for framework-synthetic
entities; use `managed_by:` for your own route/pipeline/wizard-driven ones.

### `subtype_panel:` (v0.71.184, #1217 Phase 3e.v)

Inside a surface section, dispatches inline rendering by `row.kind`. Each
branch names a snake_case discriminator value and the per-subtype surface
to include. Valid only on surfaces whose entity is a polymorphic base
(linker rule 9).

```dsl
surface asset_card "Asset Card":
  uses entity Asset
  mode: view
  section main:
    field acquired_at "Acquired"
    subtype_panel:
      when kind = vehicle: include surface vehicle_detail
      when kind = building: include surface building_detail
```

Unknown discriminator values raise `E_SUBTYPE_PANEL_UNKNOWN_KIND`. Omitting
a known subtype emits `W_SUBTYPE_PANEL_INCOMPLETE` in
`AppSpec.metadata['link_warnings']`.

### `tenant_host:` (v0.80.X, #1289)

Declares Host-header tenant routing for an entity. When present, the framework
auto-mounts `TenantResolutionMiddleware` that strips `<base_suffix>` from the
incoming `Host` header, looks up the tenant by slug, and attaches a typed
`ResolvedTenant` to `request.state.tenant`.

```dsl
entity Trust:
  id: uuid pk
  slug: slug required unique
  tenant_host:
    topology: provider_subdomain
    domain: example.com
    slug_field: slug
    canonical_hosts: [www.example.com, example.com]
    cookie_scope: host
    super_admin_role: super_admin
    history_entity: TrustSlugHistory
    not_found_template: pipeline.tenant.templates:render_404
    expired_template: pipeline.tenant.templates:render_410
    order: 1
```

Sub-fields: `topology:` (required: `apex` | `provider_subdomain`; ADR-0055),
`domain:` (required), `slug_field:` (required, must reference a
`slug:`-typed field on the same entity), `canonical_hosts:` (required and
exhaustive on `topology: apex`), `cookie_scope:`
(`host` | `apex`, default `host` — slug bounce only when topology is
`provider_subdomain` **and** `cookie_scope: apex`), `super_admin_role:` (default
`super_admin`), `history_entity:`, `not_found_template:` (dotted-path
callable), `expired_template:` (dotted-path callable), `order:` (required
when 2+ entities share a `domain:`), `membership_gated:`, `parent:`.

See the full design in
`archive/docs-superpowers/specs/2026-05-28-tenant-host-keyword-design.md` (archived; see the `archive` branch).

```ebnf
entity_tenant_host_block = "tenant_host" ":" NEWLINE INDENT
    tenant_host_field+
    DEDENT ;

tenant_host_field =
    "domain"             ":" string  NEWLINE
  | "slug_field"         ":" IDENT   NEWLINE
  | "topology"           ":" ("apex" | "provider_subdomain") NEWLINE
  | "canonical_hosts"    ":" "[" host_list "]" NEWLINE
  | "cookie_scope"       ":" ("host" | "apex") NEWLINE
  | "super_admin_role"   ":" IDENT   NEWLINE
  | "history_entity"     ":" IDENT   NEWLINE
  | "not_found_template" ":" dotted_callable NEWLINE
  | "expired_template"   ":" dotted_callable NEWLINE
  | "order"              ":" NUMBER  NEWLINE
  | "membership_gated"   ":" ("true" | "false") NEWLINE
  | "parent"             ":" IDENT   NEWLINE ;
```
"""

_DISPATCH_GUIDE_SECTION = '''\
## Writing a Keyword-Dispatch Parser (post-#1088a)

The `dsl_parser_impl/` family has historically used a `while not self.match(TokenType.DEDENT): if … elif self.match(TokenType.X): … elif self.match(TokenType.Y): …` chain to parse INDENT-bounded blocks. For blocks with more than ~5 keywords this produced hard-to-read monoliths — the worst case (`parse_workspace_region`) reached 859 lines / 52-branch elif chain before #1088a landed.

New parsers — and refactors of existing ones — should use the **keyword-dispatch helper** in `src/dazzle/core/dsl_parser_impl/dispatch.py`:

```python
from dataclasses import dataclass, field
from dazzle.core.dsl_parser_impl.dispatch import (
    KeywordParser,
    parse_block_with_dispatch,
)
from dazzle.core.lexer import TokenType


@dataclass
class _PersonaState:
    """Accumulator — one field per legal keyword in the block."""
    description: str | None = None
    goals: list[str] = field(default_factory=list)
    proficiency: str = "intermediate"
    # ...


def _kw_description(parser, state: _PersonaState) -> None:
    parser.advance()                                  # consume `description`
    parser.expect(TokenType.COLON)
    state.description = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _kw_goals(parser, state: _PersonaState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.goals = parser._parse_string_list()
    parser.skip_newlines()


_PERSONA_KEYWORDS: dict[TokenType, KeywordParser] = {
    TokenType.DESCRIPTION: _kw_description,
    TokenType.GOALS:       _kw_goals,
}
_PERSONA_IDENT_KEYWORDS: dict[str, KeywordParser] = {
    "default_workspace":   _kw_default_workspace,
    "backed_by":           _kw_backed_by,
    # ...
}


class ScenarioParserMixin:
    def parse_persona(self) -> ir.PersonaSpec:
        persona_id, label, _ = self._parse_construct_header(
            TokenType.PERSONA, allow_keyword_name=True,
        )
        state = _PersonaState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_PERSONA_KEYWORDS,
            ident_keywords=_PERSONA_IDENT_KEYWORDS,
            state=state,
        )
        self.expect(TokenType.DEDENT)
        return _build_persona(persona_id, label or persona_id, state)
```

### Rules of thumb

1. **One accumulator dataclass per block.** Field names match the keyword names; defaults match what an absent keyword should mean.
2. **One keyword-parser function per keyword.** Module-private (`_kw_*` prefix). Takes `(parser, state)`, mutates `state`, advances the parser past its value tokens.
3. **Two dispatch tables.** `first_class_keywords` for keywords with their own `TokenType` (e.g. `TokenType.DESCRIPTION`). `ident_keywords` for keywords matched as plain `IDENTIFIER` tokens (e.g. `"backed_by"`).
4. **Caller owns the header and the closing DEDENT.** The helper handles only the body — that keeps `_parse_construct_header` and the final IR-build under direct caller control.
5. **`on_unknown=...` for custom recovery.** The default raises `"Unknown keyword in block: 'foo'"`. Override when the block has a renamed-keyword diagnostic, an `extra_attrs` catch-all, or other bespoke recovery.

### When *not* to use the dispatch helper

- Blocks with ≤3 keywords. The dispatch indirection costs more than the elif chain saves.
- Parsers that need positional argument order (rare in Dazzle DSL but possible — most state machines need this).
- Parsers where the keyword-parser logic needs information from earlier keywords mid-block (rare — usually the accumulator-then-build pattern handles this fine, but if you need conditional sub-grammars based on `display:` for instance, that's still handled by the accumulator + a post-loop dispatch on `state.display`).
'''


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_grammar() -> str:
    """
    Generate the full grammar markdown document.

    Returns:
        Complete markdown content for docs/reference/grammar.md
    """
    version = get_version()
    parts: list[str] = []

    # Header
    parts.append("# DSL Grammar Specification\n")
    parts.append(f"Formal EBNF grammar for DAZZLE DSL v{version}.\n")
    parts.append(
        "> **Auto-generated** from parser source code by `grammar_gen.py`. "
        "Do not edit manually; run `dazzle grammar` to regenerate.\n"
    )

    # Overview
    parts.append("## Overview\n")
    parts.append(
        "This grammar defines the complete syntax for the DAZZLE Domain-Specific Language. "
        "The DSL supports the following construct categories:\n"
    )
    for cat in _CATEGORY_ORDER:
        sections = _GRAMMAR_SECTIONS.get(cat, [])
        section_names = ", ".join(title for title, _ in sections if title)
        parts.append(f"- **{cat}**: {section_names}")
    parts.append("")

    # Anti-Turing note
    parts.append("## Anti-Turing Enforcement\n")
    parts.append("DAZZLE intentionally limits computational expressiveness to ensure:\n")
    parts.append("- Aggregate functions only in computed expressions")
    parts.append("- `AGGREGATE_FN` explicitly enumerates allowed functions")
    parts.append("- Turing-complete logic lives in service stubs (not DSL)\n")

    # Keyword inventory
    parts.append("## Keyword Inventory\n")
    keyword_groups = get_keyword_groups()
    for group, keywords in keyword_groups.items():
        parts.append(f"**{group}**: `{'`, `'.join(keywords)}`\n")

    # Field types
    parts.append("## Field Types\n")
    parts.append("All field types supported by the DSL (from `FieldTypeKind` enum):\n")
    for kind in FieldTypeKind:
        parts.append(f"- `{kind.value}`")
    parts.append("")

    # Full grammar
    parts.append("## Full Grammar\n")
    parts.append("```ebnf")
    parts.append(_EBNF_HEADER.format(version=version).rstrip())
    parts.append("")

    for cat in _CATEGORY_ORDER:
        sections = _GRAMMAR_SECTIONS.get(cat, [])
        for title, builder in sections:
            if title:
                parts.append(_section_separator(title))
            content = str(builder() if callable(builder) else builder)
            parts.append(content.rstrip())
            parts.append("")

    parts.append("```\n")

    # Hand-authored construct guides (preserved across regeneration, #1350)
    parts.append(_ENTITY_CONSTRUCTS_SECTION.rstrip())
    parts.append("")

    # DSL examples by category
    parts.append("## DSL Examples\n")
    for cat in _CATEGORY_ORDER:
        example = _CATEGORY_EXAMPLES.get(cat)
        if example:
            parts.append(f"### {cat}\n")
            parts.append(example.rstrip())
            parts.append("")

    # Parser mixin coverage
    parts.append("## Parser Mixin Coverage\n")
    parts.append("The grammar above is derived from these parser mixin modules:\n")
    parts.append("| Module | Class | Category |")
    parts.append("|--------|-------|----------|")
    class_names = get_mixin_class_names()
    for mod_name, _title, category in _MIXIN_SECTIONS:
        cls_name = class_names.get(mod_name, "-")
        parts.append(f"| `{mod_name}.py` | `{cls_name}` | {category} |")
    parts.append("")

    # Hand-authored contributor guide (preserved across regeneration, #1350)
    parts.append(_DISPATCH_GUIDE_SECTION.rstrip())
    parts.append("")

    return "\n".join(parts) + "\n"


def write_grammar(output_path: Path | None = None) -> Path:
    """
    Generate and write the grammar markdown file.

    Args:
        output_path: Path to write to; defaults to docs/reference/grammar.md

    Returns:
        Path to the written file
    """
    if output_path is None:
        output_path = Path.cwd() / "docs" / "reference" / "grammar.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = generate_grammar()
    output_path.write_text(content, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if "--write" in sys.argv:
        path = write_grammar()
        print(f"Wrote grammar to {path}")
    else:
        print(generate_grammar())
