"""Full-text search parser mixin (#954 cycle 1).

Parses ``search on <Entity>: ...`` blocks. Cycle 2 adds the
Alembic migration for the GIN index; cycle 3 wires the search
endpoint; cycle 4 the search-box region.

DSL shape::

    search on Manuscript:
      fields: title, content, author.name
      ranking:
        title: 4
        content: 1
      highlight: true
      tokenizer: english
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class SearchParserMixin:
    """Parser mixin for ``search`` blocks (#954)."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any

    def parse_search(self) -> ir.SearchSpec:
        """Parse `search on <Entity>: ...`."""
        self.expect(TokenType.SEARCH)
        self.expect(TokenType.ON)
        entity = self.expect_identifier_or_keyword().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        field_paths: list[str] = []
        ranking: dict[str, int] = {}
        highlight = False
        tokenizer = "english"

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            if self.match(TokenType.FIELDS):
                self.advance()
                self.expect(TokenType.COLON)
                field_paths = self._parse_search_field_paths()
                self.skip_newlines()

            elif self.match(TokenType.RANKING):
                self.advance()
                self.expect(TokenType.COLON)
                ranking = self._parse_search_ranking()

            elif self.match(TokenType.HIGHLIGHT):
                self.advance()
                self.expect(TokenType.COLON)
                highlight = self._parse_search_bool()
                self.skip_newlines()

            elif self.match(TokenType.TOKENIZER):
                self.advance()
                self.expect(TokenType.COLON)
                tok = self.expect_identifier_or_keyword()
                tokenizer = str(tok.value)
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        if not field_paths:
            tok = self.current_token()
            raise make_parse_error(
                f"Search '{entity}' requires at least one field in `fields:`.",
                self.file,
                tok.line,
                tok.column,
            )

        # Combine field paths + ranking weights into SearchField list.
        search_fields = [
            ir.SearchField(path=path, weight=ranking.get(path, 1)) for path in field_paths
        ]
        return ir.SearchSpec(
            entity=entity,
            fields=search_fields,
            highlight=highlight,
            tokenizer=tokenizer,
        )

    def _parse_search_field_paths(self) -> list[str]:
        """Parse ``title, content, author.name`` — comma-separated paths
        of identifiers + dots."""
        paths: list[str] = []
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            paths.append(self._parse_search_field_path())
            if self.match(TokenType.COMMA):
                self.advance()
            else:
                break
        return paths

    def _parse_search_field_path(self) -> str:
        """Parse a single ``a.b.c`` path."""
        parts: list[str] = [self.expect_identifier_or_keyword().value]
        while self.match(TokenType.DOT):
            self.advance()
            parts.append(self.expect_identifier_or_keyword().value)
        return ".".join(parts)

    def _parse_search_ranking(self) -> dict[str, int]:
        """Parse the ``ranking:`` block — indented ``field: weight`` pairs."""
        self.skip_newlines()
        if not self.match(TokenType.INDENT):
            return {}
        self.advance()  # consume INDENT
        weights: dict[str, int] = {}
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break
            path = self._parse_search_field_path()
            self.expect(TokenType.COLON)
            weight_tok = self.expect(TokenType.NUMBER)
            weight = int(weight_tok.value)
            if not 1 <= weight <= 4:
                raise make_parse_error(
                    f"Search ranking weight must be 1..4 (Postgres tsvector D..A); got {weight}.",
                    self.file,
                    weight_tok.line,
                    weight_tok.column,
                )
            weights[path] = weight
            self.skip_newlines()
        if self.match(TokenType.DEDENT):
            self.advance()
        return weights

    def _parse_search_bool(self) -> bool:
        """Parse a ``true``/``false`` literal."""
        tok = self.expect_identifier_or_keyword()
        value = str(tok.value).lower()
        if value == "true":
            return True
        if value == "false":
            return False
        raise make_parse_error(
            f"Expected `true` or `false`; got {tok.value!r}.",
            self.file,
            tok.line,
            tok.column,
        )
