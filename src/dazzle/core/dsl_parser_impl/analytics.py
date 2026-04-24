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
        server_side: ir.AnalyticsServerSideSpec | None = None

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
            elif key == "server_side":
                self.advance()
                self.expect(TokenType.COLON)
                server_side = self._parse_server_side_block(key_tok.line, key_tok.column)
            else:
                raise make_parse_error(
                    f"Unknown analytics key `{key}`. "
                    f"Expected `providers`, `consent`, or `server_side`.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
            self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        return ir.AnalyticsSpec(
            providers=providers,
            consent=consent,
            server_side=server_side,
        )

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

    def _parse_server_side_block(
        self,
        block_line: int,
        block_col: int,
    ) -> ir.AnalyticsServerSideSpec:
        """Parse the server_side: subsection.

        Keys:
            sink:             required — name of a registered AnalyticsSink
            measurement_id:   optional — provider default ID
            bus_topics:       optional — list of topic globs to subscribe to
        """
        self.skip_newlines()
        sink: str | None = None
        measurement_id: str | None = None
        bus_topics: list[str] = []
        seen_keys: set[str] = set()

        if not self.match(TokenType.INDENT):
            raise make_parse_error(
                "Empty `server_side:` block — must declare at least `sink:`.",
                self.file,
                block_line,
                block_col,
            )

        self.advance()  # consume INDENT
        while not self.match(TokenType.DEDENT, TokenType.EOF):
            self.skip_newlines()
            if self.match(TokenType.DEDENT, TokenType.EOF):
                break

            key_tok = self.current_token()
            key = str(key_tok.value)
            if key in seen_keys:
                raise make_parse_error(
                    f"Duplicate server_side key `{key}`.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
            if key not in ("sink", "measurement_id", "bus_topics"):
                raise make_parse_error(
                    f"Unknown server_side key `{key}`. "
                    f"Expected `sink`, `measurement_id`, or `bus_topics`.",
                    self.file,
                    key_tok.line,
                    key_tok.column,
                )
            seen_keys.add(key)
            self.advance()
            self.expect(TokenType.COLON)

            if key == "bus_topics":
                bus_topics = self._parse_topic_glob_list()
            else:
                val_tok = self.current_token()
                value = str(val_tok.value)
                self.advance()
                if key == "sink":
                    sink = value
                else:
                    measurement_id = value
            self.skip_newlines()

        if self.match(TokenType.DEDENT):
            self.advance()

        if sink is None:
            raise make_parse_error(
                "`server_side:` block missing required `sink:` key.",
                self.file,
                block_line,
                block_col,
            )
        return ir.AnalyticsServerSideSpec(
            sink=sink,
            measurement_id=measurement_id,
            bus_topics=bus_topics,
        )

    def _parse_topic_glob_list(self) -> list[str]:
        """Parse a bracket list of topic globs.

        Globs accept alphanumerics, underscore, dot, and `*`. The parser
        concatenates tokens so `audit.*` / `transition.*.created` parse
        cleanly even though the lexer splits them.
        """
        topics: list[str] = []
        if not self.match(TokenType.LBRACKET):
            tok = self.current_token()
            self.advance()
            return [str(tok.value)]

        self.advance()  # consume '['
        while not self.match(TokenType.RBRACKET):
            tok = self.current_token()
            value = str(tok.value)
            self.advance()
            # Stitch subsequent DOT + identifier / STAR tokens into one glob.
            while self.match(TokenType.DOT) or self.match(TokenType.STAR):
                piece = self.advance().value
                value = f"{value}{piece}"
                # After a dot, the next token is usually an identifier/star.
                if value.endswith("."):
                    next_tok = self.current_token()
                    value = f"{value}{next_tok.value}"
                    self.advance()
            topics.append(value)
            if self.match(TokenType.COMMA):
                self.advance()
        self.expect(TokenType.RBRACKET)
        return topics

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
