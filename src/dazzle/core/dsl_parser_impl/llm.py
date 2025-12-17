"""
LLM parsing for DAZZLE DSL.

Handles parsing of llm_model, llm_config, and llm_intent blocks.
Part of Issue #33: LLM Jobs as First-Class Events.
"""

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType


class LLMParserMixin:
    """
    Mixin providing LLM-related block parsing.

    Note: This mixin expects to be combined with BaseParser via multiple inheritance.
    """

    if TYPE_CHECKING:
        expect: Any
        advance: Any
        match: Any
        current_token: Any
        expect_identifier_or_keyword: Any
        skip_newlines: Any
        file: Any

    def parse_llm_model(self) -> ir.LLMModelSpec:
        """
        Parse llm_model declaration.

        Syntax:
            llm_model claude_sonnet "Claude Sonnet":
              provider: anthropic
              model_id: claude-3-5-sonnet-20241022
              tier: balanced
              max_tokens: 4096
              cost_per_1k_input: 0.003
              cost_per_1k_output: 0.015
        """
        self.expect(TokenType.LLM_MODEL)
        name = self.expect_identifier_or_keyword().value
        title = self.expect(TokenType.STRING).value if self.match(TokenType.STRING) else None

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        provider: ir.LLMProvider | None = None
        model_id: str | None = None
        tier: ir.ModelTier = ir.ModelTier.BALANCED
        max_tokens: int = 4096
        cost_per_1k_input: Decimal | None = None
        cost_per_1k_output: Decimal | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # provider: anthropic | openai | google | local
            if self.match(TokenType.PROVIDER):
                self.advance()
                self.expect(TokenType.COLON)
                provider_str = self.expect_identifier_or_keyword().value
                try:
                    provider = ir.LLMProvider(provider_str)
                except ValueError:
                    token = self.current_token()
                    raise make_parse_error(
                        f"Invalid LLM provider: {provider_str}. "
                        "Must be: anthropic, openai, google, or local",
                        self.file,
                        token.line,
                        token.column,
                    )
                self.skip_newlines()

            # model_id: claude-3-5-sonnet-20241022
            elif self.match(TokenType.MODEL_ID):
                self.advance()
                self.expect(TokenType.COLON)
                # model_id can be a string or identifier
                if self.match(TokenType.STRING):
                    model_id = self.current_token().value
                    self.advance()
                else:
                    model_id = self._parse_model_id_value()
                self.skip_newlines()

            # tier: fast | balanced | quality
            elif self.match(TokenType.TIER):
                self.advance()
                self.expect(TokenType.COLON)
                tier_str = self.expect_identifier_or_keyword().value
                try:
                    tier = ir.ModelTier(tier_str)
                except ValueError:
                    token = self.current_token()
                    raise make_parse_error(
                        f"Invalid model tier: {tier_str}. Must be: fast, balanced, or quality",
                        self.file,
                        token.line,
                        token.column,
                    )
                self.skip_newlines()

            # max_tokens: 4096
            elif self.match(TokenType.MAX_TOKENS):
                self.advance()
                self.expect(TokenType.COLON)
                max_tokens = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            # cost_per_1k_input: 0.003
            elif self.match(TokenType.COST_PER_1K_INPUT):
                self.advance()
                self.expect(TokenType.COLON)
                cost_per_1k_input = Decimal(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            # cost_per_1k_output: 0.015
            elif self.match(TokenType.COST_PER_1K_OUTPUT):
                self.advance()
                self.expect(TokenType.COLON)
                cost_per_1k_output = Decimal(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            else:
                # Skip unknown fields
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        # Validate required fields
        if provider is None:
            raise make_parse_error(
                "llm_model requires 'provider' field",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )
        if model_id is None:
            raise make_parse_error(
                "llm_model requires 'model_id' field",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )

        return ir.LLMModelSpec(
            name=name,
            title=title,
            provider=provider,
            model_id=model_id,
            tier=tier,
            max_tokens=max_tokens,
            cost_per_1k_input=cost_per_1k_input,
            cost_per_1k_output=cost_per_1k_output,
        )

    def _parse_model_id_value(self) -> str:
        """Parse a model ID value which may contain hyphens."""
        parts = []
        # First part - identifier
        parts.append(self.expect_identifier_or_keyword().value)

        # Handle hyphenated model IDs like claude-3-5-sonnet-20241022
        while self.match(TokenType.MINUS):
            self.advance()
            if self.match(TokenType.NUMBER):
                parts.append(self.current_token().value)
                self.advance()
            elif self.match(TokenType.IDENTIFIER):
                parts.append(self.current_token().value)
                self.advance()
            else:
                parts.append(self.expect_identifier_or_keyword().value)

        return "-".join(parts)

    def parse_llm_config(self) -> ir.LLMConfigSpec:
        """
        Parse llm_config declaration.

        Syntax:
            llm_config:
              default_model: claude_sonnet
              artifact_store: local
              logging:
                log_prompts: true
                log_completions: true
                redact_pii: true
              rate_limits:
                claude_sonnet: 60
                gpt4o: 30
        """
        self.expect(TokenType.LLM_CONFIG)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        default_model: str | None = None
        artifact_store: ir.ArtifactStore = ir.ArtifactStore.LOCAL
        logging: ir.LoggingPolicySpec = ir.LoggingPolicySpec()
        rate_limits: dict[str, int] | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # default_model: model_name
            if self.match(TokenType.DEFAULT_MODEL):
                self.advance()
                self.expect(TokenType.COLON)
                default_model = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # artifact_store: local | s3 | gcs
            elif self.match(TokenType.ARTIFACT_STORE):
                self.advance()
                self.expect(TokenType.COLON)
                store_str = self.expect_identifier_or_keyword().value
                try:
                    artifact_store = ir.ArtifactStore(store_str)
                except ValueError:
                    token = self.current_token()
                    raise make_parse_error(
                        f"Invalid artifact store: {store_str}. Must be: local, s3, or gcs",
                        self.file,
                        token.line,
                        token.column,
                    )
                self.skip_newlines()

            # logging: (nested block)
            elif self.match(TokenType.LOGGING):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                logging = self._parse_logging_policy()

            # rate_limits: (nested block)
            elif self.match(TokenType.RATE_LIMITS):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                rate_limits = self._parse_rate_limits()

            else:
                # Skip unknown fields
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.LLMConfigSpec(
            default_model=default_model,
            artifact_store=artifact_store,
            logging=logging,
            rate_limits=rate_limits,
        )

    def _parse_logging_policy(self) -> ir.LoggingPolicySpec:
        """Parse logging policy block."""
        self.expect(TokenType.INDENT)

        log_prompts: bool = True
        log_completions: bool = True
        redact_pii: bool = True

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.LOG_PROMPTS):
                self.advance()
                self.expect(TokenType.COLON)
                log_prompts = self._parse_boolean()
                self.skip_newlines()

            elif self.match(TokenType.LOG_COMPLETIONS):
                self.advance()
                self.expect(TokenType.COLON)
                log_completions = self._parse_boolean()
                self.skip_newlines()

            elif self.match(TokenType.REDACT_PII):
                self.advance()
                self.expect(TokenType.COLON)
                redact_pii = self._parse_boolean()
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.LoggingPolicySpec(
            log_prompts=log_prompts,
            log_completions=log_completions,
            redact_pii=redact_pii,
        )

    def _parse_rate_limits(self) -> dict[str, int]:
        """Parse rate limits block."""
        self.expect(TokenType.INDENT)

        rate_limits: dict[str, int] = {}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # model_name: rate
            if self.match(TokenType.IDENTIFIER):
                model_name = self.current_token().value
                self.advance()
                self.expect(TokenType.COLON)
                rate = int(self.expect(TokenType.NUMBER).value)
                rate_limits[model_name] = rate
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return rate_limits

    def parse_llm_intent(self) -> ir.LLMIntentSpec:
        """
        Parse llm_intent declaration.

        Syntax:
            llm_intent summarize_text "Summarize Text":
              model: claude_sonnet
              prompt: "Summarize the following: {{ input.text }}"
              timeout: 30
              output_schema: SummaryResult
              retry:
                max_attempts: 3
                backoff: exponential
              pii:
                scan: true
                action: redact
        """
        self.expect(TokenType.LLM_INTENT)
        name = self.expect_identifier_or_keyword().value
        title = self.expect(TokenType.STRING).value if self.match(TokenType.STRING) else None

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        model_ref: str | None = None
        prompt_template: str | None = None
        output_schema: str | None = None
        timeout_seconds: int = 30
        retry: ir.RetryPolicySpec | None = None
        pii: ir.PIIPolicySpec | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # model: model_name (note: 'model' is an identifier, not a keyword)
            if self.match(TokenType.IDENTIFIER) and self.current_token().value == "model":
                self.advance()
                self.expect(TokenType.COLON)
                model_ref = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # prompt: "template string"
            elif self.match(TokenType.PROMPT):
                self.advance()
                self.expect(TokenType.COLON)
                prompt_template = self.expect(TokenType.STRING).value
                self.skip_newlines()

            # output_schema: EntityName
            elif self.match(TokenType.OUTPUT_SCHEMA):
                self.advance()
                self.expect(TokenType.COLON)
                output_schema = self.expect_identifier_or_keyword().value
                self.skip_newlines()

            # timeout: 30
            elif self.match(TokenType.TIMEOUT):
                self.advance()
                self.expect(TokenType.COLON)
                timeout_seconds = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            # retry: (nested block)
            elif self.match(TokenType.RETRY):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                retry = self._parse_retry_policy()

            # pii: (nested block)
            elif self.match(TokenType.PII):
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                pii = self._parse_pii_policy()

            else:
                # Skip unknown fields
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        # Validate required fields
        if prompt_template is None:
            raise make_parse_error(
                "llm_intent requires 'prompt' field",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )

        return ir.LLMIntentSpec(
            name=name,
            title=title,
            model_ref=model_ref,
            prompt_template=prompt_template,
            output_schema=output_schema,
            timeout_seconds=timeout_seconds,
            retry=retry,
            pii=pii,
        )

    def _parse_retry_policy(self) -> ir.RetryPolicySpec:
        """Parse retry policy block."""
        self.expect(TokenType.INDENT)

        max_attempts: int = 3
        backoff: ir.RetryBackoff = ir.RetryBackoff.EXPONENTIAL
        initial_delay_ms: int = 1000
        max_delay_ms: int = 30000

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.MAX_ATTEMPTS):
                self.advance()
                self.expect(TokenType.COLON)
                max_attempts = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            elif self.match(TokenType.BACKOFF):
                self.advance()
                self.expect(TokenType.COLON)
                backoff_str = self.expect_identifier_or_keyword().value
                try:
                    backoff = ir.RetryBackoff(backoff_str)
                except ValueError:
                    token = self.current_token()
                    raise make_parse_error(
                        f"Invalid backoff strategy: {backoff_str}. Must be: linear or exponential",
                        self.file,
                        token.line,
                        token.column,
                    )
                self.skip_newlines()

            elif self.match(TokenType.INITIAL_DELAY_MS):
                self.advance()
                self.expect(TokenType.COLON)
                initial_delay_ms = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            elif self.match(TokenType.MAX_DELAY_MS):
                self.advance()
                self.expect(TokenType.COLON)
                max_delay_ms = int(self.expect(TokenType.NUMBER).value)
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.RetryPolicySpec(
            max_attempts=max_attempts,
            backoff=backoff,
            initial_delay_ms=initial_delay_ms,
            max_delay_ms=max_delay_ms,
        )

    def _parse_pii_policy(self) -> ir.PIIPolicySpec:
        """Parse PII policy block."""
        self.expect(TokenType.INDENT)

        scan: bool = False
        action: ir.PIIAction = ir.PIIAction.WARN
        patterns: list[str] = []

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.SCAN):
                self.advance()
                self.expect(TokenType.COLON)
                scan = self._parse_boolean()
                self.skip_newlines()

            elif self.match(TokenType.ACTION):
                self.advance()
                self.expect(TokenType.COLON)
                action_str = self.expect_identifier_or_keyword().value
                try:
                    action = ir.PIIAction(action_str)
                except ValueError:
                    token = self.current_token()
                    raise make_parse_error(
                        f"Invalid PII action: {action_str}. Must be: warn, redact, or reject",
                        self.file,
                        token.line,
                        token.column,
                    )
                self.skip_newlines()

            elif self.match(TokenType.PATTERNS):
                self.advance()
                self.expect(TokenType.COLON)
                patterns = self._parse_string_list_llm()
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return ir.PIIPolicySpec(
            scan=scan,
            action=action,
            patterns=patterns,
        )

    def _parse_boolean(self) -> bool:
        """Parse a boolean value."""
        if self.match(TokenType.TRUE):
            self.advance()
            return True
        elif self.match(TokenType.FALSE):
            self.advance()
            return False
        else:
            token = self.current_token()
            raise make_parse_error(
                f"Expected true or false, got {token.value}",
                self.file,
                token.line,
                token.column,
            )

    def _parse_string_list_llm(self) -> list[str]:
        """Parse a comma-separated list of strings."""
        strings: list[str] = []

        while True:
            if self.match(TokenType.STRING):
                strings.append(self.current_token().value)
                self.advance()

                if self.match(TokenType.COMMA):
                    self.advance()
                else:
                    break
            else:
                break

        return strings
