"""Subprocessor parser mixin for DAZZLE DSL (v0.61.0).

Parses the ``subprocessor`` top-level construct.

DSL Syntax:

    subprocessor google_analytics "Google Analytics 4":
      handler: "Google LLC"
      handler_address: "1600 Amphitheatre Parkway, Mountain View, CA 94043, USA"
      jurisdiction: US
      data_categories: [pseudonymous_id, device_fingerprint, page_url]
      retention: "14 months"
      legal_basis: legitimate_interest
      consent_category: analytics
      dpa_url: "https://business.safety.google/adsprocessorterms/"
      scc_url: "https://business.safety.google/sccs/"
      cookies: [_ga, _ga_*, _gid]
      purpose: "Product and web usage analytics."

See docs/superpowers/specs/2026-04-24-analytics-privacy-design.md §2.3.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType

_SCALAR_KEYS = {
    "handler",
    "handler_address",
    "jurisdiction",
    "retention",
    "dpa_url",
    "scc_url",
    "purpose",
}
_LIST_KEYS = {"data_categories", "cookies"}
_ENUM_KEYS = {"legal_basis", "consent_category"}
_ALL_KEYS = _SCALAR_KEYS | _LIST_KEYS | _ENUM_KEYS


class SubprocessorParserMixin:
    """Parser mixin for `subprocessor` blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any

    def parse_subprocessor(self) -> ir.SubprocessorSpec:
        """Parse a single `subprocessor <name> "<label>":` block."""
        # We enter with SUBPROCESSOR as the current token.
        self.advance()  # consume 'subprocessor'

        name_tok = self.expect_identifier_or_keyword()
        name = str(name_tok.value)

        label_tok = self.current_token()
        if label_tok.type is not TokenType.STRING:
            raise make_parse_error(
                f"Expected quoted label after subprocessor name, got {label_tok.value!r}.",
                self.file,
                label_tok.line,
                label_tok.column,
            )
        label = str(label_tok.value)
        self.advance()

        self.expect(TokenType.COLON)
        self.skip_newlines()

        values: dict[str, Any] = {}

        if self.match(TokenType.INDENT):
            self.advance()
            while not self.match(TokenType.DEDENT, TokenType.EOF):
                self.skip_newlines()
                if self.match(TokenType.DEDENT, TokenType.EOF):
                    break

                key_tok = self.current_token()
                key = str(key_tok.value)
                if key not in _ALL_KEYS:
                    raise make_parse_error(
                        f"Unknown subprocessor key `{key}`. "
                        f"Valid keys: {', '.join(sorted(_ALL_KEYS))}.",
                        self.file,
                        key_tok.line,
                        key_tok.column,
                    )
                if key in values:
                    raise make_parse_error(
                        f"Duplicate subprocessor key `{key}`.",
                        self.file,
                        key_tok.line,
                        key_tok.column,
                    )
                self.advance()
                self.expect(TokenType.COLON)

                if key in _LIST_KEYS:
                    values[key] = self._sp_parse_list(key, key_tok.line, key_tok.column)
                elif key in _ENUM_KEYS:
                    values[key] = self._sp_parse_enum(key, key_tok.line, key_tok.column)
                else:
                    values[key] = self._sp_parse_scalar()

                self.skip_newlines()

            if self.match(TokenType.DEDENT):
                self.advance()

        required = {"handler", "jurisdiction", "retention", "legal_basis", "consent_category"}
        missing = required - values.keys()
        if missing:
            raise make_parse_error(
                f"subprocessor `{name}` missing required key(s): {', '.join(sorted(missing))}.",
                self.file,
                name_tok.line,
                name_tok.column,
            )

        try:
            spec = ir.SubprocessorSpec(name=name, label=label, **values)
        except Exception as exc:
            raise make_parse_error(
                f"Invalid subprocessor `{name}`: {exc}",
                self.file,
                name_tok.line,
                name_tok.column,
            ) from exc

        return spec

    def _sp_parse_scalar(self) -> str:
        """Parse a string value — accepts quoted string or bare identifier/keyword."""
        tok = self.current_token()
        if tok.type is TokenType.STRING:
            self.advance()
            return str(tok.value)
        value = str(self.expect_identifier_or_keyword().value)
        return value

    def _sp_parse_list(self, key: str, line: int, column: int) -> list[str]:
        """Parse a bracket list of identifiers/strings/wildcard patterns.

        For `data_categories`, validate each value against the DataCategory enum.
        """
        items: list[str] = []
        if not self.match(TokenType.LBRACKET):
            # Permit single bare identifier as a one-element list
            tok = self.current_token()
            self.advance()
            items = [str(tok.value)]
        else:
            self.advance()  # consume '['
            while not self.match(TokenType.RBRACKET):
                tok = self.current_token()
                # Cookie names like `_ga_*` tokenise as IDENTIFIER + STAR; stitch them.
                value = str(tok.value)
                self.advance()
                while self.match(TokenType.STAR):
                    self.advance()
                    value = f"{value}*"
                items.append(value)
                if self.match(TokenType.COMMA):
                    self.advance()
            self.expect(TokenType.RBRACKET)

        if key == "data_categories":
            valid = {c.value for c in ir.DataCategory}
            for item in items:
                if item not in valid:
                    raise make_parse_error(
                        f"Unknown data_category `{item}`. Valid values: {', '.join(sorted(valid))}.",
                        self.file,
                        line,
                        column,
                    )
        return items

    def _sp_parse_enum(self, key: str, line: int, column: int) -> str:
        """Parse an enum value with explicit vocabulary validation."""
        tok = self.current_token()
        if tok.type is TokenType.STRING:
            self.advance()
            value = str(tok.value)
        else:
            value = str(tok.value)
            self.advance()

        if key == "legal_basis":
            valid = {b.value for b in ir.LegalBasis}
            if value not in valid:
                raise make_parse_error(
                    f"Unknown legal_basis `{value}`. Valid values: {', '.join(sorted(valid))}.",
                    self.file,
                    line,
                    column,
                )
        elif key == "consent_category":
            valid = {c.value for c in ir.ConsentCategory}
            if value not in valid:
                raise make_parse_error(
                    f"Unknown consent_category `{value}`. Valid values: {', '.join(sorted(valid))}.",
                    self.file,
                    line,
                    column,
                )
        return value
