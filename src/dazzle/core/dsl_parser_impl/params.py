"""
Param parser mixin for DAZZLE DSL.

Parses runtime parameter declarations.

DSL Syntax (v0.44.0):
    param heatmap.rag.thresholds "RAG boundary percentages":
      type: list[float]
      default: [40, 60]
      scope: tenant
      category: "Assessment Display"
      sensitive: true
      constraints:
        min_length: 2
        max_length: 5
        ordered: ascending
        range: [0, 100]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class ParamParserMixin:
    """Parser mixin for param declarations."""

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

    def parse_param(self) -> ir.ParamSpec:
        """
        Parse a param declaration.

        The 'param' keyword has already been consumed by the dispatcher.

        Grammar:
            param DOTTED_KEY [STRING] COLON NEWLINE INDENT
              type COLON TYPE_EXPR NEWLINE
              default COLON VALUE NEWLINE
              scope COLON IDENTIFIER NEWLINE
              [category COLON STRING NEWLINE]
              [sensitive COLON BOOL NEWLINE]
              [constraints COLON NEWLINE INDENT
                KEY COLON VALUE ...
              DEDENT]
            DEDENT

        Returns:
            ParamSpec with parsed values.
        """
        # Parse dotted key name: heatmap.rag.thresholds
        key_parts = [self.expect_identifier_or_keyword().value]
        while self.match(TokenType.DOT):
            self.advance()
            key_parts.append(self.expect_identifier_or_keyword().value)
        key = ".".join(key_parts)

        # Optional title string
        description: str | None = None
        if self.match(TokenType.STRING):
            description = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Parse body fields
        param_type: str = "str"
        default: Any = None
        scope: str = "system"
        category: str | None = None
        sensitive: bool = False
        constraints: ir.ParamConstraints | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()

            # type: <type_expr>
            if token.value == "type":
                self.advance()
                self.expect(TokenType.COLON)
                param_type = self._parse_param_type_expr()
                self.skip_newlines()

            # default: <value>
            elif token.value == "default":
                self.advance()
                self.expect(TokenType.COLON)
                default = self._parse_param_default_value()
                self.skip_newlines()

            # scope: system|tenant|user
            elif token.type == TokenType.SCOPE:
                self.advance()
                self.expect(TokenType.COLON)
                scope = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # category: "string"
            elif token.value == "category":
                self.advance()
                self.expect(TokenType.COLON)
                category = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # sensitive: true|false
            elif token.value == "sensitive":
                self.advance()
                self.expect(TokenType.COLON)
                sensitive = self.current_token().type == TokenType.TRUE
                self.advance()
                self.skip_newlines()

            # constraints: (nested block)
            elif token.value == "constraints":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                constraints = self._parse_param_constraints()

            else:
                # Skip unknown fields
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    # Consume rest of line
                    while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
                        self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.ParamSpec(
            key=key,
            param_type=param_type,
            default=default,
            scope=scope,
            description=description,
            category=category,
            sensitive=sensitive,
            constraints=constraints,
        )

    def _parse_param_type_expr(self) -> str:
        """Parse type expression as string, e.g. 'list[float]', 'int', 'str'."""
        parts: list[str] = []
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            parts.append(self.current_token().value)
            self.advance()
        return "".join(parts)

    def _parse_param_default_value(self) -> Any:
        """Parse a default value: number, string, bool, or bracket-enclosed list."""
        # String literal
        if self.match(TokenType.STRING):
            return self.advance().value

        # Boolean
        if self.match(TokenType.TRUE):
            self.advance()
            return True
        if self.match(TokenType.FALSE):
            self.advance()
            return False

        # List: [...]
        if self.match(TokenType.LBRACKET):
            return self._parse_param_list_value()

        # Number (possibly negative or decimal)
        if self.match(TokenType.NUMBER):
            return self._parse_param_number()

        if self.match(TokenType.MINUS):
            self.advance()
            if self.match(TokenType.NUMBER):
                return -self._parse_param_number()

        # Fallback: consume tokens as string until newline
        parts: list[str] = []
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            parts.append(self.current_token().value)
            self.advance()
        return " ".join(parts)

    def _parse_param_number(self) -> int | float:
        """Parse a number, handling decimals like 0.75."""
        num_str = self.expect(TokenType.NUMBER).value
        if self.match(TokenType.DOT):
            self.advance()
            frac = self.expect(TokenType.NUMBER).value
            num_str = num_str + "." + frac
        val = float(num_str)
        if val == int(val) and "." not in num_str:
            return int(val)
        return val

    def _parse_param_list_value(self) -> list[Any]:
        """Parse a bracket-enclosed list of values."""
        self.expect(TokenType.LBRACKET)
        items: list[Any] = []
        while not self.match(TokenType.RBRACKET):
            self.skip_newlines()
            if self.match(TokenType.RBRACKET):
                break

            if self.match(TokenType.STRING):
                items.append(self.advance().value)
            elif self.match(TokenType.NUMBER):
                items.append(self._parse_param_number())
            elif self.match(TokenType.MINUS):
                self.advance()
                if self.match(TokenType.NUMBER):
                    items.append(-self._parse_param_number())
            elif self.match(TokenType.TRUE):
                self.advance()
                items.append(True)
            elif self.match(TokenType.FALSE):
                self.advance()
                items.append(False)
            else:
                # Identifier or keyword as string value
                items.append(self.advance().value)

            if self.match(TokenType.COMMA):
                self.advance()
            self.skip_newlines()

        self.expect(TokenType.RBRACKET)
        return items

    def _parse_param_constraints(self) -> ir.ParamConstraints:
        """Parse a constraints sub-block."""
        self.expect(TokenType.INDENT)

        min_value: float | None = None
        max_value: float | None = None
        min_length: int | None = None
        max_length: int | None = None
        ordered: str | None = None
        range_val: list[float] | None = None
        enum_values: list[str] | None = None
        pattern: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            field_name = self.expect_identifier_or_keyword().value
            self.expect(TokenType.COLON)

            if field_name == "min_value":
                min_value = self._parse_constraint_number()
            elif field_name == "max_value":
                max_value = self._parse_constraint_number()
            elif field_name == "min_length":
                min_length = int(self.expect(TokenType.NUMBER).value)
            elif field_name == "max_length":
                max_length = int(self.expect(TokenType.NUMBER).value)
            elif field_name == "ordered":
                ordered = self.expect_identifier_or_keyword().value
            elif field_name == "range":
                range_val = []
                self.expect(TokenType.LBRACKET)
                while not self.match(TokenType.RBRACKET):
                    self.skip_newlines()
                    if self.match(TokenType.RBRACKET):
                        break
                    range_val.append(self._parse_constraint_number())
                    if self.match(TokenType.COMMA):
                        self.advance()
                    self.skip_newlines()
                self.expect(TokenType.RBRACKET)
            elif field_name == "enum_values":
                enum_values = []
                self.expect(TokenType.LBRACKET)
                while not self.match(TokenType.RBRACKET):
                    self.skip_newlines()
                    if self.match(TokenType.RBRACKET):
                        break
                    enum_values.append(self.expect(TokenType.STRING).value)
                    if self.match(TokenType.COMMA):
                        self.advance()
                    self.skip_newlines()
                self.expect(TokenType.RBRACKET)
            elif field_name == "pattern":
                pattern = self.expect(TokenType.STRING).value
            else:
                # Skip unknown constraint
                while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
                    self.advance()

            self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.ParamConstraints(
            min_value=min_value,
            max_value=max_value,
            min_length=min_length,
            max_length=max_length,
            ordered=ordered,
            range=range_val,
            enum_values=enum_values,
            pattern=pattern,
        )

    def _parse_constraint_number(self) -> float:
        """Parse a number in a constraint value, handling decimals."""
        negative = False
        if self.match(TokenType.MINUS):
            self.advance()
            negative = True
        num_str = self.expect(TokenType.NUMBER).value
        if self.match(TokenType.DOT):
            self.advance()
            frac = self.expect(TokenType.NUMBER).value
            num_str = num_str + "." + frac
        val = float(num_str)
        return -val if negative else val
