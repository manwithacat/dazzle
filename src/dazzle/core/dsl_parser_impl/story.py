"""
Story parser mixin for DAZZLE DSL.

Parses story blocks with Gherkin-style given/when/then/unless conditions.

DSL Syntax (v0.22.0; persona/entities vocabulary #1559):
    story ST-001 "Staff sends invoice to client":
      persona: StaffUser
      trigger: status_changed
      entities: [Invoice, Client]

      given:
        - Invoice.status is 'draft'
        - Client.email is set

      when:
        - Invoice.status changes to 'sent'

      then:
        - Invoice email is sent to Client.email
        - Invoice.sent_at is recorded

      unless:
        - Client.email is missing:
            then: FollowupTask is created
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..ir.location import SourceLocation
from ..lexer import TokenType
from .dispatch import KeywordParser, parse_block_with_dispatch


class StoryParserMixin:
    """Parser mixin for story blocks."""

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

    def _parse_compound_id(self) -> str:
        """
        Parse a compound ID like ST-001 or STORY_42.

        Reads tokens until we hit a STRING token (the title).
        Handles IDs with hyphens by concatenating IDENTIFIER-NUMBER patterns.
        """
        parts: list[str] = []

        while not self.match(TokenType.STRING, TokenType.COLON, TokenType.NEWLINE, TokenType.EOF):
            token = self.current_token()
            parts.append(token.value)
            self.advance()

        return "".join(parts)

    def parse_story(self) -> ir.StorySpec:
        """Parse a ``story <ID> "Title":`` block.

        Refactored to dispatch-table style (follow-on to #1098). 7
        token-keyed `_s_kw_*` parsers (status/persona/trigger/given/
        when/then/unless) + an `entities` ident-keyword + a
        `_skip_unknown_story_field` on_unknown + a `_build_story`
        builder enforcing the required persona + trigger.

        Grammar::

            story STORY_ID STRING COLON NEWLINE INDENT
              [persona COLON IDENTIFIER NEWLINE]
              [trigger COLON IDENTIFIER NEWLINE]
              [entities COLON LBRACKET identifier_list RBRACKET NEWLINE]
              [given COLON NEWLINE INDENT condition_list DEDENT]
              [when COLON NEWLINE INDENT condition_list DEDENT]
              [then COLON NEWLINE INDENT condition_list DEDENT]
              [unless COLON NEWLINE INDENT unless_list DEDENT]
            DEDENT
        """
        loc = self._source_location()
        story_id = self._parse_compound_id()
        title = self.expect(TokenType.STRING).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Optional docstring-style description before the field dispatch.
        description: str | None = None
        if self.match(TokenType.STRING):
            description = self.advance().value
            self.skip_newlines()

        state = _StoryState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_STORY_KEYWORDS,
            ident_keywords=_STORY_IDENT_KEYWORDS,
            state=state,
            on_unknown=_skip_unknown_story_field,
        )
        self.expect(TokenType.DEDENT)
        return _build_story(self, story_id, title, description, loc, state)

    def _parse_story_trigger(self, trigger_str: str) -> ir.StoryTrigger:
        """Parse trigger string to StoryTrigger enum."""
        trigger_map = {
            "form_submitted": ir.StoryTrigger.FORM_SUBMITTED,
            "status_changed": ir.StoryTrigger.STATUS_CHANGED,
            "timer_elapsed": ir.StoryTrigger.TIMER_ELAPSED,
            "external_event": ir.StoryTrigger.EXTERNAL_EVENT,
            "user_click": ir.StoryTrigger.USER_CLICK,
            "cron_daily": ir.StoryTrigger.CRON_DAILY,
            "cron_hourly": ir.StoryTrigger.CRON_HOURLY,
        }

        if trigger_str in trigger_map:
            return trigger_map[trigger_str]

        from ..errors import make_parse_error

        valid_triggers = ", ".join(trigger_map.keys())
        raise make_parse_error(
            f"Invalid story trigger '{trigger_str}'. Valid triggers: {valid_triggers}",
            self.file,
            self.current_token().line,
            self.current_token().column,
        )

    def _parse_story_status(self, status_str: str) -> ir.StoryStatus:
        """Parse status string to StoryStatus enum."""
        status_map = {
            "draft": ir.StoryStatus.DRAFT,
            "accepted": ir.StoryStatus.ACCEPTED,
            "rejected": ir.StoryStatus.REJECTED,
        }

        if status_str in status_map:
            return status_map[status_str]

        from ..errors import make_parse_error

        valid_statuses = ", ".join(status_map.keys())
        raise make_parse_error(
            f"Invalid story status '{status_str}'. Valid statuses: {valid_statuses}",
            self.file,
            self.current_token().line,
            self.current_token().column,
        )

    def _parse_identifier_list(self) -> list[str]:
        """Parse a bracketed list of identifiers: [A, B, C]."""
        items: list[str] = []

        self.expect(TokenType.LBRACKET)

        while not self.match(TokenType.RBRACKET):
            self.skip_newlines()
            if self.match(TokenType.RBRACKET):
                break

            item = self.expect_identifier_or_keyword().value
            items.append(item)

            if self.match(TokenType.COMMA):
                self.advance()
            else:
                break

        self.expect(TokenType.RBRACKET)
        return items

    def _parse_condition_list(self) -> list[ir.StoryCondition]:
        """
        Parse a list of conditions (given/when/then).

        Grammar:
            INDENT
              (MINUS STRING NEWLINE)*
            DEDENT

        Returns:
            List of StoryCondition objects
        """
        from .. import ir

        conditions: list[ir.StoryCondition] = []

        if not self.match(TokenType.INDENT):
            return conditions

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Expect - "condition text"
            if self.match(TokenType.MINUS):
                self.advance()

                # Read condition text - can be string or identifier sequence
                expression = self._parse_condition_expression()

                # Try to extract field path from expression
                field_path = self._extract_field_path(expression)

                conditions.append(
                    ir.StoryCondition(
                        expression=expression,
                        field_path=field_path,
                    )
                )
                self.skip_newlines()
            else:
                # Skip unexpected token
                self.advance()

        self.expect(TokenType.DEDENT)
        return conditions

    def _parse_condition_expression(self) -> str:
        """
        Parse a condition expression until end of line.

        Can be a quoted string or a sequence of tokens forming an expression.
        """
        if self.match(TokenType.STRING):
            return str(self.advance().value)

        # Read tokens until newline/dedent, forming an expression
        parts: list[str] = []
        while not self.match(TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            token = self.current_token()
            parts.append(token.value)
            self.advance()

        return " ".join(parts)

    def _extract_field_path(self, expression: str) -> str | None:
        """
        Try to extract Entity.field path from expression.

        Examples:
            "Invoice.status is 'draft'" -> "Invoice.status"
            "User submits form" -> None
        """
        from ._lexical import extract_entity_field_prefix

        return extract_entity_field_prefix(expression)

    def _parse_unless_list(self) -> list[ir.StoryException]:
        """
        Parse a list of unless branches.

        Grammar:
            INDENT
              (MINUS condition_text COLON NEWLINE INDENT
                 then COLON outcome_text NEWLINE
               DEDENT)*
            DEDENT

        Returns:
            List of StoryException objects
        """
        from .. import ir

        exceptions: list[ir.StoryException] = []

        if not self.match(TokenType.INDENT):
            return exceptions

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Expect - "condition":
            if self.match(TokenType.MINUS):
                self.advance()

                # Read condition until colon
                condition = self._parse_condition_expression_until_colon()

                self.expect(TokenType.COLON)
                self.skip_newlines()

                # Parse then outcomes
                then_outcomes: list[str] = []

                if self.match(TokenType.INDENT):
                    self.expect(TokenType.INDENT)

                    while not self.match(TokenType.DEDENT):
                        self.skip_newlines()
                        if self.match(TokenType.DEDENT):
                            break

                        if self.match(TokenType.THEN):
                            self.advance()
                            self.expect(TokenType.COLON)
                            outcome = self._parse_condition_expression()
                            then_outcomes.append(outcome)
                            self.skip_newlines()
                        else:
                            # Skip unexpected token
                            self.advance()

                    self.expect(TokenType.DEDENT)
                elif self.match(TokenType.THEN):
                    # Inline: then: outcome
                    self.advance()
                    self.expect(TokenType.COLON)
                    outcome = self._parse_condition_expression()
                    then_outcomes.append(outcome)
                    self.skip_newlines()

                exceptions.append(
                    ir.StoryException(
                        condition=condition,
                        then_outcomes=then_outcomes,
                    )
                )
            else:
                # Skip unexpected token
                self.advance()

        self.expect(TokenType.DEDENT)
        return exceptions

    def _parse_condition_expression_until_colon(self) -> str:
        """Parse expression until we hit a colon."""
        if self.match(TokenType.STRING):
            return str(self.advance().value)

        parts: list[str] = []
        while not self.match(TokenType.COLON, TokenType.NEWLINE, TokenType.DEDENT, TokenType.EOF):
            token = self.current_token()
            parts.append(token.value)
            self.advance()

        return " ".join(parts)

    def _skip_to_next_field(self) -> None:
        """Skip tokens until we reach the next field or end of block."""
        while not self.match(
            TokenType.STATUS,
            TokenType.PERSONA,
            TokenType.TRIGGER,
            TokenType.GIVEN,
            TokenType.WHEN,
            TokenType.THEN,
            TokenType.UNLESS,
            TokenType.DEDENT,
            TokenType.EOF,
        ):
            self.advance()
            self.skip_newlines()


# ============================================================ #
# parse_story — keyword-dispatch decomposition (#1098 template) #
# ============================================================ #
#
# The 141-line monolith was replaced (v0.70.22) with the dispatch
# pattern shipped in #1097. 7 token-keyed `_s_kw_*` + an `entities`
# ident-keyword + a custom on-unknown that tolerates ``unknown: value``
# patterns by skipping to the next field (and raises a #1559
# migration hint for the renamed `actor`/`scope`) + a `_build_story`
# builder enforcing the required `persona` and `trigger` fields.


@dataclass
class _StoryState:
    """Accumulator for :meth:`StoryParserMixin.parse_story`."""

    persona: str | None = None
    trigger: ir.StoryTrigger | None = None
    entities: list[str] = field(default_factory=list)
    status: ir.StoryStatus | None = None
    given: list[ir.StoryCondition] = field(default_factory=list)
    when: list[ir.StoryCondition] = field(default_factory=list)
    then: list[ir.StoryCondition] = field(default_factory=list)
    unless: list[ir.StoryException] = field(default_factory=list)


# ---------- Keyword parsers ---------- #


def _s_kw_status(parser: Any, state: _StoryState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    status_str = parser.expect_identifier_or_keyword().value
    state.status = parser._parse_story_status(status_str)
    parser.skip_newlines()


def _s_kw_persona(parser: Any, state: _StoryState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.persona = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _s_kw_trigger(parser: Any, state: _StoryState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    trigger_str = parser.expect_identifier_or_keyword().value
    state.trigger = parser._parse_story_trigger(trigger_str)
    parser.skip_newlines()


def _s_kw_entities(parser: Any, state: _StoryState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.entities = parser._parse_identifier_list()
    parser.skip_newlines()


def _s_kw_given(parser: Any, state: _StoryState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    state.given = parser._parse_condition_list()


def _s_kw_when(parser: Any, state: _StoryState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    state.when = parser._parse_condition_list()


def _s_kw_then(parser: Any, state: _StoryState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    state.then = parser._parse_condition_list()


def _s_kw_unless(parser: Any, state: _StoryState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    state.unless = parser._parse_unless_list()


# ---------- Dispatch table + on_unknown + builder ---------- #


_STORY_KEYWORDS: dict[TokenType, KeywordParser[_StoryState]] = {
    TokenType.STATUS: _s_kw_status,
    TokenType.PERSONA: _s_kw_persona,
    TokenType.TRIGGER: _s_kw_trigger,
    TokenType.GIVEN: _s_kw_given,
    TokenType.WHEN: _s_kw_when,
    TokenType.THEN: _s_kw_then,
    TokenType.UNLESS: _s_kw_unless,
}

# `entities` is dispatched as a plain IDENTIFIER (not a reserved token) so
# the common word stays usable as a field/identifier elsewhere — e.g. the
# `entities: json` field in fixtures/pra. (#1559 vocabulary unification.)
_STORY_IDENT_KEYWORDS: dict[str, KeywordParser[_StoryState]] = {
    "entities": _s_kw_entities,
}


def _skip_unknown_story_field(parser: Any) -> None:
    """Tolerate ``unknown_field: value`` lines (mirrors legacy else branch).

    Advances past the unknown keyword, and if it's followed by a colon,
    delegates to the mixin's ``_skip_to_next_field`` helper to skip the
    value as well. Without this, the dispatch helper's default
    ``Unknown keyword`` raise would break forward-compat parsing.

    #1559 footgun guard: the `actor` / `scope` keywords were renamed to
    `persona` / `entities`. An unmigrated `actor:`/`scope:` would otherwise
    be silently swallowed here (then surface as a misleading "missing
    required 'persona' field" further on), so raise an actionable hint.
    """
    tok = parser.current_token()
    _RENAMED = {"actor": "persona", "scope": "entities"}
    new_kw = _RENAMED.get(str(tok.value))
    if new_kw is not None:
        raise make_parse_error(
            f"`{tok.value}` is not a valid story field. #1559 renamed "
            f"`{tok.value}:` → `{new_kw}:` in story blocks. Run:\n"
            f"  sed -i '' -E 's/^([[:space:]]+){tok.value}:/\\1{new_kw}:/' <dsl-file>",
            parser.file,
            tok.line,
            tok.column,
        )
    parser.advance()
    if parser.match(TokenType.COLON):
        parser.advance()
        parser._skip_to_next_field()


def _build_story(
    parser: Any,
    story_id: str,
    title: str,
    description: str | None,
    loc: SourceLocation,
    state: _StoryState,
) -> ir.StorySpec:
    """Enforce required persona + trigger, then assemble the frozen IR."""
    if state.persona is None:
        tok = parser.current_token()
        raise make_parse_error(
            "Story missing required 'persona' field",
            parser.file,
            tok.line,
            tok.column,
        )

    if state.trigger is None:
        tok = parser.current_token()
        raise make_parse_error(
            "Story missing required 'trigger' field",
            parser.file,
            tok.line,
            tok.column,
        )

    return ir.StorySpec(
        story_id=story_id,
        title=title,
        description=description,
        persona=state.persona,
        trigger=state.trigger,
        entities=state.entities,
        status=state.status or ir.StoryStatus.DRAFT,
        given=state.given,
        when=state.when,
        then=state.then,
        unless=state.unless,
        source=loc,
    )
