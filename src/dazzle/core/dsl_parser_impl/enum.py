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
from ..errors import make_parse_error
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
        _parse_construct_header: Any

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
        # #1493: declared value->tone map from a `semantic:` line; applied to the
        # EnumValueSpecs after the block is parsed (the line may sit before or
        # after the values). Stored raw/lowercased — normalised+validated downstream.
        semantics: dict[str, str] = {}
        semantic_pos: tuple[int, int] | None = None  # line, col of the `semantic:` line
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()
            value_name = self.expect_identifier_or_keyword().value

            # `semantic: open=warning, done=positive` — a binding line, not a value.
            # Distinguished by the trailing COLON (enum values never carry one).
            if value_name == "semantic" and self.match(TokenType.COLON):
                self.advance()
                semantic_pos = (tok.line, tok.column)
                semantics.update(self._parse_semantic_map())
                self.skip_newlines()
                continue

            value_title = None
            if self.match(TokenType.STRING):
                value_title = str(self.advance().value)

            values.append(ir.EnumValueSpec(name=value_name, title=value_title))
            self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        if semantics:
            declared = {v.name for v in values}
            unknown = [k for k in semantics if k not in declared]
            if unknown:
                line, col = semantic_pos or (0, 0)
                raise make_parse_error(
                    f"E_SEMANTIC_VALUE_UNKNOWN: enum '{name}' `semantic:` line binds "
                    f"value(s) not declared in the enum: {', '.join(sorted(unknown))}. "
                    f"Declared values: {', '.join(sorted(declared))}.",
                    self.file,
                    line,
                    col,
                )
            values = [
                v.model_copy(update={"semantic": semantics[v.name]}) if v.name in semantics else v
                for v in values
            ]

        return ir.EnumSpec(name=name, title=title, values=values)

    def _parse_semantic_map(self) -> dict[str, str]:
        """Parse a `value=tone, value=tone, ...` map (the body of a `semantic:`
        line, after the colon). Returns raw/lowercased tones keyed by value name;
        the tone palette + value membership are checked by the validator (#1493).
        """
        pairs: dict[str, str] = {}
        while True:
            key = self.expect_identifier_or_keyword().value
            self.expect(TokenType.EQUALS)
            tone = self.expect_identifier_or_keyword().value
            pairs[key] = str(tone).lower()
            if self.match(TokenType.COMMA):
                self.advance()
                continue
            break
        return pairs
