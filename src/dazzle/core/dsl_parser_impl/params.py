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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from .. import ir
from ..lexer import TokenType
from .dispatch import KeywordParser, parse_block_with_dispatch


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

    def _parse_string_or_param(
        self, param_type: str = "str", default: Any = ""
    ) -> str | ir.ParamRef:
        """Parse a string literal or param("key") reference."""
        if self.match(TokenType.PARAM):
            self.advance()
            self.expect(TokenType.LPAREN)
            ref_key = self.expect(TokenType.STRING).value
            self.expect(TokenType.RPAREN)
            return ir.ParamRef(key=ref_key, param_type=param_type, default=default)
        return str(self.expect(TokenType.STRING).value)

    def _parse_int_or_param(self, default: int = 0) -> int | ir.ParamRef:
        """Parse an integer literal or param("key") reference."""
        if self.match(TokenType.PARAM):
            self.advance()
            self.expect(TokenType.LPAREN)
            ref_key = self.expect(TokenType.STRING).value
            self.expect(TokenType.RPAREN)
            return ir.ParamRef(key=ref_key, param_type="int", default=default)
        return int(self.expect(TokenType.NUMBER).value)

    def parse_param(self) -> ir.ParamSpec:
        """Parse a ``param <dotted.key> ["description"]:`` block.

        Refactored to dispatch-table style (follow-on to #1098). 1
        token-keyed (``scope``) + 5 IDENT-text-matched (``type``,
        ``default``, ``category``, ``sensitive``, ``constraints``) +
        a tolerant ``_skip_unknown_param_field`` on_unknown that
        consumes the unknown key + COLON + rest of the line + a
        ``_build_param`` builder.

        The ``param`` keyword is consumed by the top-level dispatcher
        before this method is called.

        Grammar::

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
        """
        key_parts = [self.expect_identifier_or_keyword().value]
        while self.match(TokenType.DOT):
            self.advance()
            key_parts.append(self.expect_identifier_or_keyword().value)
        key = ".".join(key_parts)

        description: str | None = None
        if self.match(TokenType.STRING):
            description = self.advance().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        state = _ParamState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_PARAM_KEYWORDS,
            ident_keywords=_PARAM_IDENT_KEYWORDS,
            state=state,
            on_unknown=_skip_unknown_param_field,
        )
        self.expect(TokenType.DEDENT)
        return _build_param(key, description, state)

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


# ============================================================ #
# parse_param — keyword-dispatch decomposition (#1098 template) #
# ============================================================ #
#
# The 116-line monolith was replaced (v0.70.28) with the dispatch
# pattern shipped in #1097. 1 token-keyed (``scope``) + 5
# IDENT-text-matched (``type``, ``default``, ``category``,
# ``sensitive``, ``constraints``) + a tolerant on_unknown that
# consumes the unknown key + colon + rest of line + a
# `_build_param` builder.


@dataclass
class _ParamState:
    """Accumulator for :meth:`ParamParserMixin.parse_param`."""

    param_type: str = "str"
    default: Any = None
    scope: Literal["system", "tenant", "user"] = "system"
    category: str | None = None
    sensitive: bool = False
    constraints: ir.ParamConstraints | None = None


# ---------- Token-keyed keyword parsers ---------- #


def _pa_kw_scope(parser: Any, state: _ParamState) -> None:
    """``scope: system|tenant|user`` — lexer-keyword form."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.scope = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


# ---------- IDENT-text-matched keyword parsers ---------- #


def _pa_kw_type(parser: Any, state: _ParamState) -> None:
    """``type: <type_expr>`` — type expression captured as raw string."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.param_type = parser._parse_param_type_expr()
    parser.skip_newlines()


def _pa_kw_default(parser: Any, state: _ParamState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.default = parser._parse_param_default_value()
    parser.skip_newlines()


def _pa_kw_category(parser: Any, state: _ParamState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.category = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _pa_kw_sensitive(parser: Any, state: _ParamState) -> None:
    """``sensitive: true|false`` — tolerant of any TRUE-typed token."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.sensitive = parser.current_token().type == TokenType.TRUE
    parser.advance()
    parser.skip_newlines()


def _pa_kw_constraints(parser: Any, state: _ParamState) -> None:
    """``constraints:`` — nested block delegating to the mixin helper."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    state.constraints = parser._parse_param_constraints()


# ---------- Dispatch tables + on_unknown + builder ---------- #


_PARAM_KEYWORDS: dict[TokenType, KeywordParser[_ParamState]] = {
    TokenType.SCOPE: _pa_kw_scope,
}


_PARAM_IDENT_KEYWORDS: dict[str, KeywordParser[_ParamState]] = {
    "type": _pa_kw_type,
    "default": _pa_kw_default,
    "category": _pa_kw_category,
    "sensitive": _pa_kw_sensitive,
    "constraints": _pa_kw_constraints,
}


def _skip_unknown_param_field(parser: Any) -> None:
    """Tolerate ``unknown: value`` lines — advance past key + COLON + value.

    Mirrors the legacy else branch: advance the unknown identifier, and if
    followed by a colon, consume the rest of the line until newline / dedent /
    EOF. Skip_newlines at the end re-syncs the loop.
    """
    parser.advance()
    if parser.match(TokenType.COLON):
        parser.advance()
        while not parser.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            parser.advance()
    parser.skip_newlines()


def _build_param(key: str, description: str | None, state: _ParamState) -> ir.ParamSpec:
    return ir.ParamSpec(
        key=key,
        param_type=state.param_type,
        default=state.default,
        scope=state.scope,
        description=description,
        category=state.category,
        sensitive=state.sensitive,
        constraints=state.constraints,
    )
