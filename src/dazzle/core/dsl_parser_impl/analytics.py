"""Analytics block parser mixin (v0.61.0 Phase 3).

Parses the `analytics:` top-level construct.

DSL Syntax:

    analytics:
      providers:
        gtm:
          id: "GTM-XXXXXX"
        plausible:
          domain: "example.com"
      consent:
        default_jurisdiction: EU

Only one `analytics:` block per module is supported. Provider names match
the framework registry (gtm, plausible, ...); unknown names are parser
errors. Per-provider parameters are validated against the registry's
`required_params` / `optional_params` declarations at link time.

See docs/superpowers/specs/2026-04-24-analytics-privacy-design.md §2.1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class AnalyticsParserMixin:
    """Parser mixin for the `analytics:` block."""

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        skip_newlines: Any
        expect_identifier_or_keyword: Any
        current_token: Any
        file: Any

    def parse_analytics(self) -> ir.AnalyticsSpec:
        """Parse a single analytics: block.

        Called with `analytics` as the current token.
        """
        self.advance()  # consume 'analytics'
        self.expect(TokenType.COLON)
        self.skip_newlines()

        providers: list[ir.AnalyticsProviderInstance] = []
        consent: ir.AnalyticsConsentSpec | None = None

        if not self.match(TokenType.INDENT):
            return ir.AnalyticsSpec()

        self.advance()  # consume INDENT
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            key_tok = self.current_token()
            key = str(key_tok.value)
            if key == "providers":
                self.advance()
                self.expect(TokenType.COLON)
                providers = self._parse_providers_block()
            elif key == "consent":
                self.advance()
                self.expect(TokenType.COLON)
                consent = self._parse_consent_block()
            else:
                raise make_parse_error(
                    f"Unknown analytics key `{key}`. Expected `providers` or `consent`.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
            self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.AnalyticsSpec(providers=providers, consent=consent)

    def _parse_providers_block(self) -> list[ir.AnalyticsProviderInstance]:
        """Parse an indented providers map:

        providers:
          gtm:
            id: "GTM-XXX"
          plausible:
            domain: "example.com"
        """
        self.skip_newlines()
        result: list[ir.AnalyticsProviderInstance] = []
        seen_names: set[str] = set()

        if not self.match(TokenType.INDENT):
            return result

        self.advance()  # consume INDENT
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            name_tok = self.current_token()
            name = str(name_tok.value)
            if name in seen_names:
                raise make_parse_error(
                    f"Duplicate analytics provider `{name}`.",
                    self.file,
                    name_tok.line,
                    name_tok.column,
                )
            seen_names.add(name)
            self.advance()
            self.expect(TokenType.COLON)
            params = self._parse_provider_params()
            result.append(ir.AnalyticsProviderInstance(name=name, params=params))
            self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()
        return result

    def _parse_provider_params(self) -> dict[str, str]:
        """Parse an indented map of key: "value" pairs for one provider."""
        self.skip_newlines()
        params: dict[str, str] = {}

        if not self.match(TokenType.INDENT):
            # A provider with no indented body is valid (no params).
            return params

        self.advance()  # consume INDENT
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            key_tok = self.current_token()
            key = str(key_tok.value)
            if key in params:
                raise make_parse_error(
                    f"Duplicate provider parameter `{key}`.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
            self.advance()
            self.expect(TokenType.COLON)

            val_tok = self.current_token()
            if val_tok.type is TokenType.STRING:
                params[key] = str(val_tok.value)
            else:
                params[key] = str(val_tok.value)
            self.advance()
            self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()
        return params

    def _parse_consent_block(self) -> ir.AnalyticsConsentSpec:
        """Parse the consent: subsection."""
        self.skip_newlines()
        default_jurisdiction: str | None = None
        consent_override: str | None = None

        if not self.match(TokenType.INDENT):
            return ir.AnalyticsConsentSpec()

        self.advance()  # consume INDENT
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            key_tok = self.current_token()
            key = str(key_tok.value)
            self.advance()
            self.expect(TokenType.COLON)

            val_tok = self.current_token()
            value = str(val_tok.value)
            self.advance()

            if key == "default_jurisdiction":
                default_jurisdiction = value
            elif key == "consent_override":
                if value not in ("granted", "denied"):
                    raise make_parse_error(
                        f"consent_override must be `granted` or `denied`, got `{value}`.",
                        self.file,
                        val_tok.line,
                        val_tok.column,
                    )
                consent_override = value
            else:
                raise make_parse_error(
                    f"Unknown consent key `{key}`. "
                    f"Expected `default_jurisdiction` or `consent_override`.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
            self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.AnalyticsConsentSpec(
            default_jurisdiction=default_jurisdiction,
            consent_override=consent_override,
        )
