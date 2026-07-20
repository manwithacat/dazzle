"""
LLM parsing for DAZZLE DSL.

Handles parsing of llm_model, llm_config, and llm_intent blocks.
Part of Issue #33: LLM Jobs as First-Class Events.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from .. import ir
from ..errors import make_parse_error
from ..lexer import TokenType
from .dispatch import KeywordParser, parse_block_with_dispatch


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
        """Parse a ``llm_model <name> "Title"?:`` declaration.

        Refactored to dispatch-table style (follow-on to #1098). 6
        token-keyed `_lm_kw_*` parsers (provider/model_id/tier/max_tokens/
        cost_per_1k_input/cost_per_1k_output) + a `_build_llm_model`
        builder enforcing the required `provider` + `model_id` fields.

        Syntax::

            llm_model claude_sonnet "Claude Sonnet":
              provider: anthropic
              model_id: claude-sonnet-4-6
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

        state = _LLMModelState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_LLM_MODEL_KEYWORDS,
            state=state,
            on_unknown=_on_unknown_llm_model,
            ident_keywords=_LLM_MODEL_IDENT_KEYWORDS,
        )
        self.expect(TokenType.DEDENT)
        return _build_llm_model(self, name, title, state)

    def _parse_model_id_value(self) -> str:
        """Parse a model ID value which may contain hyphens."""
        parts = []
        # First part - identifier
        parts.append(self.expect_identifier_or_keyword().value)

        # Handle hyphenated model IDs like claude-haiku-4-5-20251001
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
        """Parse a top-level ``llm_config:`` block.

        Refactored to dispatch-table style (follow-on to #1098). 6
        token-keyed `_lc_kw_*` + 1 IDENT-text-matched (`concurrency`)
        + a `_build_llm_config` builder.

        Syntax::

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
              concurrency:
                claude_sonnet: 5
                gpt4o: 3
        """
        self.expect(TokenType.LLM_CONFIG)
        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        state = _LLMConfigState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_LLM_CONFIG_KEYWORDS,
            ident_keywords=_LLM_CONFIG_IDENT_KEYWORDS,
            state=state,
            on_unknown=_on_unknown_llm_config,
        )
        self.expect(TokenType.DEDENT)
        return _build_llm_config(state)

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
        """Parse a ``llm_intent <name> "Title":`` declaration.

        Refactored to dispatch-table style (follow-on to #1098). 9
        token-keyed `_li_kw_*` parsers + 1 IDENT-text-matched (`model`
        — IDENT-keyed because ``model`` is also a top-level
        ``llm_model`` constructor) + a `_build_llm_intent` builder.

        Syntax::

            llm_intent summarize_text "Summarize Text":
              model: claude_sonnet
              prompt: "Summarize the following: {{ input.text }}"
              timeout: 30
              output_schema: SummaryResult
              retry: ...
              pii: ...
              trigger: ...
        """
        self.expect(TokenType.LLM_INTENT)
        name = self.expect_identifier_or_keyword().value
        title = self.expect(TokenType.STRING).value if self.match(TokenType.STRING) else None

        self.expect(TokenType.COLON)
        self.skip_newlines()
        self.expect(TokenType.INDENT)

        state = _LLMIntentState()
        parse_block_with_dispatch(
            self,
            first_class_keywords=_LLM_INTENT_KEYWORDS,
            ident_keywords=_LLM_INTENT_IDENT_KEYWORDS,
            state=state,
            on_unknown=_on_unknown_llm_intent,
        )
        self.expect(TokenType.DEDENT)
        return _build_llm_intent(name, title, state)

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

    def _parse_llm_trigger(self) -> ir.LLMTriggerSpec:
        """Parse an LLM intent trigger block.

        Syntax:
            trigger:
              on_entity: Ticket
              on_event: created
              input_map:
                title: entity.title
              write_back:
                Ticket.category: output
              when: "entity.category == null"
        """
        self.expect(TokenType.INDENT)

        on_entity: str | None = None
        on_event: ir.LLMTriggerEvent | None = None
        input_map: dict[str, str] = {}
        write_back: dict[str, str] | None = None
        when: str | None = None

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            token = self.current_token()
            val = str(token.value)

            if val == "on_entity":
                self.advance()
                self.expect(TokenType.COLON)
                on_entity = str(self.expect_identifier_or_keyword().value)
                self.skip_newlines()

            elif val == "on_event":
                self.advance()
                self.expect(TokenType.COLON)
                event_str = str(self.expect_identifier_or_keyword().value)
                try:
                    on_event = ir.LLMTriggerEvent(event_str)
                except ValueError:
                    raise make_parse_error(
                        f"Invalid trigger event: {event_str}. "
                        "Must be: created, updated, or deleted",
                        self.file,
                        token.line,
                        token.column,
                    )
                self.skip_newlines()

            elif val == "input_map":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                input_map = self._parse_string_map()

            elif val == "write_back":
                self.advance()
                self.expect(TokenType.COLON)
                self.skip_newlines()
                write_back = self._parse_string_map()

            elif self.match(TokenType.WHEN):
                self.advance()
                self.expect(TokenType.COLON)
                when = str(self.expect(TokenType.STRING).value)
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        if on_entity is None:
            raise make_parse_error(
                "Trigger requires 'on_entity' field",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )
        if on_event is None:
            raise make_parse_error(
                "Trigger requires 'on_event' field",
                self.file,
                self.current_token().line,
                self.current_token().column,
            )

        return ir.LLMTriggerSpec(
            on_entity=on_entity,
            on_event=on_event,
            input_map=input_map,
            write_back=write_back,
            when=when,
        )

    def _parse_string_map(self) -> dict[str, str]:
        """Parse a block of key: value mappings into a dict.

        Syntax:
            INDENT
              key: value
              key: value
            DEDENT

        Keys may contain dots (e.g. Ticket.category).
        Values are read to end of line.
        """
        result: dict[str, str] = {}

        self.expect(TokenType.INDENT)

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            # Parse key (possibly dotted like Ticket.category)
            key = str(self.expect_identifier_or_keyword().value)
            while self.match(TokenType.DOT):
                self.advance()
                key += "." + str(self.expect_identifier_or_keyword().value)

            self.expect(TokenType.COLON)

            # Parse value — read tokens to end of line
            if self.match(TokenType.STRING):
                value = str(self.current_token().value)
                self.advance()
            else:
                # Read dotted identifier value like entity.title
                value = str(self.expect_identifier_or_keyword().value)
                while self.match(TokenType.DOT):
                    self.advance()
                    value += "." + str(self.expect_identifier_or_keyword().value)

            result[key] = value
            self.skip_newlines()

        self.expect(TokenType.DEDENT)
        return result

    def _parse_concurrency_limits(self) -> dict[str, int]:
        """Parse concurrency limits block (same format as rate_limits)."""
        self.expect(TokenType.INDENT)

        limits: dict[str, int] = {}

        while not self.match(TokenType.DEDENT):
            self.skip_newlines()
            if self.match(TokenType.DEDENT):
                break

            if self.match(TokenType.IDENTIFIER):
                model_name = self.current_token().value
                self.advance()
                self.expect(TokenType.COLON)
                limit = int(self.expect(TokenType.NUMBER).value)
                limits[model_name] = limit
                self.skip_newlines()

            else:
                self.advance()
                self.skip_newlines()

        self.expect(TokenType.DEDENT)

        return limits


# ============================================================ #
# parse_llm_intent — keyword-dispatch decomposition (#1098 template) #
# ============================================================ #
#
# The 140-line monolith was replaced (v0.70.23) with the dispatch
# pattern shipped in #1097. 9 token-keyed `_li_kw_*` parsers + 1
# IDENT-text-matched (`model`) + a `_build_llm_intent` builder.


@dataclass
class _LLMIntentState:
    """Accumulator for :meth:`LLMParserMixin.parse_llm_intent`."""

    model_ref: str | None = None
    prompt_template: str = ""
    description: str | None = None
    output_schema: str | None = None
    timeout_seconds: int = 30
    vision: bool = False
    retry: ir.RetryPolicySpec | None = None
    pii: ir.PIIPolicySpec | None = None
    triggers: list[ir.LLMTriggerSpec] = field(default_factory=list)


# ---------- Token-keyed keyword parsers ---------- #


def _li_kw_prompt(parser: Any, state: _LLMIntentState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.prompt_template = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _li_kw_description(parser: Any, state: _LLMIntentState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.description = parser.expect(TokenType.STRING).value
    parser.skip_newlines()


def _li_kw_output_schema(parser: Any, state: _LLMIntentState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.output_schema = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _li_kw_timeout(parser: Any, state: _LLMIntentState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.timeout_seconds = int(parser.expect(TokenType.NUMBER).value)
    parser.skip_newlines()


def _li_kw_max_tokens(parser: Any, state: _LLMIntentState) -> None:
    """``max_tokens: <int>`` — informational at the intent level.

    Authoritative ``max_tokens`` lives on the referenced ``llm_model``;
    accept and discard here for authoring convenience.
    """
    parser.advance()
    parser.expect(TokenType.COLON)
    int(parser.expect(TokenType.NUMBER).value)  # discarded
    parser.skip_newlines()


def _li_kw_vision(parser: Any, state: _LLMIntentState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.vision = parser._parse_boolean()
    parser.skip_newlines()


def _li_kw_retry(parser: Any, state: _LLMIntentState) -> None:
    """``retry:`` — nested policy block (max_attempts/backoff/delays)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    state.retry = parser._parse_retry_policy()


def _li_kw_pii(parser: Any, state: _LLMIntentState) -> None:
    """``pii:`` — nested PII scan/action policy block."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    state.pii = parser._parse_pii_policy()


def _li_kw_trigger(parser: Any, state: _LLMIntentState) -> None:
    """``trigger:`` — nested entity/event-bound trigger block (multi-allowed)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    state.triggers.append(parser._parse_llm_trigger())


# ---------- IDENT-text-matched keyword parsers ---------- #


def _li_kw_model(parser: Any, state: _LLMIntentState) -> None:
    """``model: model_name`` — IDENT-keyed because ``model`` is not a lexer keyword."""
    parser.advance()
    parser.expect(TokenType.COLON)
    state.model_ref = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


# ---------- Dispatch tables + on_unknown + builder ---------- #


_LLM_INTENT_KEYWORDS: dict[TokenType, KeywordParser[_LLMIntentState]] = {
    TokenType.PROMPT: _li_kw_prompt,
    TokenType.DESCRIPTION: _li_kw_description,
    TokenType.OUTPUT_SCHEMA: _li_kw_output_schema,
    TokenType.TIMEOUT: _li_kw_timeout,
    TokenType.MAX_TOKENS: _li_kw_max_tokens,
    TokenType.VISION: _li_kw_vision,
    TokenType.RETRY: _li_kw_retry,
    TokenType.PII: _li_kw_pii,
    TokenType.TRIGGER: _li_kw_trigger,
}


_LLM_INTENT_IDENT_KEYWORDS: dict[str, KeywordParser[_LLMIntentState]] = {
    "model": _li_kw_model,
}


def _on_unknown_llm_intent(parser: Any) -> None:
    """Silently skip unknown keywords + their newline (mirrors legacy else branch)."""
    parser.advance()
    parser.skip_newlines()


def _build_llm_intent(name: str, title: str | None, state: _LLMIntentState) -> ir.LLMIntentSpec:
    return ir.LLMIntentSpec(
        name=name,
        title=title,
        description=state.description,
        model_ref=state.model_ref,
        prompt_template=state.prompt_template,
        output_schema=state.output_schema,
        timeout_seconds=state.timeout_seconds,
        vision=state.vision,
        retry=state.retry,
        pii=state.pii,
        triggers=state.triggers,
    )


# ============================================================ #
# parse_llm_model — keyword-dispatch decomposition (#1098 template) #
# ============================================================ #
#
# The 133-line monolith was replaced (v0.70.25) with the dispatch
# pattern shipped in #1097. 6 token-keyed `_lm_kw_*` parsers + a
# `_build_llm_model` builder enforcing the required `provider` and
# `model_id` fields.


@dataclass
class _LLMModelState:
    """Accumulator for :meth:`LLMParserMixin.parse_llm_model`."""

    provider: ir.LLMProvider | None = None
    model_id: str | None = None
    tier: ir.ModelTier = ir.ModelTier.BALANCED
    max_tokens: int = 4096
    cost_per_1k_input: Decimal | None = None
    cost_per_1k_output: Decimal | None = None
    base_url: str | None = None
    project: str | None = None
    location: str | None = None
    api_key_env: str | None = None


# ---------- Keyword parsers ---------- #


def _lm_kw_provider(parser: Any, state: _LLMModelState) -> None:
    """``provider: anthropic | openai | google | local`` — validated."""
    parser.advance()
    parser.expect(TokenType.COLON)
    provider_str = parser.expect_identifier_or_keyword().value
    try:
        state.provider = ir.LLMProvider(provider_str)
    except ValueError:
        token = parser.current_token()
        raise make_parse_error(
            f"Invalid LLM provider: {provider_str}. Must be: anthropic, openai, google, or local",
            parser.file,
            token.line,
            token.column,
        )
    parser.skip_newlines()


def _lm_kw_model_id(parser: Any, state: _LLMModelState) -> None:
    """``model_id: <STRING | hyphenated-id>`` — accepts both forms."""
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.STRING):
        state.model_id = parser.current_token().value
        parser.advance()
    else:
        state.model_id = parser._parse_model_id_value()
    parser.skip_newlines()


def _lm_kw_tier(parser: Any, state: _LLMModelState) -> None:
    """``tier: fast | balanced | quality`` — validated."""
    parser.advance()
    parser.expect(TokenType.COLON)
    tier_str = parser.expect_identifier_or_keyword().value
    try:
        state.tier = ir.ModelTier(tier_str)
    except ValueError:
        token = parser.current_token()
        raise make_parse_error(
            f"Invalid model tier: {tier_str}. Must be: fast, balanced, or quality",
            parser.file,
            token.line,
            token.column,
        )
    parser.skip_newlines()


def _lm_kw_max_tokens(parser: Any, state: _LLMModelState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.max_tokens = int(parser.expect(TokenType.NUMBER).value)
    parser.skip_newlines()


def _lm_kw_cost_per_1k_input(parser: Any, state: _LLMModelState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.cost_per_1k_input = Decimal(parser.expect(TokenType.NUMBER).value)
    parser.skip_newlines()


def _lm_kw_cost_per_1k_output(parser: Any, state: _LLMModelState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.cost_per_1k_output = Decimal(parser.expect(TokenType.NUMBER).value)
    parser.skip_newlines()


def _lm_ident_string_field(parser: Any, *, allow_hyphenated: bool = False) -> str:
    """``field: "value"`` or bare identifier — return the string value.

    When ``allow_hyphenated`` is True (GCP project / location ids), bare
    values may include hyphens like ``badger-payroll`` or ``europe-west2``.
    """
    parser.advance()
    parser.expect(TokenType.COLON)
    if parser.match(TokenType.STRING):
        value = str(parser.current_token().value)
        parser.advance()
    elif allow_hyphenated:
        value = str(parser._parse_model_id_value())
    else:
        value = str(parser.expect_identifier_or_keyword().value)
    parser.skip_newlines()
    return value


def _lm_kw_base_url(parser: Any, state: _LLMModelState) -> None:
    """``base_url: "https://…"`` — OpenAI-compatible endpoint (prefer quoted)."""
    state.base_url = _lm_ident_string_field(parser)


def _lm_kw_project(parser: Any, state: _LLMModelState) -> None:
    """``project: badger-payroll`` — Vertex GCP project id (hyphens ok)."""
    state.project = _lm_ident_string_field(parser, allow_hyphenated=True)


def _lm_kw_location(parser: Any, state: _LLMModelState) -> None:
    """``location: global | europe-west2`` — Vertex Gen AI location."""
    state.location = _lm_ident_string_field(parser, allow_hyphenated=True)


def _lm_kw_api_key_env(parser: Any, state: _LLMModelState) -> None:
    """``api_key_env: OPENAI_API_KEY`` — override credential env var name."""
    state.api_key_env = _lm_ident_string_field(parser)


# ---------- Dispatch table + on_unknown + builder ---------- #


_LLM_MODEL_KEYWORDS: dict[TokenType, KeywordParser[_LLMModelState]] = {
    TokenType.PROVIDER: _lm_kw_provider,
    TokenType.MODEL_ID: _lm_kw_model_id,
    TokenType.TIER: _lm_kw_tier,
    TokenType.MAX_TOKENS: _lm_kw_max_tokens,
    TokenType.COST_PER_1K_INPUT: _lm_kw_cost_per_1k_input,
    TokenType.COST_PER_1K_OUTPUT: _lm_kw_cost_per_1k_output,
}


# Ident-keyed so common words (project, location) are not global lexer keywords.
_LLM_MODEL_IDENT_KEYWORDS: dict[str, KeywordParser[_LLMModelState]] = {
    "base_url": _lm_kw_base_url,
    "project": _lm_kw_project,
    "location": _lm_kw_location,
    "api_key_env": _lm_kw_api_key_env,
}


def _on_unknown_llm_model(parser: Any) -> None:
    """Silently skip unknown keywords + their newline (mirrors legacy else branch)."""
    parser.advance()
    parser.skip_newlines()


def _build_llm_model(
    parser: Any, name: str, title: str | None, state: _LLMModelState
) -> ir.LLMModelSpec:
    """Enforce required provider + model_id; assemble the IR."""
    if state.provider is None:
        token = parser.current_token()
        raise make_parse_error(
            "llm_model requires 'provider' field",
            parser.file,
            token.line,
            token.column,
        )
    if state.model_id is None:
        token = parser.current_token()
        raise make_parse_error(
            "llm_model requires 'model_id' field",
            parser.file,
            token.line,
            token.column,
        )

    return ir.LLMModelSpec(
        name=name,
        title=title,
        provider=state.provider,
        model_id=state.model_id,
        tier=state.tier,
        max_tokens=state.max_tokens,
        cost_per_1k_input=state.cost_per_1k_input,
        cost_per_1k_output=state.cost_per_1k_output,
        base_url=state.base_url,
        project=state.project,
        location=state.location,
        api_key_env=state.api_key_env,
    )


# ============================================================ #
# parse_llm_config — keyword-dispatch decomposition (#1098 template) #
# ============================================================ #
#
# The 122-line monolith was replaced (v0.70.26) with the dispatch
# pattern shipped in #1097. 6 token-keyed `_lc_kw_*` + 1 IDENT-keyed
# (`concurrency`) + a `_build_llm_config` builder.


@dataclass
class _LLMConfigState:
    """Accumulator for :meth:`LLMParserMixin.parse_llm_config`."""

    default_model: str | None = None
    default_provider: ir.LLMProvider | None = None
    budget_alert_usd: Decimal | None = None
    artifact_store: ir.ArtifactStore = ir.ArtifactStore.LOCAL
    logging: ir.LoggingPolicySpec = field(default_factory=ir.LoggingPolicySpec)
    rate_limits: dict[str, int] | None = None
    concurrency: dict[str, int] | None = None


# ---------- Token-keyed keyword parsers ---------- #


def _lc_kw_default_model(parser: Any, state: _LLMConfigState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.default_model = parser.expect_identifier_or_keyword().value
    parser.skip_newlines()


def _lc_kw_default_provider(parser: Any, state: _LLMConfigState) -> None:
    """``default_provider: anthropic | openai | google | local`` — validated."""
    parser.advance()
    parser.expect(TokenType.COLON)
    provider_str = parser.expect_identifier_or_keyword().value
    try:
        state.default_provider = ir.LLMProvider(provider_str)
    except ValueError:
        token = parser.current_token()
        raise make_parse_error(
            f"Invalid LLM provider: {provider_str}. Must be: anthropic, openai, google, or local",
            parser.file,
            token.line,
            token.column,
        )
    parser.skip_newlines()


def _lc_kw_budget_alert_usd(parser: Any, state: _LLMConfigState) -> None:
    parser.advance()
    parser.expect(TokenType.COLON)
    state.budget_alert_usd = Decimal(parser.expect(TokenType.NUMBER).value)
    parser.skip_newlines()


def _lc_kw_artifact_store(parser: Any, state: _LLMConfigState) -> None:
    """``artifact_store: local | s3 | gcs`` — validated."""
    parser.advance()
    parser.expect(TokenType.COLON)
    store_str = parser.expect_identifier_or_keyword().value
    try:
        state.artifact_store = ir.ArtifactStore(store_str)
    except ValueError:
        token = parser.current_token()
        raise make_parse_error(
            f"Invalid artifact store: {store_str}. Must be: local, s3, or gcs",
            parser.file,
            token.line,
            token.column,
        )
    parser.skip_newlines()


def _lc_kw_logging(parser: Any, state: _LLMConfigState) -> None:
    """``logging:`` — nested LoggingPolicy block."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    state.logging = parser._parse_logging_policy()


def _lc_kw_rate_limits(parser: Any, state: _LLMConfigState) -> None:
    """``rate_limits:`` — nested map of model_name → int RPM."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    state.rate_limits = parser._parse_rate_limits()


# ---------- IDENT-text-matched keyword parsers ---------- #


def _lc_kw_concurrency(parser: Any, state: _LLMConfigState) -> None:
    """``concurrency:`` — nested map (same shape as rate_limits)."""
    parser.advance()
    parser.expect(TokenType.COLON)
    parser.skip_newlines()
    state.concurrency = parser._parse_concurrency_limits()


# ---------- Dispatch tables + on_unknown + builder ---------- #


_LLM_CONFIG_KEYWORDS: dict[TokenType, KeywordParser[_LLMConfigState]] = {
    TokenType.DEFAULT_MODEL: _lc_kw_default_model,
    TokenType.DEFAULT_PROVIDER: _lc_kw_default_provider,
    TokenType.BUDGET_ALERT_USD: _lc_kw_budget_alert_usd,
    TokenType.ARTIFACT_STORE: _lc_kw_artifact_store,
    TokenType.LOGGING: _lc_kw_logging,
    TokenType.RATE_LIMITS: _lc_kw_rate_limits,
}


_LLM_CONFIG_IDENT_KEYWORDS: dict[str, KeywordParser[_LLMConfigState]] = {
    "concurrency": _lc_kw_concurrency,
}


def _on_unknown_llm_config(parser: Any) -> None:
    """Silently skip unknown keywords + their newline (mirrors legacy else)."""
    parser.advance()
    parser.skip_newlines()


def _build_llm_config(state: _LLMConfigState) -> ir.LLMConfigSpec:
    return ir.LLMConfigSpec(
        default_model=state.default_model,
        default_provider=state.default_provider,
        budget_alert_usd=state.budget_alert_usd,
        artifact_store=state.artifact_store,
        logging=state.logging,
        rate_limits=state.rate_limits,
        concurrency=state.concurrency,
    )
