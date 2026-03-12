"""
Question parser mixin for DAZZLE DSL.

Parses question blocks with blocks, raised_by, status, and resolution fields.

DSL Syntax (v0.41.0):
    question Q-001 "Which approval workflow applies to high-value invoices?":
      blocks: [RULE-A-002, ST-014]
      raised_by: reviewer
      status: open
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class QuestionParserMixin:
    """Parser mixin for question blocks."""

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

    def parse_question(self) -> ir.QuestionSpec:
        """
        Parse a question block.

        Grammar:
            question QUESTION_ID STRING COLON NEWLINE INDENT
              [blocks COLON LBRACKET id_list RBRACKET NEWLINE]
              [raised_by COLON IDENTIFIER NEWLINE]
              [status COLON IDENTIFIER NEWLINE]
              [resolution COLON text NEWLINE]
            DEDENT

        Returns:
            QuestionSpec with parsed values
        """
        loc = self._source_location()
        question_id = self._parse_compound_id()
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
        blocks: list[str] = []
        raised_by: str | None = None
        status: ir.QuestionStatus | None = None
        resolution: str | None = None

        # Parse question fields
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()
            field_name = token.value

            if field_name == "blocks":
                self.advance()
                self.expect(TokenType.COLON)
                blocks = self._parse_question_id_list()
                self.skip_newlines()

            elif field_name == "raised_by":
                self.advance()
                self.expect(TokenType.COLON)
                raised_by = self.advance().value
                self.skip_newlines()

            elif field_name == "status":
                self.advance()
                self.expect(TokenType.COLON)
                status_str = self.advance().value
                status = self._parse_question_status(status_str)
                self.skip_newlines()

            elif field_name == "resolution":
                self.advance()
                self.expect(TokenType.COLON)
                resolution = self._parse_question_text()
                self.skip_newlines()

            else:
                # Skip unknown field
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    self._skip_question_field()

        self.expect(TokenType.DEDENT)

        return ir.QuestionSpec(
            question_id=question_id,
            title=title,
            description=description,
            blocks=blocks,
            raised_by=raised_by,
            status=status or ir.QuestionStatus.OPEN,
            resolution=resolution,
            source=loc,
        )

    def _parse_question_id_list(self) -> list[str]:
        """Parse a bracketed list of compound IDs: [RULE-A-002, ST-014]."""
        items: list[str] = []
        self.expect(TokenType.LBRACKET)

        while not self.match(TokenType.RBRACKET):
            self.skip_newlines()
            if self.match(TokenType.RBRACKET):
                break

            # Compound IDs can contain hyphens (RULE-A-002, ST-014)
            parts: list[str] = []
            while not self.match(
                TokenType.COMMA, TokenType.RBRACKET, TokenType.NEWLINE, TokenType.EOF
            ):
                token = self.current_token()
                parts.append(token.value)
                self.advance()
            if parts:
                items.append("".join(parts))

            if self.match(TokenType.COMMA):
                self.advance()
            else:
                break

        self.expect(TokenType.RBRACKET)
        return items

    def _parse_question_text(self) -> str:
        """Parse text until end of line — supports quoted or unquoted."""
        if self.match(TokenType.STRING):
            return str(self.advance().value)

        parts: list[str] = []
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            token = self.current_token()
            parts.append(token.value)
            self.advance()
        return " ".join(parts)

    def _parse_question_status(self, status_str: str) -> ir.QuestionStatus:
        """Parse status string to QuestionStatus enum."""
        status_map = {
            "open": ir.QuestionStatus.OPEN,
            "resolved": ir.QuestionStatus.RESOLVED,
            "deferred": ir.QuestionStatus.DEFERRED,
        }
        if status_str in status_map:
            return status_map[status_str]

        from ..errors import make_parse_error

        valid = ", ".join(status_map.keys())
        raise make_parse_error(
            f"Invalid question status '{status_str}'. Valid statuses: {valid}",
            self.file,
            self.current_token().line,
            self.current_token().column,
        )

    def _skip_question_field(self) -> None:
        """Skip tokens until we reach the next field or end of block."""
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            if self.match(TokenType.NEWLINE):
                self.skip_newlines()
                break
            self.advance()
