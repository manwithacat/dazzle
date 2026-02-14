"""
Island parser mixin for DAZZLE DSL.

Parses UI island component definitions.

DSL Syntax:

    island task_chart "Task Progress Chart":
      entity: Task
      src: "islands/task-chart/index.js"
      fallback: "Loading task chart..."
      prop chart_type: str = "bar"
      prop date_range: str = "30d"
      event chart_clicked:
        detail: [task_id, series]
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

    def parse_island(self) -> ir.IslandSpec:
        """Parse an island block."""
        self.expect(TokenType.ISLAND)
        name = self.expect_identifier_or_keyword().value

        title = None
        if self.match(TokenType.STRING):
            title = str(self.advance().value)

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        entity = None
        src = None
        fallback = None
        props: list[ir.IslandPropSpec] = []
        events: list[ir.IslandEventSpec] = []

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

            elif tok.value == "prop":
                self.advance()
                prop = self._parse_island_prop()
                props.append(prop)
                self.skip_newlines()

            elif tok.value == "event":
                self.advance()
                event = self._parse_island_event()
                events.append(event)
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
            props=props,
            events=events,
        )

    def _parse_island_prop(self) -> ir.IslandPropSpec:
        """Parse a prop declaration: prop name: type = default."""
        name = self.expect_identifier_or_keyword().value
        self.expect(TokenType.COLON)
        prop_type = self.expect_identifier_or_keyword().value

        default: str | int | float | bool | None = None
        if self.match(TokenType.EQUALS):
            self.advance()
            if self.match(TokenType.STRING):
                default = str(self.advance().value)
            elif self.match(TokenType.NUMBER):
                val = self.advance().value
                default = (
                    int(val)
                    if isinstance(val, int) or (isinstance(val, str) and "." not in val)
                    else float(val)
                )
            elif self.match(TokenType.TRUE):
                self.advance()
                default = True
            elif self.match(TokenType.FALSE):
                self.advance()
                default = False
            else:
                default = str(self.expect_identifier_or_keyword().value)

        return ir.IslandPropSpec(name=name, type=prop_type, default=default)

    def _parse_island_event(self) -> ir.IslandEventSpec:
        """Parse an event declaration with optional detail fields."""
        name = self.expect_identifier_or_keyword().value
        detail_fields: list[str] = []

        self.expect(TokenType.COLON)
        self.skip_newlines()

        # Check if there's an indented block with detail
        if self.match(TokenType.INDENT):
            self.advance()
            while not self.match(TokenType.DEDENT, TokenType.EOF):
                self.skip_newlines()
                if self.match(TokenType.DEDENT, TokenType.EOF):
                    break

                tok = self.current_token()
                if tok.value == "detail":
                    self.advance()
                    self.expect(TokenType.COLON)
                    detail_fields = self._parse_island_identifier_list()
                    self.skip_newlines()
                else:
                    self.advance()
                    self.skip_newlines()

            if self.match(TokenType.DEDENT):
                self.advance()

        return ir.IslandEventSpec(name=name, detail_fields=detail_fields)

    def _parse_island_identifier_list(self) -> list[str]:
        """Parse bracketed identifier list: [id1, id2, ...]."""
        items: list[str] = []
        self.expect(TokenType.LBRACKET)
        while not self.match(TokenType.RBRACKET, TokenType.EOF):
            items.append(self.expect_identifier_or_keyword().value)
            if self.match(TokenType.COMMA):
                self.advance()
        if self.match(TokenType.RBRACKET):
            self.advance()
        return items
