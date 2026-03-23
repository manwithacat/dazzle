"""
Feedback widget parser mixin for DAZZLE DSL.

Parses the ``feedback_widget`` top-level keyword.

DSL Syntax:

    feedback_widget: enabled
      position: bottom-right
      shortcut: backtick
      categories: [bug, ux, visual, behaviour, enhancement, other]
      severities: [blocker, annoying, minor]
      capture: [url, persona, viewport, user_agent, console_errors, nav_history, page_snapshot]

    feedback_widget: disabled
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class FeedbackWidgetParserMixin:
    """Parser mixin for feedback_widget blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any

    def parse_feedback_widget(self) -> ir.FeedbackWidgetSpec:
        """Parse a feedback_widget block."""
        # Expect 'enabled' or 'disabled' after colon
        self.expect(TokenType.COLON)
        value_token = self.expect_identifier_or_keyword()
        enabled = value_token.value == "enabled"

        self.skip_newlines()

        # Parse optional indented sub-keys
        position: str | None = None
        shortcut: str | None = None
        categories: list[str] | None = None
        severities: list[str] | None = None
        capture: list[str] | None = None

        if self.match(TokenType.INDENT):
            self.advance()
            while not self.match(TokenType.DEDENT, TokenType.EOF):
                self.skip_newlines()
                if self.match(TokenType.DEDENT, TokenType.EOF):
                    break

                token = self.current_token()
                if token.type == TokenType.IDENTIFIER:
                    key = token.value
                    self.advance()
                    self.expect(TokenType.COLON)

                    if key == "position":
                        position = self._parse_fw_string_value()
                    elif key == "shortcut":
                        shortcut = self._parse_fw_string_value()
                    elif key == "categories":
                        categories = self._parse_fw_list()
                    elif key == "severities":
                        severities = self._parse_fw_list()
                    elif key == "capture":
                        capture = self._parse_fw_list()
                    else:
                        # Skip unknown sub-keys
                        self._parse_fw_string_value()
                    self.skip_newlines()
                else:
                    self.advance()
                    self.skip_newlines()

            if self.match(TokenType.DEDENT):
                self.advance()

        kwargs: dict[str, Any] = {"enabled": enabled}
        if position is not None:
            kwargs["position"] = position
        if shortcut is not None:
            kwargs["shortcut"] = shortcut
        if categories is not None:
            kwargs["categories"] = categories
        if severities is not None:
            kwargs["severities"] = severities
        if capture is not None:
            kwargs["capture"] = capture

        return ir.FeedbackWidgetSpec(**kwargs)

    def _parse_fw_string_value(self) -> str:
        """Parse a single identifier/keyword value, including hyphenated forms like 'bottom-right'."""
        token = self.current_token()
        if token.type == TokenType.STRING:
            self.advance()
            return str(token.value)
        value = str(self.expect_identifier_or_keyword().value)
        # Handle hyphenated values (e.g. bottom-right, top-left)
        while self.match(TokenType.MINUS):
            self.advance()
            next_part = str(self.expect_identifier_or_keyword().value)
            value = f"{value}-{next_part}"
        return value

    def _parse_fw_list(self) -> list[str]:
        """Parse a bracket list: [item1, item2, ...].

        List items may be reserved keywords (e.g. ``persona``, ``url``),
        so we accept any non-structural token value.
        """
        items: list[str] = []
        if self.match(TokenType.LBRACKET):
            self.advance()
            while not self.match(TokenType.RBRACKET):
                token = self.current_token()
                # Accept identifiers and keywords alike
                value = token.value
                self.advance()
                # Handle underscored names tokenised as keywords
                items.append(str(value))
                if self.match(TokenType.COMMA):
                    self.advance()
            self.expect(TokenType.RBRACKET)
        else:
            token = self.current_token()
            items.append(str(token.value))
            self.advance()
        return items
