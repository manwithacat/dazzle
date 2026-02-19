"""
Notification parser mixin for DAZZLE DSL.

Parses in-app notification rules that fire on entity events.

DSL Syntax (v0.34.0):

    notification invoice_overdue "Invoice Overdue":
      on: Invoice.status -> overdue
      channels: [in_app, email]
      message: "Invoice {{title}} is overdue"
      recipients: role(accountant)
      preferences: opt_out

    notification task_assigned "Task Assigned":
      on: Task.assigned_to changed
      channels: [in_app, email, slack]
      message: "You have been assigned {{title}}"
      recipients: field(assigned_to)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class NotificationParserMixin:
    """Parser mixin for notification blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any

    def parse_notification(self) -> ir.NotificationSpec:
        """Parse a notification block."""
        self.expect(TokenType.NOTIFICATION)
        name = self.expect_identifier_or_keyword().value

        title = None
        if self.match(TokenType.STRING):
            title = str(self.advance().value)

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        trigger: ir.NotificationTrigger | None = None
        channels: list[ir.NotificationChannel] = [ir.NotificationChannel.IN_APP]
        message = ""
        recipients = ir.NotificationRecipient()
        preference = ir.NotificationPreference.OPT_OUT

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            # on: Entity.field -> value  OR  on: Entity.field changed  OR  on: Entity created
            if self.match(TokenType.ON):
                self.advance()
                self.expect(TokenType.COLON)
                trigger = self._parse_notification_trigger()
                self.skip_newlines()

            # channels: [in_app, email, sms, slack]
            elif self.match(TokenType.CHANNELS):
                self.advance()
                self.expect(TokenType.COLON)
                channels = self._parse_notification_channels()
                self.skip_newlines()

            # message: "..."
            elif self.match(TokenType.MESSAGE):
                self.advance()
                self.expect(TokenType.COLON)
                message = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # recipients: role(name) | field(name) | creator
            elif self.match(TokenType.IDENTIFIER) and self.current_token().value == "recipients":
                self.advance()
                self.expect(TokenType.COLON)
                recipients = self._parse_notification_recipients()
                self.skip_newlines()

            # preferences: opt_out | opt_in | mandatory
            elif self.match(TokenType.PREFERENCES):
                self.advance()
                self.expect(TokenType.COLON)
                pref_token = self.expect_identifier_or_keyword()
                preference = ir.NotificationPreference(pref_token.value)
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        if trigger is None:
            token = self.current_token()
            raise make_parse_error(
                f"Notification '{name}' requires an 'on:' trigger",
                self.file,
                token.line,
                token.column,
            )

        return ir.NotificationSpec(
            name=name,
            title=title,
            trigger=trigger,
            channels=channels,
            message=message,
            recipients=recipients,
            preference=preference,
        )

    def _parse_notification_trigger(self) -> ir.NotificationTrigger:
        """Parse trigger: Entity.field -> value or Entity.field changed or Entity created."""
        entity = self.expect_identifier_or_keyword().value
        field: str | None = None
        event = "created"
        to_value: str | None = None

        # Check for .field
        if self.match(TokenType.DOT):
            self.advance()
            field = self.expect_identifier_or_keyword().value

        # Check for -> value (status transition)
        if self.match(TokenType.ARROW):
            self.advance()
            to_value = self.expect_identifier_or_keyword().value
            event = "status_changed" if field == "status" else "field_changed"
        # Check for "changed" keyword
        elif self.match(TokenType.CHANGED):
            self.advance()
            event = "field_changed"
        # Check for explicit event keyword
        elif self.match(TokenType.IDENTIFIER):
            tok = self.current_token()
            if tok.value in ("created", "updated", "deleted"):
                event = tok.value
                self.advance()

        return ir.NotificationTrigger(
            entity=entity,
            event=event,
            field=field,
            to_value=to_value,
        )

    def _parse_notification_channels(self) -> list[ir.NotificationChannel]:
        """Parse channel list: [in_app, email, sms, slack]."""
        channels: list[ir.NotificationChannel] = []

        if self.match(TokenType.LBRACKET):
            self.advance()
            while not self.match(TokenType.RBRACKET):
                ch_token = self.expect_identifier_or_keyword()
                channels.append(ir.NotificationChannel(ch_token.value))
                if self.match(TokenType.COMMA):
                    self.advance()
            self.expect(TokenType.RBRACKET)
        else:
            ch_token = self.expect_identifier_or_keyword()
            channels.append(ir.NotificationChannel(ch_token.value))

        return channels

    def _parse_notification_recipients(self) -> ir.NotificationRecipient:
        """Parse recipients: role(name) | field(name) | creator."""
        token = self.current_token()

        # creator (no parens)
        if token.type == TokenType.IDENTIFIER and token.value == "creator":
            self.advance()
            return ir.NotificationRecipient(kind="creator", value="")

        # role(name) or field(name)
        kind = self.expect_identifier_or_keyword().value
        if kind not in ("role", "field"):
            raise make_parse_error(
                f"Expected 'role', 'field', or 'creator' for recipients, got '{kind}'",
                self.file,
                token.line,
                token.column,
            )
        self.expect(TokenType.LPAREN)
        value = self.expect_identifier_or_keyword().value
        self.expect(TokenType.RPAREN)

        return ir.NotificationRecipient(kind=kind, value=value)
