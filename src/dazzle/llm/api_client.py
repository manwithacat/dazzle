"""
API client for LLM providers (Anthropic, OpenAI).

Handles authentication, request formatting, and response parsing.
Supports fallback to Claude CLI for users with Claude subscriptions.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from dazzle.core.model_defaults import ANTHROPIC_PRICING_PER_MTOK, DEFAULT_JUDGMENT_MODEL
from dazzle.llm.driver import (
    DRIVER_CLAUDE_CLI,
    DRIVER_GROK_CLI,
    PRODUCTION_NEEDS_API_KEY_MSG,
    call_subscription_cli,
    pick_available_subscription_driver,
)

if TYPE_CHECKING:
    from anthropic import Anthropic
    from openai import OpenAI

logger = logging.getLogger(__name__)


def _strip_code_fence(s: str) -> str:
    """Strip an optional markdown code fence from an LLM response (#1219).

    Claude's instruction-following routinely wraps JSON output in
    triple-backtick fences even when the prompt explicitly asks for
    raw JSON. Rather than fight the model, normalise on the consumer
    side. Handles ``\\`\\`\\`json\\n…\\n\\`\\`\\``` and bare ``\\`\\`\\`…\\`\\`\\``` and
    leaves unfenced responses unchanged.
    """
    s = s.strip()
    if not s.startswith("```"):
        return s
    # Drop the opening fence (and optional language tag on the same line).
    s = s.split("\n", 1)[1] if "\n" in s else s[3:]
    # Drop the closing fence if present.
    if s.rstrip().endswith("```"):
        s = s.rstrip()[:-3]
    return s.strip()


class LLMProvider(StrEnum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    CLAUDE_CLI = "claude_cli"  # Claude Code CLI (subscription)
    GROK_CLI = "grok_cli"  # Grok Build CLI (subscription)


class Completion(NamedTuple):
    """A completion plus the provider-reported token usage (#1528).

    ``tokens_in`` / ``tokens_out`` are 0 when the provider does not
    report usage (notably the Claude CLI subscription path, which only
    reports a total) — cost computation treats 0/0 as "unknown", never
    as free.
    """

    text: str
    tokens_in: int
    tokens_out: int


class LLMAPIClient:
    """
    API client for LLM providers.

    Supports Anthropic Claude and OpenAI GPT models.
    """

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.ANTHROPIC,
        model: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16000,
        use_prompt_caching: bool = True,
    ):
        """
        Initialize LLM API client.

        Args:
            provider: LLM provider (anthropic or openai)
            model: Model name (defaults based on provider)
            api_key: API key (if not provided, read from env)
            api_key_env: Environment variable name for API key
            temperature: Temperature for sampling (0.0 = deterministic)
            max_tokens: Maximum tokens in response
            use_prompt_caching: Use prompt caching if supported
        """
        self.provider = provider
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_prompt_caching = use_prompt_caching
        # Unique identifier for this client instance — correlates LLM
        # invocations with telemetry/proposals. Consumed by the fitness
        # investigator runner (see LlmClient Protocol). Generated once per
        # client so multiple invocations from the same run share the ID.
        self.run_id: str = uuid.uuid4().hex

        # Get API key
        self.api_key: str | None = None
        self._use_cli_fallback = False
        # Concrete subscription driver when using CLI fallback (claude-cli / grok-cli).
        self._cli_driver: str | None = None

        if api_key:
            self.api_key = api_key
        elif api_key_env:
            self.api_key = os.environ.get(api_key_env)
        else:
            # Default env var names
            if provider == LLMProvider.ANTHROPIC:
                self.api_key = os.environ.get("ANTHROPIC_API_KEY")
            elif provider == LLMProvider.OPENAI:
                self.api_key = os.environ.get("OPENAI_API_KEY")
            elif provider == LLMProvider.CLAUDE_CLI:
                self._use_cli_fallback = True
                self._cli_driver = DRIVER_CLAUDE_CLI
            elif provider == LLMProvider.GROK_CLI:
                self._use_cli_fallback = True
                self._cli_driver = DRIVER_GROK_CLI

        # If no API key found, try any available subscription CLI.
        if not self.api_key and not self._use_cli_fallback:
            picked = pick_available_subscription_driver()
            if picked is not None:
                logger.info(
                    "No API key found, using subscription CLI fallback (%s)",
                    picked,
                )
                self._use_cli_fallback = True
                self._cli_driver = picked
                self.provider = (
                    LLMProvider.GROK_CLI if picked == DRIVER_GROK_CLI else LLMProvider.CLAUDE_CLI
                )
            else:
                raise ValueError(
                    f"API key not found for {provider}.\n"
                    f"Options:\n"
                    f"  1. Set {api_key_env or 'ANTHROPIC_API_KEY'} environment variable\n"
                    f"  2. Install Claude Code CLI (claude.com/claude-code) or Grok Build "
                    f"CLI (`grok login`) for subscription-based local cognition\n"
                )

        # Subscription billing is a development convenience, never a
        # production dependency — a deployed app must not run its
        # cognition on a developer's personal subscription.
        if self._use_cli_fallback and os.environ.get("DAZZLE_ENV") == "production":
            raise RuntimeError(PRODUCTION_NEEDS_API_KEY_MSG)

        # Set default model
        if model:
            self.model = model
        elif provider == LLMProvider.OPENAI:
            self.model = "gpt-4-turbo"
        elif self._cli_driver == DRIVER_GROK_CLI or provider == LLMProvider.GROK_CLI:
            from dazzle.core.model_defaults import DEFAULT_GROK_JUDGMENT_MODEL

            self.model = DEFAULT_GROK_JUDGMENT_MODEL
        else:
            # Anthropic API and Claude CLI both speak Claude model IDs.
            self.model = DEFAULT_JUDGMENT_MODEL

        # Initialize provider client
        self._init_client()

    def _init_client(self) -> None:
        """Initialize provider-specific client."""
        self.client: Anthropic | OpenAI | None = None
        if self._use_cli_fallback:
            # No client needed for CLI fallback
            return

        if self.provider == LLMProvider.ANTHROPIC:
            try:
                from anthropic import Anthropic

                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "Anthropic SDK not installed. Install with: pip install anthropic"
                )
        elif self.provider == LLMProvider.OPENAI:
            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("OpenAI SDK not installed. Install with: pip install openai")

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """General-purpose LLM completion.

        Args:
            system_prompt: System instruction for the LLM.
            user_prompt: User message / content to process.

        Returns:
            The LLM's response text.
        """
        return self.complete_with_usage(system_prompt, user_prompt).text

    def complete_with_usage(self, system_prompt: str, user_prompt: str) -> Completion:
        """Completion plus provider-reported token usage (#1528).

        The metered providers (Anthropic / OpenAI) report an input/output
        split; the Claude CLI subscription path reports only a total, so
        both counts come back 0 there (subscription calls have no metered
        cost to compute anyway).
        """
        if self._use_cli_fallback:
            text, _tokens = call_subscription_cli(
                self._cli_driver or DRIVER_CLAUDE_CLI,
                user_prompt,
                system_prompt=system_prompt,
                model=self.model,
            )
            return Completion(text, 0, 0)
        elif self.provider == LLMProvider.ANTHROPIC:
            return self._call_anthropic(system_prompt, user_prompt)
        else:
            return self._call_openai(system_prompt, user_prompt)

    def analyze_spec(
        self, spec_content: str, spec_path: str, system_prompt: str | None = None
    ) -> dict[str, Any]:
        """
        Analyze a specification and return structured analysis.

        Args:
            spec_content: The specification text
            spec_path: Path to spec file (for error reporting)
            system_prompt: Optional system prompt override

        Returns:
            Parsed JSON analysis with state machines, CRUD analysis, questions, etc.

        Raises:
            ValueError: If LLM returns invalid JSON
        """
        # Build prompts
        if system_prompt is None:
            system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(spec_content, spec_path)

        logger.info(
            f"Analyzing spec via {self.provider}"
            + (f" ({self.model})" if not self._use_cli_fallback else " (CLI)")
        )

        # Call LLM
        if self._use_cli_fallback:
            response_text, _tokens = call_subscription_cli(
                self._cli_driver or DRIVER_CLAUDE_CLI,
                user_prompt,
                system_prompt=system_prompt,
                model=self.model,
            )
        elif self.provider == LLMProvider.ANTHROPIC:
            response_text = self._call_anthropic(system_prompt, user_prompt).text
        else:
            response_text = self._call_openai(system_prompt, user_prompt).text

        # Parse JSON response — strip optional markdown code fences first
        # (#1219). Claude's instruction-following defaults to fenced output
        # like ```json\n{...}\n``` even when the prompt asks for raw JSON;
        # rather than fight the LLM, normalise on read.
        response_text = _strip_code_fence(response_text)
        try:
            analysis = json.loads(response_text)
            logger.info("Successfully parsed LLM analysis")
            return analysis  # type: ignore[no-any-return]  # LLM returns unstructured JSON dict
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM output as JSON: %s", e)
            logger.debug("Raw output: %s...", response_text[:500])
            raise ValueError(f"LLM returned invalid JSON: {e}\n\nOutput: {response_text[:200]}...")

    def _build_system_prompt(self) -> str:
        """Build the system prompt for spec analysis."""
        return """You are a specification analyzer for the DAZZLE DSL-based application generator.

Your task is to analyze a product specification and extract structured information needed for code generation.

You must return ONLY valid JSON with this exact structure:

{
  "state_machines": [
    {
      "entity": "EntityName",
      "field": "field_name",
      "states": ["state1", "state2"],
      "transitions_found": [
        {
          "from": "state1",
          "to": "state2",
          "trigger": "description",
          "location": "line reference",
          "side_effects": ["effect1"],
          "conditions": ["condition1"],
          "who_can_trigger": "role or description"
        }
      ],
      "transitions_implied_but_missing": [
        {
          "from": "state1",
          "to": "state2",
          "reason": "why this transition is needed",
          "question": "clarifying question for founder"
        }
      ],
      "states_without_exit": [],
      "unreachable_states": []
    }
  ],
  "crud_analysis": [
    {
      "entity": "EntityName",
      "operations_mentioned": {
        "create": {"found": true, "location": "reference", "who": "role"},
        "read": {"found": true, "location": "reference"},
        "update": {"found": false, "question": "clarifying question"},
        "delete": {"found": true, "constraints": ["constraint1"]},
        "list": {"found": true, "filters_needed": ["filter1"]}
      },
      "missing_operations": ["update"],
      "additional_operations": [{"name": "operation_name", "description": "what it does and when it applies"}],
      "questions": []
    }
  ],
  "business_rules": [
    {
      "type": "validation|constraint|access_control|cascade|computed",
      "entity": "EntityName",
      "field": "field_name",
      "rule": "description",
      "location": "reference"
    }
  ],
  "missing_specifications": [
    {
      "type": "authentication|notifications|search|etc",
      "issue": "description",
      "locations": ["reference"],
      "questions": ["question"]
    }
  ],
  "clarifying_questions": [
    {
      "category": "State Machine|CRUD|Access Control|...",
      "priority": "high|medium|low",
      "questions": [
        {
          "q": "The question",
          "context": "Why this matters",
          "options": ["Option A", "Option B"],
          "impacts": "What this affects"
        }
      ]
    }
  ]
}

Be thorough but concise. Focus on actionable information. Provide line references when possible."""

    def _build_user_prompt(self, spec_content: str, spec_path: str) -> str:
        """Build the user prompt with spec content."""
        return f"""Analyze this specification file: {spec_path}

<specification>
{spec_content}
</specification>

Extract structured information following the JSON schema provided in the system prompt. Focus on:

1. **State Machines**: Identify entities with status/state fields and extract:
   - All states mentioned
   - Explicit transitions with triggers, conditions, and side effects
   - Implied transitions (mentioned in workflows but not formalized)
   - Missing transitions (gaps in the state machine)

2. **CRUD Completeness**: For each entity:
   - Which operations are mentioned (Create, Read, Update, Delete, List)
   - Who can perform each operation
   - Any constraints or special rules
   - Missing operations that should be clarified

3. **Business Rules**: Extract:
   - Validation rules (required fields, uniqueness, formats)
   - Access control (who can do what)
   - Cascade rules (what happens when X is deleted)
   - Computed/derived fields

4. **Missing Specifications**: Identify gaps like:
   - Authentication method not specified
   - Notification system mentioned but not detailed
   - Search/filtering requirements unclear

5. **Clarifying Questions**: Generate specific questions for:
   - Incomplete state machines
   - Missing CRUD operations
   - Ambiguous access control
   - Edge cases not covered

Return ONLY the JSON object. Do not include any explanatory text before or after the JSON."""

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> Completion:
        """Call Anthropic Claude API."""
        logger.debug("Calling Anthropic API with model %s", self.model)
        assert self.client is not None, "Client not initialized"
        client = cast("Anthropic", self.client)

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            # Extract text from response (first block is always a TextBlock for completions)
            text_block = response.content[0]
            if not hasattr(text_block, "text"):
                raise ValueError(f"Unexpected response block type: {type(text_block)}")
            usage = getattr(response, "usage", None)
            return Completion(
                str(text_block.text),
                int(getattr(usage, "input_tokens", 0) or 0),
                int(getattr(usage, "output_tokens", 0) or 0),
            )

        except Exception as e:
            logger.error("Anthropic API call failed: %s", e)
            raise

    def _call_openai(self, system_prompt: str, user_prompt: str) -> Completion:
        """Call OpenAI GPT API."""
        logger.debug("Calling OpenAI API with model %s", self.model)
        assert self.client is not None, "Client not initialized"
        client = cast("OpenAI", self.client)

        try:
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                response_format={"type": "json_object"},  # Ensure JSON response
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

            content = response.choices[0].message.content
            assert content is not None, "OpenAI returned empty response"
            usage = getattr(response, "usage", None)
            return Completion(
                content,
                int(getattr(usage, "prompt_tokens", 0) or 0),
                int(getattr(usage, "completion_tokens", 0) or 0),
            )

        except Exception as e:
            logger.error("OpenAI API call failed: %s", e)
            raise

    def estimate_cost(self, spec_size_kb: float) -> float:
        """
        Estimate API cost for analyzing a spec.

        Args:
            spec_size_kb: Specification size in kilobytes

        Returns:
            Estimated cost in USD
        """
        # Rough token estimation (1KB ≈ 750 tokens)
        estimated_input_tokens = spec_size_kb * 750
        system_prompt_tokens = 500  # Approximate
        estimated_output_tokens = 8000  # Structured analysis

        total_input = estimated_input_tokens + system_prompt_tokens
        total_output = estimated_output_tokens

        pricing = {
            LLMProvider.ANTHROPIC: {
                model: {"input": input_mtok / 1_000_000, "output": output_mtok / 1_000_000}
                for model, (input_mtok, output_mtok) in ANTHROPIC_PRICING_PER_MTOK.items()
            },
            LLMProvider.OPENAI: {
                "gpt-4-turbo": {"input": 10.00 / 1_000_000, "output": 30.00 / 1_000_000},
                "gpt-4": {"input": 30.00 / 1_000_000, "output": 60.00 / 1_000_000},
            },
        }

        # Get rates for current model
        provider_pricing = pricing.get(self.provider, {})
        model_pricing = provider_pricing.get(self.model)

        if not model_pricing:
            logger.warning(
                "No pricing info for %s/%s, using default estimates",
                self.provider,
                self.model,
            )
            # Default to current Sonnet-tier pricing
            model_pricing = pricing[LLMProvider.ANTHROPIC][DEFAULT_JUDGMENT_MODEL]

        cost = total_input * model_pricing["input"] + total_output * model_pricing["output"]

        return cost
