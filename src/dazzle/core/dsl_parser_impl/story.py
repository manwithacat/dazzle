"""
Story parser mixin for DAZZLE DSL.

Parses story blocks with Gherkin-style given/when/then/unless conditions.

DSL Syntax (v0.22.0):
    story ST-001 "Staff sends invoice to client":
      actor: StaffUser
      trigger: status_changed
      scope: [Invoice, Client]

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

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


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
        """
        Parse a story block.

        Grammar:
            story STORY_ID STRING COLON NEWLINE INDENT
              actor COLON IDENTIFIER NEWLINE
              trigger COLON IDENTIFIER NEWLINE
              [scope COLON LBRACKET identifier_list RBRACKET NEWLINE]
              [given COLON NEWLINE INDENT condition_list DEDENT]
              [when COLON NEWLINE INDENT condition_list DEDENT]
              [then COLON NEWLINE INDENT condition_list DEDENT]
              [unless COLON NEWLINE INDENT unless_list DEDENT]
            DEDENT

        Returns:
            StorySpec with parsed values
        """
        # story ST-001 "Title":
        # Story ID can be compound like ST-001, so read tokens until we hit STRING
        story_id = self._parse_compound_id()
        title = self.expect(TokenType.STRING).value
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        # Parse description if present (docstring-style)
        description = None
        if self.match(TokenType.STRING):
            description = self.advance().value
            self.skip_newlines()

        # Initialize fields
        actor = None
        trigger = None
        scope: list[str] = []
        given: list[ir.StoryCondition] = []
        when: list[ir.StoryCondition] = []
        then: list[ir.StoryCondition] = []
        unless: list[ir.StoryException] = []

        # Parse story fields
        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.ACTOR):
                self.advance()
                self.expect(TokenType.COLON)
                actor = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif self.match(TokenType.TRIGGER):
                self.advance()
                self.expect(TokenType.COLON)
                trigger_str = self.expect_identifier_or_keyword().value
                trigger = self._parse_story_trigger(trigger_str)
                self.skip_newlines()

            elif self.match(TokenType.SCOPE):
                self.advance()
                self.expect(TokenType.COLON)
                scope = self._parse_identifier_list()
                self.skip_newlines()

            elif self.match(TokenType.GIVEN):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                given = self._parse_condition_list()

            elif self.match(TokenType.WHEN):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                when = self._parse_condition_list()

            elif self.match(TokenType.THEN):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                then = self._parse_condition_list()

            elif self.match(TokenType.UNLESS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                unless = self._parse_unless_list()

            else:
                # Skip unknown field
                self.advance()
                if self.match(TokenType.COLON):
                    self.advance()
                    self._skip_to_next_field()

        self.expect(TokenType.DEDENT)

        if actor is None:
            from ..errors import make_parse_error

            raise make_parse_error(
                "Story missing required 'actor' field",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )

        if trigger is None:
            from ..errors import make_parse_error

            raise make_parse_error(
                "Story missing required 'trigger' field",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )

        return ir.StorySpec(
            story_id=story_id,
            title=title,
            description=description,
            actor=actor,
            trigger=trigger,
            scope=scope,
            given=given,
            when=when,
            then=then,
            unless=unless,
        )

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
        # Simple pattern: look for Entity.field at start
        import re

        match = re.match(r"([A-Z][a-zA-Z0-9_]*\.[a-z][a-zA-Z0-9_]*)", expression)
        if match:
            return match.group(1)
        return None

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
            TokenType.ACTOR,
            TokenType.TRIGGER,
            TokenType.SCOPE,
            TokenType.GIVEN,
            TokenType.WHEN,
            TokenType.THEN,
            TokenType.UNLESS,
            TokenType.DEDENT,
            TokenType.EOF,
        ):
            self.advance()
            self.skip_newlines()
