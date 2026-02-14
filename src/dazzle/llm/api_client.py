"""
API client for LLM providers (Anthropic, OpenAI).

Handles authentication, request formatting, and response parsing.
Supports fallback to Claude CLI for users with Claude subscriptions.
"""

import json
import logging
import os
import shutil
import subprocess
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


def _claude_cli_available() -> bool:
    """Check if Claude CLI is available."""
    return shutil.which("claude") is not None


def _call_claude_cli(prompt: str, system_prompt: str | None = None) -> str:
    """
    Call Claude via CLI (uses subscription, no API key needed).

    Args:
        prompt: The user prompt
        system_prompt: Optional system prompt

    Returns:
        Claude's response text
    """
    cmd = ["claude", "--print"]

    if system_prompt:
        cmd.extend(["--system", system_prompt])

    cmd.append(prompt)

    logger.info("Calling Claude via CLI (using subscription)")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed: {result.stderr}")

    return result.stdout


class LLMProvider(StrEnum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    CLAUDE_CLI = "claude_cli"  # Fallback using Claude CLI (subscription)


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

        # Get API key
        self.api_key: str | None = None
        self._use_cli_fallback = False

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

        # If no API key found, try Claude CLI fallback
        if not self.api_key and not self._use_cli_fallback:
            if _claude_cli_available():
                logger.info("No API key found, using Claude CLI fallback (subscription-based)")
                self._use_cli_fallback = True
                self.provider = LLMProvider.CLAUDE_CLI
            else:
                raise ValueError(
                    f"API key not found for {provider}.\n"
                    f"Options:\n"
                    f"  1. Set {api_key_env or 'ANTHROPIC_API_KEY'} environment variable\n"
                    f"  2. Install Claude CLI: https://claude.ai/download\n"
                    f"     (Uses your Claude subscription, no API key needed)"
                )

        # Set default model
        if model:
            self.model = model
        else:
            if provider == LLMProvider.ANTHROPIC:
                self.model = "claude-3-5-sonnet-20241022"
            else:
                self.model = "gpt-4-turbo"

        # Initialize provider client
        self._init_client()

    def _init_client(self) -> None:
        """Initialize provider-specific client."""
        # Type as Any since client can be Anthropic, OpenAI, or None
        self.client: Any = None
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
        if self._use_cli_fallback:
            return _call_claude_cli(user_prompt, system_prompt)
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
            response_text = _call_claude_cli(user_prompt, system_prompt)
        elif self.provider == LLMProvider.ANTHROPIC:
            response_text = self._call_anthropic(system_prompt, user_prompt)
        else:
            response_text = self._call_openai(system_prompt, user_prompt)

        # Parse JSON response
        try:
            analysis = json.loads(response_text)
            logger.info("Successfully parsed LLM analysis")
            return analysis  # type: ignore[no-any-return]  # LLM returns unstructured JSON dict
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM output as JSON: {e}")
            logger.debug(f"Raw output: {response_text[:500]}...")
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
      "additional_operations": [],
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

    def _call_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        """Call Anthropic Claude API."""
        logger.debug(f"Calling Anthropic API with model {self.model}")
        assert self.client is not None, "Client not initialized"

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            # Extract text from response (first block is always a TextBlock for completions)
            text_block = response.content[0]
            if hasattr(text_block, "text"):
                return str(text_block.text)
            raise ValueError(f"Unexpected response block type: {type(text_block)}")

        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}")
            raise

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI GPT API."""
        logger.debug(f"Calling OpenAI API with model {self.model}")
        assert self.client is not None, "Client not initialized"

        try:
            response = self.client.chat.completions.create(
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
            result: str = content
            return result

        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
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

        # Pricing (as of 2024)
        pricing = {
            LLMProvider.ANTHROPIC: {
                "claude-3-5-sonnet-20241022": {
                    "input": 3.00 / 1_000_000,
                    "output": 15.00 / 1_000_000,
                },
                "claude-3-sonnet-20240229": {
                    "input": 3.00 / 1_000_000,
                    "output": 15.00 / 1_000_000,
                },
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
                f"No pricing info for {self.provider}/{self.model}, using default estimates"
            )
            # Default to Claude Sonnet pricing
            model_pricing = pricing[LLMProvider.ANTHROPIC]["claude-3-5-sonnet-20241022"]

        cost = total_input * model_pricing["input"] + total_output * model_pricing["output"]

        return cost
