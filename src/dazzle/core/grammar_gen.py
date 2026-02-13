"""
Grammar documentation generator for the DAZZLE DSL.

Introspects the parser source code (mixin docstrings, lexer keywords,
IR field types) to produce an authoritative EBNF grammar specification.

Usage:
    python -m dazzle.core.grammar_gen           # print to stdout
    dazzle grammar                              # write docs/reference/grammar.md
"""

from __future__ import annotations

import importlib
import inspect
import re
import textwrap
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
    ("flow", "E2E Test Flows", "Testing"),
    ("test", "API Contract Tests", "Testing"),
    ("scenario", "Scenario and Demo Data", "Testing"),
    ("story", "Story Definitions", "Workflow"),
    ("process", "Process Workflows", "Workflow"),
    ("messaging", "Messaging Channels", "Eventing"),
    ("eventing", "Event-First Architecture", "Eventing"),
    ("hless", "HLESS Event Semantics", "Eventing"),
    ("ledger", "TigerBeetle Ledgers and Transactions", "Financial"),
    ("governance", "Governance Sections", "Governance"),
    ("llm", "LLM Jobs", "LLM"),
]

# Categories in presentation order.
_CATEGORY_ORDER = [
    "Core",
    "Surface",
    "Workflow",
    "Integration",
    "Testing",
    "Eventing",
    "Financial",
    "Governance",
    "LLM",
]


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


def get_mixin_docstring(mod_name: str) -> str:
    """Return the module-level docstring for a parser mixin."""
    mod = _load_mixin_module(mod_name)
    return inspect.getdoc(mod) or ""


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


def extract_dsl_examples(mod_name: str) -> list[str]:
    """Extract DSL code blocks from a module docstring."""
    docstring = get_mixin_docstring(mod_name)
    blocks: list[str] = []

    # Find indented code blocks after "DSL syntax" or "DSL Syntax" lines
    in_block = False
    current_block: list[str] = []
    for line in docstring.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("dsl syntax"):
            in_block = True
            continue
        if in_block:
            if stripped == "" and current_block:
                # End of indented block on blank line after content
                pass
            elif line.startswith("    ") or line.startswith("\t"):
                current_block.append(line)
            elif stripped and current_block:
                # Non-indented line after content = end of block
                blocks.append(textwrap.dedent("\n".join(current_block)).strip())
                current_block = []
                in_block = False
            elif not stripped and not current_block:
                # Blank line before content starts
                continue
            else:
                in_block = False

    if current_block:
        blocks.append(textwrap.dedent("\n".join(current_block)).strip())

    return blocks


# ---------------------------------------------------------------------------
# Helpers — keyword inventory
# ---------------------------------------------------------------------------


def get_keyword_groups() -> dict[str, list[str]]:
    """
    Extract keywords from TokenType, grouped by version/feature comment blocks.

    Returns a dict of group_label -> list[keyword_value].
    """
    source_path = Path(__file__).parent / "lexer.py"
    source = source_path.read_text()

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
                | "role" "(" IDENT ("," IDENT)* ")"
                | "auto" "after" NUMBER time_unit ("or" "manual")?
                | "manual" ;

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
"""


def _build_workspace_section() -> str:
    return """\
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
"""


def _build_flow_section() -> str:
    return """\
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
"""


def _build_test_section() -> str:
    return """\
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
"""


def _build_story_section() -> str:
    return """\
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
"""


def _build_process_section() -> str:
    return """\
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
"""


def _build_messaging_section() -> str:
    return """\
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
"""


def _build_eventing_section() -> str:
    return """\
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
"""


def _build_hless_section() -> str:
    return """\
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
"""


def _build_ledger_section() -> str:
    return """\
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
"""


def _build_llm_section() -> str:
    return """\
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
        ("E2E Test Flows", _build_flow_section),
        ("API Contract Tests", _build_test_section),
        ("Scenario and Demo Data", _build_scenario_section),
    ],
    "Eventing": [
        ("Messaging Channels", _build_messaging_section),
        ("Event-First Architecture", _build_eventing_section),
        ("HLESS Event Semantics", _build_hless_section),
    ],
    "Financial": [
        ("TigerBeetle Ledgers and Transactions", _build_ledger_section),
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
""",
    "Workflow": """\
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
""",
    "Testing": """\
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
""",
    "Eventing": """\
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
""",
    "Financial": """\
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
""",
}


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
        project_root = Path(__file__).resolve().parents[3]
        output_path = project_root / "docs" / "reference" / "grammar.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = generate_grammar()
    output_path.write_text(content)
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
