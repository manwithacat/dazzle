"""Parser mixin for `ingest name:` blocks (#1676)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class IngestParserMixin:
    """Parse ingest declarations."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        error: Any
        _parse_construct_header: Any

    def parse_ingest(self) -> ir.IngestSpec:
        """Parse ``ingest <name>:`` with entity / key / optional protect."""
        name, _title, _ = self._parse_construct_header(TokenType.INGEST, allow_keyword_name=True)

        entity = ""
        key: list[str] = []
        protect: ir.IngestProtectSpec | None = None

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()
            if tok.type == TokenType.ENTITY or tok.value == "entity":
                self.advance()
                self.expect(TokenType.COLON)
                entity = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            elif tok.type == TokenType.KEY or tok.value == "key":
                self.advance()
                self.expect(TokenType.COLON)
                key = self._parse_ingest_key_list()
                self.skip_newlines()
            elif tok.type == TokenType.PROTECT or tok.value == "protect":
                self.advance()
                self.expect(TokenType.COLON)
                protect = self._parse_ingest_protect()
                self.skip_newlines()
            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        if not entity:
            self.error("ingest requires entity:")
        if not key:
            self.error("ingest requires key: [field, ...]")

        return ir.IngestSpec(name=name, entity=entity, key=tuple(key), protect=protect)

    def _parse_ingest_key_list(self) -> list[str]:
        fields: list[str] = []
        if self.match(TokenType.LBRACKET):
            self.advance()
            while not self.match(TokenType.RBRACKET, TokenType.EOF):
                fields.append(self.expect_identifier_or_keyword().value)
                if self.match(TokenType.COMMA):
                    self.advance()
            self.expect(TokenType.RBRACKET)
            return fields
        fields.append(self.expect_identifier_or_keyword().value)
        while self.match(TokenType.COMMA):
            self.advance()
            fields.append(self.expect_identifier_or_keyword().value)
        return fields

    def _parse_ingest_protect(self) -> ir.IngestProtectSpec:
        field = self.expect_identifier_or_keyword().value
        self.expect(TokenType.EQUALS)
        if self.match(TokenType.STRING):
            value = str(self.advance().value)
        else:
            value = self.expect_identifier_or_keyword().value
        return ir.IngestProtectSpec(field=field, value=value)
