"""
Restricted template parser for DAZZLE messaging.

Provides a safe, Jinja-ish template syntax with intentional limitations:
- Variable interpolation: {{ variable }}
- Dot notation: {{ user.email }}
- Conditionals: {% if condition %}...{% endif %}
- NO loops (for security and simplicity)
- NO filters (use computed fields in DSL instead)
- NO math operations (compute in DSL layer)
- NO function calls

This keeps templates simple, secure, and easy to reason about.
LLMs can generate these templates without risk of injection attacks.

Example:
    template = "Hello {{ user.name }}, your order #{{ order.number }} is confirmed."
    result = render_template(template, {"user": {"name": "John"}, "order": {"number": "1234"}})
    # Result: "Hello John, your order #1234 is confirmed."
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger("dazzle.channels.templates")


class TemplateError(Exception):
    """Error in template parsing or rendering."""

    pass


class TemplateSyntaxError(TemplateError):
    """Invalid template syntax."""

    def __init__(self, message: str, position: int | None = None):
        self.position = position
        super().__init__(message)


class TemplateRenderError(TemplateError):
    """Error during template rendering."""

    pass


# =============================================================================
# Token Types
# =============================================================================


class TokenType(Enum):
    """Template token types."""

    TEXT = "text"
    VAR = "var"  # {{ variable }}
    IF = "if"  # {% if condition %}
    ELIF = "elif"  # {% elif condition %}
    ELSE = "else"  # {% else %}
    ENDIF = "endif"  # {% endif %}


@dataclass
class Token:
    """A template token."""

    type: TokenType
    value: str
    position: int


# =============================================================================
# Lexer
# =============================================================================

# Regex patterns for template syntax
VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")
# Use [^%]+ to avoid matching the closing %} in the expression
TAG_PATTERN = re.compile(r"\{%\s*(if|elif|else|endif)(?:\s+([^%]+?))?\s*%\}")


def tokenize(template: str) -> list[Token]:
    """Tokenize a template string.

    Args:
        template: Template string to tokenize

    Returns:
        List of tokens

    Raises:
        TemplateSyntaxError: If template has invalid syntax
    """
    tokens: list[Token] = []
    pos = 0

    while pos < len(template):
        # Check for variable interpolation {{ var }}
        var_match = VAR_PATTERN.match(template, pos)
        if var_match:
            tokens.append(Token(TokenType.VAR, var_match.group(1), pos))
            pos = var_match.end()
            continue

        # Check for control tags {% if/elif/else/endif %}
        tag_match = TAG_PATTERN.match(template, pos)
        if tag_match:
            tag_type = tag_match.group(1)
            tag_expr = tag_match.group(2) or ""

            if tag_type == "if":
                if not tag_expr.strip():
                    raise TemplateSyntaxError("{% if %} requires a condition", pos)
                tokens.append(Token(TokenType.IF, tag_expr.strip(), pos))
            elif tag_type == "elif":
                if not tag_expr.strip():
                    raise TemplateSyntaxError("{% elif %} requires a condition", pos)
                tokens.append(Token(TokenType.ELIF, tag_expr.strip(), pos))
            elif tag_type == "else":
                tokens.append(Token(TokenType.ELSE, "", pos))
            elif tag_type == "endif":
                tokens.append(Token(TokenType.ENDIF, "", pos))

            pos = tag_match.end()
            continue

        # Check for invalid/unsupported syntax
        if template[pos : pos + 2] == "{{":
            raise TemplateSyntaxError(
                f"Invalid variable syntax at position {pos}. "
                "Use {{ variable_name }} with valid identifier.",
                pos,
            )

        if template[pos : pos + 2] == "{%":
            # Check for unsupported tags
            for_match = re.match(r"\{%\s*for\b", template[pos:])
            if for_match:
                raise TemplateSyntaxError(
                    "{% for %} loops are not supported. Use DSL list operations instead.",
                    pos,
                )

            macro_match = re.match(r"\{%\s*macro\b", template[pos:])
            if macro_match:
                raise TemplateSyntaxError(
                    "{% macro %} is not supported. Keep templates simple.",
                    pos,
                )

            raise TemplateSyntaxError(
                f"Invalid or unsupported tag at position {pos}. "
                "Only if/elif/else/endif are supported.",
                pos,
            )

        # Regular text - find next special sequence
        next_var = template.find("{{", pos)
        next_tag = template.find("{%", pos)

        if next_var == -1:
            next_var = len(template)
        if next_tag == -1:
            next_tag = len(template)

        end = min(next_var, next_tag)
        if end == pos:
            end = pos + 1

        text = template[pos:end]
        if text:
            tokens.append(Token(TokenType.TEXT, text, pos))
        pos = end

    return tokens


# =============================================================================
# AST Nodes
# =============================================================================


@dataclass
class TextNode:
    """Plain text node."""

    text: str


@dataclass
class VarNode:
    """Variable interpolation node."""

    path: list[str]  # e.g., ["user", "email"]


@dataclass
class IfNode:
    """Conditional node."""

    condition: str
    then_body: list[Any]  # List of nodes
    elif_branches: list[tuple[str, list[Any]]]  # [(condition, body), ...]
    else_body: list[Any] | None


def parse(tokens: list[Token]) -> list[Any]:
    """Parse tokens into an AST.

    Args:
        tokens: List of tokens from lexer

    Returns:
        List of AST nodes

    Raises:
        TemplateSyntaxError: If template structure is invalid
    """
    nodes: list[Any] = []
    pos = 0

    while pos < len(tokens):
        token = tokens[pos]

        if token.type == TokenType.TEXT:
            nodes.append(TextNode(token.value))
            pos += 1

        elif token.type == TokenType.VAR:
            path = token.value.split(".")
            nodes.append(VarNode(path))
            pos += 1

        elif token.type == TokenType.IF:
            if_node, new_pos = parse_if(tokens, pos)
            nodes.append(if_node)
            pos = new_pos

        elif token.type in (TokenType.ELIF, TokenType.ELSE, TokenType.ENDIF):
            # These should be consumed by parse_if
            raise TemplateSyntaxError(
                f"Unexpected {{% {token.type.value} %}} outside of if block",
                token.position,
            )

        else:
            pos += 1

    return nodes


def parse_if(tokens: list[Token], start: int) -> tuple[IfNode, int]:
    """Parse an if/elif/else/endif block.

    Args:
        tokens: All tokens
        start: Position of the IF token

    Returns:
        Tuple of (IfNode, next_position)
    """
    if tokens[start].type != TokenType.IF:
        raise TemplateSyntaxError("Expected {% if %}", tokens[start].position)

    condition = tokens[start].value
    then_body: list[Any] = []
    elif_branches: list[tuple[str, list[Any]]] = []
    else_body: list[Any] | None = None

    pos = start + 1
    current_body = then_body

    while pos < len(tokens):
        token = tokens[pos]

        if token.type == TokenType.ENDIF:
            return IfNode(condition, then_body, elif_branches, else_body), pos + 1

        elif token.type == TokenType.ELIF:
            elif_branches.append((token.value, []))
            current_body = elif_branches[-1][1]
            pos += 1

        elif token.type == TokenType.ELSE:
            else_body = []
            current_body = else_body
            pos += 1

        elif token.type == TokenType.TEXT:
            current_body.append(TextNode(token.value))
            pos += 1

        elif token.type == TokenType.VAR:
            path = token.value.split(".")
            current_body.append(VarNode(path))
            pos += 1

        elif token.type == TokenType.IF:
            # Nested if
            nested_if, new_pos = parse_if(tokens, pos)
            current_body.append(nested_if)
            pos = new_pos

        else:
            pos += 1

    raise TemplateSyntaxError(
        f"Unclosed {{% if %}} block starting at position {tokens[start].position}",
        tokens[start].position,
    )


# =============================================================================
# Renderer
# =============================================================================


def resolve_path(context: dict[str, Any], path: list[str]) -> Any:
    """Resolve a dotted path in a context dictionary.

    Args:
        context: Context dictionary
        path: List of path segments, e.g., ["user", "email"]

    Returns:
        Resolved value or empty string if not found
    """
    value: Any = context
    for segment in path:
        if isinstance(value, dict):
            value = value.get(segment)
        elif hasattr(value, segment):
            value = getattr(value, segment)
        else:
            return ""

        if value is None:
            return ""

    return value


def evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
    """Evaluate a simple condition.

    Supports:
    - Variable references: user.is_active
    - Equality: user.role == "admin"
    - Inequality: user.role != "guest"
    - Boolean values: true, false

    Args:
        condition: Condition string
        context: Context dictionary

    Returns:
        Boolean result
    """
    condition = condition.strip()

    # Check for equality/inequality
    for op in ("==", "!="):
        if op in condition:
            parts = condition.split(op, 1)
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip()

                # Resolve left side (variable path)
                left_value = resolve_path(context, left.split("."))

                # Resolve right side (literal or variable)
                if right.startswith('"') and right.endswith('"'):
                    right_value = right[1:-1]
                elif right.startswith("'") and right.endswith("'"):
                    right_value = right[1:-1]
                elif right == "true":
                    right_value = True
                elif right == "false":
                    right_value = False
                elif right.isdigit():
                    right_value = int(right)
                else:
                    right_value = resolve_path(context, right.split("."))

                if op == "==":
                    return left_value == right_value
                else:
                    return left_value != right_value

    # Simple truthiness check
    if condition == "true":
        return True
    if condition == "false":
        return False

    value = resolve_path(context, condition.split("."))
    return bool(value)


def render_nodes(nodes: list[Any], context: dict[str, Any]) -> str:
    """Render AST nodes to a string.

    Args:
        nodes: List of AST nodes
        context: Context dictionary

    Returns:
        Rendered string
    """
    result: list[str] = []

    for node in nodes:
        if isinstance(node, TextNode):
            result.append(node.text)

        elif isinstance(node, VarNode):
            value = resolve_path(context, node.path)
            result.append(str(value) if value is not None else "")

        elif isinstance(node, IfNode):
            if evaluate_condition(node.condition, context):
                result.append(render_nodes(node.then_body, context))
            else:
                # Check elif branches
                matched = False
                for elif_condition, elif_body in node.elif_branches:
                    if evaluate_condition(elif_condition, context):
                        result.append(render_nodes(elif_body, context))
                        matched = True
                        break

                # Fall back to else if no elif matched
                if not matched and node.else_body:
                    result.append(render_nodes(node.else_body, context))

    return "".join(result)


# =============================================================================
# Public API
# =============================================================================


def render_template(template: str, context: dict[str, Any]) -> str:
    """Render a template with the given context.

    This is the main entry point for template rendering.

    Args:
        template: Template string
        context: Dictionary of variables

    Returns:
        Rendered string

    Raises:
        TemplateSyntaxError: If template has invalid syntax
        TemplateRenderError: If rendering fails

    Example:
        >>> render_template("Hello {{ name }}!", {"name": "World"})
        'Hello World!'

        >>> render_template(
        ...     "{% if user.is_admin %}Admin{% else %}User{% endif %}",
        ...     {"user": {"is_admin": True}}
        ... )
        'Admin'
    """
    try:
        tokens = tokenize(template)
        ast = parse(tokens)
        return render_nodes(ast, context)
    except TemplateError:
        raise
    except Exception as e:
        raise TemplateRenderError(f"Template rendering failed: {e}") from e


def validate_template(template: str) -> list[str]:
    """Validate a template without rendering.

    Args:
        template: Template string to validate

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    try:
        tokens = tokenize(template)
        parse(tokens)
    except TemplateSyntaxError as e:
        errors.append(str(e))
    except Exception as e:
        errors.append(f"Unexpected error: {e}")

    return errors


def extract_variables(template: str) -> list[str]:
    """Extract all variable paths used in a template.

    Args:
        template: Template string

    Returns:
        List of variable paths (e.g., ["user.email", "order.number"])
    """
    variables: list[str] = []

    # Find all variable references
    for match in VAR_PATTERN.finditer(template):
        path = match.group(1)
        if path not in variables:
            variables.append(path)

    # Find variables in conditions
    for match in TAG_PATTERN.finditer(template):
        condition = match.group(2) or ""
        # Extract variable-like patterns from condition
        for var_match in re.finditer(r"([a-zA-Z_][a-zA-Z0-9_.]*)", condition):
            var = var_match.group(1)
            # Skip boolean literals and operators
            if var not in ("true", "false", "if", "elif", "else", "endif"):
                if var not in variables:
                    variables.append(var)

    return variables
