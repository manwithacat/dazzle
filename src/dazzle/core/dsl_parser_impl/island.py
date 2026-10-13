"""
Island parser mixin for DAZZLE DSL.

Parses UI island component definitions.

DSL Syntax:

    island task_chart "Task Progress Chart":
      entity: Task
      src: "islands/task-chart/index.js"
      fallback: "Loading task chart..."
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class IslandParserMixin:
    """Parser mixin for island blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any
        _parse_construct_header: Any

    def parse_island(self) -> ir.IslandSpec:
        """Parse an island block."""
        name, title, _ = self._parse_construct_header(TokenType.ISLAND, allow_keyword_name=True)

        entity = None
        src = None
        fallback = None

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()

            if tok.value == "entity":
                self.advance()
                self.expect(TokenType.COLON)
                entity = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif tok.value == "src":
                self.advance()
                self.expect(TokenType.COLON)
                src = str(self.expect(TokenType.STRING).value)
                self.skip_newlines()

            elif tok.value == "fallback":
                self.advance()
                self.expect(TokenType.COLON)
                fallback = str(self.expect(TokenType.STRING).value)
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.IslandSpec(
            name=name,
            title=title,
            entity=entity,
            src=src,
            fallback=fallback,
        )
