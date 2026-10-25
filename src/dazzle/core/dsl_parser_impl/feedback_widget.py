"""
Feedback widget parser mixin for DAZZLE DSL.

Parses the ``feedback_widget`` top-level keyword.

DSL Syntax:

    feedback_widget: enabled
      position: bottom-right
      shortcut: backtick          # or none, ctrl+shift+f, f1, ...
      categories: [bug, ux, visual, behaviour, enhancement, other]
      severities: [blocker, annoying, minor]
      capture: [url, persona, viewport, user_agent, console_errors, nav_history, page_snapshot]
      review:                     # #1854: the review posture
        personas: [super_admin]   # required when review: is present
        shortcut: alt-shift-r     # default; none turns it off
        screenshot: off           # off | optional

    feedback_widget: disabled
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

from .. import ir
from ..errors import make_parse_error
from ..ir.feedback_widget import REVIEW_SCREENSHOT_POLICIES
from ..lexer import TokenType

_STRUCTURAL = frozenset(
    {
        TokenType.NEWLINE,
        TokenType.INDENT,
        TokenType.DEDENT,
        TokenType.EOF,
        TokenType.COLON,
        TokenType.LBRACKET,
        TokenType.RBRACKET,
        TokenType.COMMA,
    }
)


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
        _parse_warning: Any
        error: Any

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
        review: ir.FeedbackReviewSpec | None = None

        if self.match(TokenType.INDENT):
            self.advance()
            while not self.match(TokenType.DEDENT, TokenType.EOF):
                self.skip_newlines()
                if self.match(TokenType.DEDENT, TokenType.EOF):
                    break

                token = self.current_token()
                # Sub-keys may be lexed as keywords (`position` since #923,
                # `review` / `personas` / `screenshot` for #1854), so key on
                # the token's text rather than its type.
                key = str(token.value) if token.type not in _STRUCTURAL else ""
                if key:
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
                    elif key == "review":
                        review = self._parse_fw_review(token)
                    else:
                        # Skip unknown sub-keys
                        self._parse_fw_string_value()
                    self.skip_newlines()
                else:
                    self.advance()
                    self.skip_newlines()

            if self.match(TokenType.DEDENT):
                self.advance()

        if categories is not None and not categories:
            self.error("feedback_widget: `categories:` must list at least one value")
        if severities is not None and not severities:
            self.error("feedback_widget: `severities:` must list at least one value")

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
        if review is not None:
            kwargs["review"] = review

        return ir.FeedbackWidgetSpec(**kwargs)

    def _parse_fw_review(self, review_token: Any) -> ir.FeedbackReviewSpec:
        """Parse the ``review:`` block (#1854).

        ``personas:`` is required; ``shortcut:`` shares the ``shortcut:``
        grammar; ``screenshot:`` is ``off`` or ``optional``.
        """
        self.skip_newlines()
        personas: list[str] | None = None
        shortcut: str | None = None
        screenshot: str | None = None
        if self.match(TokenType.INDENT):
            self.advance()
            while not self.match(TokenType.DEDENT, TokenType.EOF):
                self.skip_newlines()
                if self.match(TokenType.DEDENT, TokenType.EOF):
                    break
                token = self.current_token()
                key = str(token.value) if token.type not in _STRUCTURAL else ""
                if not key:
                    self.advance()
                    self.skip_newlines()
                    continue
                self.advance()
                self.expect(TokenType.COLON)
                if key == "personas":
                    personas = self._parse_fw_list()
                elif key == "shortcut":
                    shortcut = self._parse_fw_string_value()
                elif key == "screenshot":
                    value_token = self.current_token()
                    screenshot = self._parse_fw_string_value()
                    if screenshot not in REVIEW_SCREENSHOT_POLICIES:
                        self._error_at(
                            value_token,
                            "feedback_widget review: `screenshot:` must be `off` or "
                            f"`optional`; got `{screenshot}`",
                        )
                else:
                    self._error_at(
                        token,
                        f"feedback_widget review: unknown key `{key}:` "
                        "(expected personas, shortcut or screenshot)",
                    )
                self.skip_newlines()
            if self.match(TokenType.DEDENT):
                self.advance()
        if not personas:
            self._error_at(
                review_token,
                "feedback_widget review: `personas:` is required "
                "(the personas that get the review posture)",
            )
        kwargs: dict[str, Any] = {"personas": personas}
        if shortcut is not None:
            kwargs["shortcut"] = shortcut
        if screenshot is not None:
            kwargs["screenshot"] = screenshot
        return ir.FeedbackReviewSpec(**kwargs)

    def _error_at(self, token: Any, message: str) -> NoReturn:
        """Raise a ParseError positioned at ``token`` (not the current one)."""
        raise make_parse_error(message, self.file, token.line, token.column)

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
