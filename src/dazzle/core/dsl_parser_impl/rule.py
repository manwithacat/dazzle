"""
Rule parser mixin for DAZZLE DSL.

Parses rule blocks with kind, origin, invariant, and scope fields.

DSL Syntax (v0.41.0):
    rule RULE-C-001 "Customer can identify their next required action":
      kind: constraint
      origin: top_down
      invariant: customer dashboard shows actionable items with clear next steps
      scope: [Customer, Task]
      status: accepted
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class RuleParserMixin:
    """Parser mixin for rule blocks."""

    # Type stubs for methods provided by BaseParser
    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any
        _source_location: Any
        _parse_compound_id: Any
        _parse_identifier_list: Any

    def parse_rule(self) -> ir.RuleSpec:
        """
        Parse a rule block.

        Grammar:
            rule RULE_ID STRING COLON NEWLINE INDENT
              [kind COLON IDENTIFIER NEWLINE]
              [origin COLON IDENTIFIER NEWLINE]
              [invariant COLON text NEWLINE]
              [scope COLON LBRACKET identifier_list RBRACKET NEWLINE]
              [status COLON IDENTIFIER NEWLINE]
            DEDENT

        Returns:
            RuleSpec with parsed values
        """
        loc = self._source_location()
        rule_id = self._parse_compound_id()
        title = self.expect(TokenType.STRING).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Parse optional description (docstring-style)
        description = None
        if self.match(TokenType.STRING):
            description = self.advance().value
            self.skip_newlines()

        # Initialize fields
        kind: ir.RuleKind | None = None
        origin: ir.RuleOrigin | None = None
        invariant: str | None = None
        scope: list[str] = []
        status: ir.RuleStatus | None = None

        # Parse rule fields
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()
            field_name = token.value

            if field_name == "kind":
                self.advance()
                self.expect(TokenType.COLON)
                kind_str = self.advance().value
                kind = self._parse_rule_kind(kind_str)
                self.skip_newlines()

            elif field_name == "origin":
                self.advance()
                self.expect(TokenType.COLON)
                origin_str = self.advance().value
                origin = self._parse_rule_origin(origin_str)
                self.skip_newlines()

            elif field_name == "invariant":
                self.advance()
                self.expect(TokenType.COLON)
                invariant = self._parse_rule_text()
                self.skip_newlines()

            elif field_name == "scope":
                self.advance()
                self.expect(TokenType.COLON)
                scope = self._parse_identifier_list()
                self.skip_newlines()

            elif field_name == "status":
                self.advance()
                self.expect(TokenType.COLON)
                status_str = self.advance().value
                status = self._parse_rule_status(status_str)
                self.skip_newlines()

            else:
                # Skip unknown field
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    self._skip_rule_field()

        self.expect(TokenType.DEDENT)

        return ir.RuleSpec(
            rule_id=rule_id,
            title=title,
            description=description,
            kind=kind or ir.RuleKind.CONSTRAINT,
            origin=origin or ir.RuleOrigin.TOP_DOWN,
            invariant=invariant,
            scope=scope,
            status=status or ir.RuleStatus.DRAFT,
            source=loc,
        )

    def _parse_rule_text(self) -> str:
        """Parse text until end of line — supports quoted or unquoted."""
        if self.match(TokenType.STRING):
            return str(self.advance().value)

        parts: list[str] = []
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            token = self.current_token()
            parts.append(token.value)
            self.advance()
        return " ".join(parts)

    def _parse_rule_kind(self, kind_str: str) -> ir.RuleKind:
        """Parse kind string to RuleKind enum."""
        kind_map = {
            "constraint": ir.RuleKind.CONSTRAINT,
            "precondition": ir.RuleKind.PRECONDITION,
            "authorization": ir.RuleKind.AUTHORIZATION,
            "derivation": ir.RuleKind.DERIVATION,
        }
        if kind_str in kind_map:
            return kind_map[kind_str]

        from ..errors import make_parse_error

        valid = ", ".join(kind_map.keys())
        raise make_parse_error(
            f"Invalid rule kind '{kind_str}'. Valid kinds: {valid}",
            self.file,
            self.current_token().line,
            self.current_token().column,
        )

    def _parse_rule_origin(self, origin_str: str) -> ir.RuleOrigin:
        """Parse origin string to RuleOrigin enum."""
        origin_map = {
            "top_down": ir.RuleOrigin.TOP_DOWN,
            "bottom_up": ir.RuleOrigin.BOTTOM_UP,
        }
        if origin_str in origin_map:
            return origin_map[origin_str]

        from ..errors import make_parse_error

        valid = ", ".join(origin_map.keys())
        raise make_parse_error(
            f"Invalid rule origin '{origin_str}'. Valid origins: {valid}",
            self.file,
            self.current_token().line,
            self.current_token().column,
        )

    def _parse_rule_status(self, status_str: str) -> ir.RuleStatus:
        """Parse status string to RuleStatus enum."""
        status_map = {
            "draft": ir.RuleStatus.DRAFT,
            "accepted": ir.RuleStatus.ACCEPTED,
            "rejected": ir.RuleStatus.REJECTED,
        }
        if status_str in status_map:
            return status_map[status_str]

        from ..errors import make_parse_error

        valid = ", ".join(status_map.keys())
        raise make_parse_error(
            f"Invalid rule status '{status_str}'. Valid statuses: {valid}",
            self.file,
            self.current_token().line,
            self.current_token().column,
        )

    def _skip_rule_field(self) -> None:
        """Skip tokens until we reach the next field or end of block."""
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            if self.match(TokenType.NEWLINE):
                self.skip_newlines()
                # Check if next token looks like a new field (identifier followed by colon)
                if self.match(TokenType.DEDENT, TokenType.EOF):
                    break
                # Peek: if the next-next token is a colon, this is a new field
                break
            self.advance()
