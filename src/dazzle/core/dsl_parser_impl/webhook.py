"""
Webhook parser mixin for DAZZLE DSL.

Parses outbound HTTP notification definitions.

DSL Syntax (v0.25.0):

    webhook OrderNotification "Order Status Webhook":
      entity: Order
      events: [created, updated, deleted]
      url: config("ORDER_WEBHOOK_URL")
      auth:
        method: hmac_sha256
        secret: config("WEBHOOK_SECRET")
      payload:
        include: [id, status, total, customer.name]
        format: json
      retry:
        max_attempts: 3
        backoff: exponential
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..lexer import TokenType


class WebhookParserMixin:
    """Parser mixin for webhook blocks."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any

    def parse_webhook(self) -> ir.WebhookSpec:
        """Parse a webhook block."""
        self.expect(TokenType.WEBHOOK)
        name = self.expect_identifier_or_keyword().value

        title = None
        if self.match(TokenType.STRING):
            title = str(self.advance().value)

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        entity = ""
        events: list[ir.WebhookEvent] = []
        url = ""
        auth = None
        payload = None
        retry = None

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()

            if tok.value == "entity":
                self.advance()
                self.expect(TokenType.COLON)
                entity = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            elif tok.value == "events":
                self.advance()
                self.expect(TokenType.COLON)
                events = self._parse_webhook_events()
                self.skip_newlines()

            elif tok.value == "url":
                self.advance()
                self.expect(TokenType.COLON)
                url = self._parse_webhook_url()
                self.skip_newlines()

            elif tok.value == "auth":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                auth = self._parse_webhook_auth()
                self.skip_newlines()

            elif tok.value == "payload":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                payload = self._parse_webhook_payload()
                self.skip_newlines()

            elif tok.value == "retry":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                self.expect(TokenType.INDENT)
                retry = self._parse_webhook_retry()
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.WebhookSpec(
            name=name,
            title=title,
            entity=entity,
            events=events,
            url=url,
            auth=auth,
            payload=payload,
            retry=retry,
        )

    def _parse_webhook_events(self) -> list[ir.WebhookEvent]:
        """Parse bracketed event list: [created, updated, deleted]."""
        events: list[ir.WebhookEvent] = []
        self.expect(TokenType.LBRACKET)
        while not self.match(TokenType.RBRACKET, TokenType.EOF):
            token = self.expect_identifier_or_keyword()
            try:
                events.append(ir.WebhookEvent(token.value))
            except ValueError:
                pass
            if self.match(TokenType.COMMA):
                self.advance()
        if self.match(TokenType.RBRACKET):
            self.advance()
        return events

    def _parse_webhook_url(self) -> str:
        """Parse URL value: string literal or config("KEY") call."""
        if self.match(TokenType.STRING):
            return str(self.advance().value)
        elif self.match(TokenType.CONFIG):
            self.advance()
            self.expect(TokenType.LPAREN)
            value = self.expect(TokenType.STRING).value
            self.expect(TokenType.RPAREN)
            return f'config("{value}")'
        else:
            return str(self.expect_identifier_or_keyword().value)

    def _parse_webhook_auth(self) -> ir.WebhookAuthSpec:
        """Parse webhook auth block."""
        method = ir.WebhookAuthMethod.HMAC_SHA256
        secret_ref = None

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()
            if tok.value == "method":
                self.advance()
                self.expect(TokenType.COLON)
                method_str = self.expect_identifier_or_keyword().value
                try:
                    method = ir.WebhookAuthMethod(method_str)
                except ValueError:
                    pass
                self.skip_newlines()
            elif tok.value == "secret":
                self.advance()
                self.expect(TokenType.COLON)
                secret_ref = self._parse_webhook_url()
                self.skip_newlines()
            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.WebhookAuthSpec(method=method, secret_ref=secret_ref)

    def _parse_webhook_payload(self) -> ir.WebhookPayloadSpec:
        """Parse webhook payload block."""
        include_fields: list[str] = []
        fmt = "json"

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()
            if tok.value == "include":
                self.advance()
                self.expect(TokenType.COLON)
                include_fields = self._parse_webhook_dotted_list()
                self.skip_newlines()
            elif tok.value == "format":
                self.advance()
                self.expect(TokenType.COLON)
                fmt = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.WebhookPayloadSpec(include_fields=include_fields, format=fmt)

    def _parse_webhook_dotted_list(self) -> list[str]:
        """Parse bracketed list of possibly dotted identifiers."""
        items: list[str] = []
        self.expect(TokenType.LBRACKET)
        while not self.match(TokenType.RBRACKET, TokenType.EOF):
            parts = [self.expect_identifier_or_keyword().value]
            while self.match(TokenType.DOT):
                self.advance()
                parts.append(self.expect_identifier_or_keyword().value)
            items.append(".".join(parts))
            if self.match(TokenType.COMMA):
                self.advance()
        if self.match(TokenType.RBRACKET):
            self.advance()
        return items

    def _parse_webhook_retry(self) -> ir.WebhookRetrySpec:
        """Parse webhook retry block."""
        max_attempts = 3
        backoff = "exponential"

        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            tok = self.current_token()
            if tok.value == "max_attempts":
                self.advance()
                self.expect(TokenType.COLON)
                max_attempts = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()
            elif tok.value == "backoff":
                self.advance()
                self.expect(TokenType.COLON)
                backoff = self.expect_identifier_or_keyword().value
                self.skip_newlines()
            else:
                self.advance()
                self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.WebhookRetrySpec(max_attempts=max_attempts, backoff=backoff)
