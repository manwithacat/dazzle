"""Audit-trail parser mixin (#956 cycle 1).

Parses ``audit on <Entity>: ...`` blocks. Captures the declaration
only; cycle 2-6 wires runtime (auto-generated AuditEntry, repository
hooks, history region rendering, RBAC, retention sweep).

DSL shape::

    audit on Manuscript:
      track: status, source_pdf, marking_result
      show_to: persona(teacher, admin)
      retention: 90d
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class AuditParserMixin:
    """Parser mixin for ``audit`` blocks (#956)."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any

    def parse_audit(self) -> ir.AuditSpec:
        """Parse `audit on <Entity>: ...`."""
        self.expect(TokenType.AUDIT)
        self.expect(TokenType.ON)
        entity = self.expect_identifier_or_keyword().value

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        track: list[str] = []
        show_to = ir.AuditShowTo()
        retention_days = 0

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()

            # track: f1, f2, f3
            if tok.type == TokenType.IDENTIFIER and tok.value == "track":
                self.advance()
                self.expect(TokenType.COLON)
                track = self._parse_audit_track()
                self.skip_newlines()

            # show_to: persona(name1, name2)
            elif tok.type == TokenType.IDENTIFIER and tok.value == "show_to":
                self.advance()
                self.expect(TokenType.COLON)
                show_to = self._parse_audit_show_to()
                self.skip_newlines()

            # retention: 90d / 30d / 0
            elif self.match(TokenType.RETENTION):
                self.advance()
                self.expect(TokenType.COLON)
                retention_days = self._parse_audit_retention_days()
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.AuditSpec(
            entity=entity,
            track=track,
            show_to=show_to,
            retention_days=retention_days,
        )

    def _parse_audit_track(self) -> list[str]:
        """Parse comma-separated field names: ``status, source_pdf, x``."""
        names: list[str] = []
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            names.append(self.expect_identifier_or_keyword().value)
            if self.match(TokenType.COMMA):
                self.advance()
            else:
                break
        return names

    def _parse_audit_show_to(self) -> ir.AuditShowTo:
        """Parse ``persona(name1, name2)``. Cycle 1 only supports the
        persona kind; cycle 5 will expand to role / all.

        ``persona`` is a reserved keyword (PERSONA token), not in the
        keyword-as-identifier allow-list, so we match its token type
        directly rather than going through ``expect_identifier_or_keyword``.
        """
        kind_tok = self.current_token()
        if kind_tok.type == TokenType.PERSONA:
            self.advance()
            kind = "persona"
        else:
            # Best-effort error path — accept identifier so we can produce
            # a better message than "expected PERSONA, got X".
            try:
                kind_tok = self.expect_identifier_or_keyword()
                kind = kind_tok.value
            except Exception:
                kind = ""
            raise make_parse_error(
                f"Unknown audit show_to kind {kind!r}; cycle 1 supports `persona(...)` only.",
                self.file,
                kind_tok.line,
                kind_tok.column,
            )
        self.expect(TokenType.LPAREN)
        personas: list[str] = []
        while not self.match(TokenType.RPAREN):
            personas.append(self.expect_identifier_or_keyword().value)
            if self.match(TokenType.COMMA):
                self.advance()
            else:
                break
        self.expect(TokenType.RPAREN)
        return ir.AuditShowTo(kind="persona", personas=personas)

    def _parse_audit_retention_days(self) -> int:
        """Parse ``90d`` / ``30d`` / ``0`` (no retention) into days.

        Hours/minutes are accepted but rounded down to whole days; cycle
        6's sweep job runs daily so sub-day retention is moot.
        """
        tok = self.current_token()
        if tok.type == TokenType.DURATION_LITERAL:
            self.advance()
            text = str(tok.value).strip()
            return _audit_duration_to_days(text, file=self.file, line=tok.line, column=tok.column)
        if tok.type == TokenType.NUMBER:
            self.advance()
            # Plain integer interpreted as days.
            return int(tok.value)
        raise make_parse_error(
            f"Expected duration (e.g. 90d) or integer days; got {tok.type.value}.",
            self.file,
            tok.line,
            tok.column,
        )


def _audit_duration_to_days(text: str, *, file: Any, line: int, column: int) -> int:
    """Convert ``90d`` / ``720h`` / ``0`` into a day count."""
    if not text:
        raise make_parse_error("Empty retention duration.", file, line, column)
    suffix = text[-1].lower()
    multipliers_seconds = {"s": 1, "m": 60, "h": 3600, "d": 86_400}
    if suffix not in multipliers_seconds:
        try:
            return int(text)
        except ValueError as exc:
            raise make_parse_error(
                f"Invalid retention duration {text!r}.", file, line, column
            ) from exc
    try:
        magnitude = int(text[:-1])
    except ValueError as exc:
        raise make_parse_error(f"Invalid retention duration {text!r}.", file, line, column) from exc
    seconds = magnitude * multipliers_seconds[suffix]
    return max(0, seconds // 86_400)
