"""
API client for LLM providers (Anthropic, OpenAI, Vertex / Gemini).

Handles authentication, request formatting, and response parsing.
Supports fallback to Claude CLI for users with Claude subscriptions,
OpenAI-compatible base URLs (Ollama, Azure OpenAI, proxies), and
Google Vertex AI via ADC (``google-genai``, same shape as Badger).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from dazzle.core.model_defaults import (
    ANTHROPIC_PRICING_PER_MTOK,
    DEFAULT_GROK_JUDGMENT_MODEL,
    DEFAULT_JUDGMENT_MODEL,
)
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

# Vertex defaults — mirror Badger's env contract so the same ADC setup works.
_DEFAULT_VERTEX_LOCATION = "global"
_DEFAULT_VERTEX_MODEL = "gemini-2.5-flash"


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
    """Supported LLM providers (client runtime ids)."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"  # Vertex AI Gemini via google-genai + ADC
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

    # #1631 — analyze-spec must not hang indefinitely (Run A hang was the
    # sibling of bootstrap pollution). Loud timeout > infinite wait.
    DEFAULT_TIMEOUT_S = 90.0

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.ANTHROPIC,
        model: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16000,
        use_prompt_caching: bool = True,
        timeout: float | None = None,
        base_url: str | None = None,
        project: str | None = None,
        location: str | None = None,
    ):
        """
        Initialize LLM API client.

        Args:
            provider: LLM provider (anthropic, openai, google, …)
            model: Model name (defaults based on provider)
            api_key: API key (if not provided, read from env)
            api_key_env: Environment variable name for API key
            temperature: Temperature for sampling (0.0 = deterministic)
            max_tokens: Maximum tokens in response
            use_prompt_caching: Use prompt caching if supported
            timeout: HTTP/SDK timeout in seconds (default 90; #1631 fail loud)
            base_url: OpenAI-compatible API base (openai provider only)
            project: GCP project for Vertex (google provider)
            location: Vertex Gen AI location (google provider)
        """
        self.provider = provider
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_prompt_caching = use_prompt_caching
        self.timeout = float(timeout) if timeout is not None else self.DEFAULT_TIMEOUT_S
        self.base_url = (base_url or "").strip() or None
        self.project = (project or "").strip() or None
        self.location = (location or "").strip() or None
        # Unique identifier for this client instance — correlates LLM
        # invocations with telemetry/proposals. Consumed by the fitness
        # investigator runner (see LlmClient Protocol). Generated once per
        # client so multiple invocations from the same run share the ID.
        self.run_id: str = uuid.uuid4().hex

        # Get API key / subscription CLI fallback (extracted for CC ceiling).
        self.api_key: str | None = None
        self._use_cli_fallback = False
        # Concrete subscription driver when using CLI fallback (claude-cli / grok-cli).
        self._cli_driver: str | None = None
        # Vertex holds a google-genai Client; not Anthropic/OpenAI SDK.
        self._vertex_client: Any | None = None
        self._resolve_credentials(provider, api_key, api_key_env)

        # Subscription billing is a development convenience, never a
        # production dependency — a deployed app must not run its
        # cognition on a developer's personal subscription.
        if self._use_cli_fallback and os.environ.get("DAZZLE_ENV") == "production":
            raise RuntimeError(PRODUCTION_NEEDS_API_KEY_MSG)

        self.model = self._default_model(model, provider)
        self._init_client()

    def _resolve_credentials(
        self,
        provider: LLMProvider,
        api_key: str | None,
        api_key_env: str | None,
    ) -> None:
        """Populate api_key / CLI fallback from args, env, or subscription CLI."""
        if provider == LLMProvider.GOOGLE:
            self._resolve_google_credentials(api_key, api_key_env)
            return

        self._resolve_key_or_cli(provider, api_key, api_key_env)
        if self.api_key or self._use_cli_fallback:
            return

        # OpenAI-compatible local servers (Ollama, etc.) often ignore the key
        # but the SDK requires a non-empty string.
        if provider == LLMProvider.OPENAI and self.base_url:
            self.api_key = "local"
            return

        self._fallback_to_subscription_cli(api_key_env)

    def _resolve_google_credentials(
        self,
        api_key: str | None,
        api_key_env: str | None,
    ) -> None:
        """Vertex uses ADC (IAM); optional GOOGLE_API_KEY for AI Studio only."""
        if api_key:
            self.api_key = api_key
        elif api_key_env:
            self.api_key = os.environ.get(api_key_env)
        else:
            self.api_key = os.environ.get("GOOGLE_API_KEY")

        if not self.project:
            self.project = (
                os.environ.get("VERTEX_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT") or None
            )
        if not self.location:
            self.location = (
                os.environ.get("VERTEX_LOCATION")
                or os.environ.get("GOOGLE_CLOUD_LOCATION")
                or _DEFAULT_VERTEX_LOCATION
            )
        if self.project or self.api_key:
            return
        raise ValueError(
            "Vertex / Google provider needs a GCP project (ADC) or API key.\n"
            "Options:\n"
            "  1. Set project on llm_model (project: my-gcp-project)\n"
            "  2. export GOOGLE_CLOUD_PROJECT=… (or VERTEX_PROJECT)\n"
            "  3. gcloud auth application-default login\n"
            "  4. (dev only) GOOGLE_API_KEY for Gemini Developer API\n"
            "See docs/reference/llm-drivers.md (Vertex section)."
        )

    def _resolve_key_or_cli(
        self,
        provider: LLMProvider,
        api_key: str | None,
        api_key_env: str | None,
    ) -> None:
        """Resolve metered API keys or explicit subscription-CLI providers."""
        if api_key:
            self.api_key = api_key
        elif api_key_env:
            self.api_key = os.environ.get(api_key_env)
        elif provider == LLMProvider.ANTHROPIC:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        elif provider == LLMProvider.OPENAI:
            self.api_key = os.environ.get("OPENAI_API_KEY")
        elif provider == LLMProvider.CLAUDE_CLI:
            self._use_cli_fallback = True
            self._cli_driver = DRIVER_CLAUDE_CLI
        elif provider == LLMProvider.GROK_CLI:
            self._use_cli_fallback = True
            self._cli_driver = DRIVER_GROK_CLI

    def _fallback_to_subscription_cli(self, api_key_env: str | None) -> None:
        """When no key is set, use a local subscription CLI or fail loudly."""
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
            return
        raise ValueError(
            "API key not found for LLM client.\n"
            "Options:\n"
            f"  1. Set {api_key_env or 'ANTHROPIC_API_KEY'} environment variable\n"
            "  2. Install Claude Code CLI (claude.com/claude-code) or Grok Build "
            "CLI (`grok login`) for subscription-based local cognition\n"
            "  3. For OpenAI-compatible local servers: set base_url on llm_model\n"
        )

    def _default_model(self, model: str | None, provider: LLMProvider) -> str:
        if model:
            return model
        if provider == LLMProvider.OPENAI:
            return "gpt-4-turbo"
        if provider == LLMProvider.GOOGLE:
            return os.environ.get("VERTEX_MODEL") or _DEFAULT_VERTEX_MODEL
        if self._cli_driver == DRIVER_GROK_CLI or provider == LLMProvider.GROK_CLI:
            return DEFAULT_GROK_JUDGMENT_MODEL
        # Anthropic API and Claude CLI both speak Claude model IDs.
        return DEFAULT_JUDGMENT_MODEL

    def _init_client(self) -> None:
        """Initialize provider-specific client."""
        self.client: Anthropic | OpenAI | None = None
        if self._use_cli_fallback:
            # No client needed for CLI fallback
            return

        if self.provider == LLMProvider.ANTHROPIC:
            try:
                from anthropic import Anthropic

                # timeout= fails loud rather than hanging analyze-spec (#1631)
                self.client = Anthropic(api_key=self.api_key, timeout=self.timeout)
            except ImportError:
                raise ImportError(
                    "Anthropic SDK not installed. Install with: pip install anthropic"
                )
        elif self.provider == LLMProvider.OPENAI:
            try:
                from openai import OpenAI

                kwargs: dict[str, Any] = {
                    "api_key": self.api_key,
                    "timeout": self.timeout,
                }
                if self.base_url:
                    kwargs["base_url"] = self.base_url
                self.client = OpenAI(**kwargs)
            except ImportError:
                raise ImportError("OpenAI SDK not installed. Install with: pip install openai")
        elif self.provider == LLMProvider.GOOGLE:
            self._init_vertex_client()

    def _init_vertex_client(self) -> None:
        """Build a google-genai Client for Vertex (ADC) or AI Studio (api key).

        Shape borrowed from Badger ``scripts/vertex_smoke.py``:
        ``genai.Client(vertexai=True, project=…, location=…)``.
        """
        try:
            from google import genai
        except ImportError as exc:
            raise ImportError(
                "google-genai is required for provider: google (Vertex AI). "
                "Install with: pip install 'dazzle-dsl[llm]'  (or google-genai)"
            ) from exc

        if self.project:
            # Enterprise / Vertex path — IAM via Application Default Credentials.
            self._vertex_client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location or _DEFAULT_VERTEX_LOCATION,
            )
            logger.debug(
                "Vertex client project=%s location=%s model=%s",
                self.project,
                self.location or _DEFAULT_VERTEX_LOCATION,
                self.model,
            )
        elif self.api_key:
            # Gemini Developer API (AI Studio) — personal experiments only.
            self._vertex_client = genai.Client(api_key=self.api_key)
            logger.debug("Gemini Developer API client (api_key) model=%s", self.model)
        else:
            raise ValueError("Vertex client needs project=… (ADC) or GOOGLE_API_KEY (AI Studio)")

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """General-purpose LLM completion.

        Args:
            system_prompt: System instruction for the LLM.
            user_prompt: User message / content to process.

        Returns:
            The LLM's response text.
        """
        return self.complete_with_usage(system_prompt, user_prompt).text

    def complete_with_usage(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        force_json: bool = False,
    ) -> Completion:
        """Completion plus provider-reported token usage (#1528).

        The metered providers (Anthropic / OpenAI / Vertex) report an
        input/output split when the SDK surfaces usage; the Claude CLI
        subscription path reports only a total, so both counts come back
        0 there (subscription calls have no metered cost to compute).

        ``force_json`` is for analyze-spec only — general ``llm_intent``
        tasking must not require ``response_format=json_object`` (many
        OpenAI-compatible servers reject it).
        """
        if self._use_cli_fallback:
            text, _tokens = call_subscription_cli(
                self._cli_driver or DRIVER_CLAUDE_CLI,
                user_prompt,
                system_prompt=system_prompt,
                model=self.model,
            )
            return Completion(text, 0, 0)
        if self.provider == LLMProvider.ANTHROPIC:
            return self._call_anthropic(system_prompt, user_prompt)
        if self.provider == LLMProvider.GOOGLE:
            return self._call_vertex(system_prompt, user_prompt)
        return self._call_openai(system_prompt, user_prompt, force_json=force_json)

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

        # Call LLM (force JSON for OpenAI-compatible analyze path only)
        if self._use_cli_fallback:
            response_text, _tokens = call_subscription_cli(
                self._cli_driver or DRIVER_CLAUDE_CLI,
                user_prompt,
                system_prompt=system_prompt,
                model=self.model,
            )
        elif self.provider == LLMProvider.ANTHROPIC:
            response_text = self._call_anthropic(system_prompt, user_prompt).text
        elif self.provider == LLMProvider.GOOGLE:
            response_text = self._call_vertex(system_prompt, user_prompt).text
        else:
            response_text = self._call_openai(system_prompt, user_prompt, force_json=True).text

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

    def _call_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        force_json: bool = False,
    ) -> Completion:
        """Call OpenAI or any OpenAI-compatible chat completions API."""
        logger.debug(
            "Calling OpenAI-compatible API model=%s base_url=%s force_json=%s",
            self.model,
            self.base_url or "(default)",
            force_json,
        )
        assert self.client is not None, "Client not initialized"
        client = cast("OpenAI", self.client)

        try:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            # analyze-spec only. General llm_intent tasking and many
            # OpenAI-compatible servers (Ollama, vLLM) reject or ignore
            # response_format=json_object.
            if force_json:
                kwargs["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**kwargs)

            content = response.choices[0].message.content
            assert content is not None, "OpenAI returned empty response"
            usage = getattr(response, "usage", None)
            return Completion(
                content,
                int(getattr(usage, "prompt_tokens", 0) or 0),
                int(getattr(usage, "completion_tokens", 0) or 0),
            )

        except Exception as e:
            logger.error("OpenAI-compatible API call failed: %s", e)
            raise

    def _call_vertex(self, system_prompt: str, user_prompt: str) -> Completion:
        """Call Vertex AI / Gemini via google-genai (Badger-compatible shape)."""
        logger.debug(
            "Calling Vertex/Gemini model=%s project=%s location=%s",
            self.model,
            self.project,
            self.location,
        )
        if self._vertex_client is None:
            raise RuntimeError("Vertex client not initialized")

        try:
            from google.genai import types
        except ImportError:
            types = None  # type: ignore[assignment]

        try:
            config: dict[str, Any] = {
                "temperature": self.temperature,
                "max_output_tokens": self.max_tokens,
                "system_instruction": system_prompt,
            }
            if types is not None:
                gen_config = types.GenerateContentConfig(**config)
            else:
                gen_config = config

            response = self._vertex_client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=gen_config,
            )
            text = (getattr(response, "text", None) or "").strip()
            if not text:
                raise ValueError("Vertex/Gemini returned empty response")

            # Usage metadata shape varies by SDK version; be defensive.
            tokens_in = 0
            tokens_out = 0
            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                tokens_in = int(
                    getattr(usage, "prompt_token_count", 0)
                    or getattr(usage, "input_tokens", 0)
                    or 0
                )
                tokens_out = int(
                    getattr(usage, "candidates_token_count", 0)
                    or getattr(usage, "output_tokens", 0)
                    or 0
                )
            return Completion(text, tokens_in, tokens_out)

        except Exception as e:
            logger.error("Vertex/Gemini API call failed: %s", e)
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
