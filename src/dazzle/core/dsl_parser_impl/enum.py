"""
Enum parser mixin for DAZZLE DSL.

Parses shared enum definitions.

DSL Syntax (v0.25.0):

    enum OrderStatus "Order Status":
      draft "Draft"
      pending_review "Pending Review"
      approved "Approved"
      rejected "Rejected"
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class EnumParserMixin:
    """Parser mixin for shared enum blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any

    def parse_enum(self) -> ir.EnumSpec:
        """
        Parse a shared enum block.

        Grammar:
            enum IDENTIFIER STRING? COLON NEWLINE INDENT
              (IDENTIFIER STRING? NEWLINE)*
            DEDENT

        Returns:
            EnumSpec with parsed values
        """
        name, title, _ = self._parse_construct_header(TokenType.ENUM, allow_keyword_name=True)

        values: list[ir.EnumValueSpec] = []
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            value_name = self.expect_identifier_or_keyword().value

            value_title = None
            if self.match(TokenType.STRING):
                value_title = str(self.advance().value)

            values.append(ir.EnumValueSpec(name=value_name, title=value_title))
            self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.EnumSpec(name=name, title=title, values=values)
