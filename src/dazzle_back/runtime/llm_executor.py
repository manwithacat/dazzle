"""LLM intent executor.

Connects DSL-declared ``llm_intent`` blocks to the ``LLMAPIClient`` at
runtime, producing ``ExecutionResult`` values and optionally recording
``AIJob`` entities for cost tracking.
"""

from __future__ import annotations  # required: forward reference

import asyncio
import logging
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import jinja2

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.llm import LLMIntentSpec, LLMModelSpec, RetryBackoff
from dazzle.core.ir.llm import LLMProvider as IRProvider
from dazzle.llm.api_client import LLMAPIClient
from dazzle.llm.api_client import LLMProvider as ClientProvider

logger = logging.getLogger(__name__)

# IR provider → api_client provider mapping
_PROVIDER_MAP: dict[IRProvider, ClientProvider] = {
    IRProvider.ANTHROPIC: ClientProvider.ANTHROPIC,
    IRProvider.OPENAI: ClientProvider.OPENAI,
    IRProvider.GOOGLE: ClientProvider.OPENAI,  # OpenAI-compatible endpoint
    IRProvider.LOCAL: ClientProvider.CLAUDE_CLI,
}

# IR provider → default env var for API key
_API_KEY_ENV: dict[IRProvider, str] = {
    IRProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    IRProvider.OPENAI: "OPENAI_API_KEY",
    IRProvider.GOOGLE: "GOOGLE_API_KEY",
}


@dataclass
class ExecutionResult:
    """Result of executing an LLM intent."""

    success: bool
    output: str | None = None
    job_id: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: Decimal | None = None
    duration_ms: int = 0
    error: str | None = None


class LLMIntentExecutor:
    """Execute LLM intents declared in the DSL.

    Follows the same dependency-injection pattern as ``IntegrationExecutor``:
    the caller provides the ``AppSpec`` and an optional service for persisting
    ``AIJob`` records.
    """

    def __init__(self, appspec: AppSpec, ai_job_service: Any | None = None) -> None:
        self._appspec = appspec
        self._ai_job_service = ai_job_service
        # Pre-index for O(1) lookup
        self._intents: dict[str, LLMIntentSpec] = {i.name: i for i in appspec.llm_intents}
        self._models: dict[str, LLMModelSpec] = {m.name: m for m in appspec.llm_models}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_model(self, intent: LLMIntentSpec) -> LLMModelSpec:
        """Resolve the model for an intent via explicit ref or config default."""
        if intent.model_ref:
            model = self._models.get(intent.model_ref)
            if model:
                return model
            raise ValueError(
                f"Intent '{intent.name}' references unknown model '{intent.model_ref}'"
            )

        # Fall back to llm_config.default_model
        cfg = self._appspec.llm_config
        if cfg and cfg.default_model:
            model = self._models.get(cfg.default_model)
            if model:
                return model
            raise ValueError(
                f"llm_config.default_model '{cfg.default_model}' not found in llm_models"
            )

        raise ValueError(
            f"Intent '{intent.name}' has no model_ref and no default_model in llm_config"
        )

    @staticmethod
    def _render_prompt(template_str: str, input_data: dict[str, Any]) -> str:
        """Render a Jinja2 prompt template with ``input`` in the namespace."""
        env = jinja2.Environment(undefined=jinja2.StrictUndefined)  # nosec B701 — prompt rendering, not HTML
        tpl = env.from_string(template_str)
        return tpl.render(input=input_data)

    @staticmethod
    def _build_client(model: LLMModelSpec) -> LLMAPIClient:
        """Build an ``LLMAPIClient`` from an IR model spec."""
        provider = _PROVIDER_MAP.get(model.provider, ClientProvider.ANTHROPIC)
        api_key_env = _API_KEY_ENV.get(model.provider)
        return LLMAPIClient(
            provider=provider,
            model=model.model_id,
            api_key_env=api_key_env,
            max_tokens=model.max_tokens,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        intent_name: str,
        input_data: dict[str, Any],
        *,
        user_id: str | None = None,
    ) -> ExecutionResult:
        """Execute a named intent with the given input data."""
        intent = self._intents.get(intent_name)
        if not intent:
            return ExecutionResult(success=False, error=f"Unknown intent: {intent_name}")

        # Resolve model
        try:
            model = self._resolve_model(intent)
        except ValueError as exc:
            return ExecutionResult(success=False, error=str(exc))

        # Render prompt
        try:
            rendered = self._render_prompt(intent.prompt_template, input_data)
        except jinja2.TemplateError as exc:
            return ExecutionResult(success=False, error=f"Prompt template error: {exc}")

        # Build client
        try:
            client = self._build_client(model)
        except (ValueError, ImportError) as exc:
            return ExecutionResult(success=False, error=f"Client error: {exc}")

        # Determine retry parameters
        max_attempts = 1
        initial_delay_s = 1.0
        max_delay_s = 30.0
        backoff = RetryBackoff.EXPONENTIAL
        if intent.retry:
            max_attempts = intent.retry.max_attempts
            initial_delay_s = intent.retry.initial_delay_ms / 1000.0
            max_delay_s = intent.retry.max_delay_ms / 1000.0
            backoff = intent.retry.backoff

        system_prompt = intent.description or ""
        last_error: str | None = None

        for attempt in range(1, max_attempts + 1):
            t0 = time.monotonic()
            try:
                output = await asyncio.wait_for(
                    asyncio.to_thread(client.complete, system_prompt, rendered),
                    timeout=intent.timeout_seconds,
                )
                duration_ms = int((time.monotonic() - t0) * 1000)

                result = ExecutionResult(
                    success=True,
                    output=output,
                    duration_ms=duration_ms,
                )

                # Record AIJob if service available
                await self._record_job(intent, model, result, user_id=user_id)

                return result

            except TimeoutError:
                last_error = f"Timeout after {intent.timeout_seconds}s"
            except Exception as exc:
                last_error = str(exc)

            # Sleep before retry (unless last attempt)
            if attempt < max_attempts:
                if backoff == RetryBackoff.LINEAR:
                    delay = initial_delay_s * attempt
                else:
                    delay = initial_delay_s * (2 ** (attempt - 1))
                delay = min(delay, max_delay_s)
                logger.info(
                    "Intent '%s' attempt %d failed, retrying in %.1fs", intent_name, attempt, delay
                )
                await asyncio.sleep(delay)

        duration_ms = int((time.monotonic() - t0) * 1000)
        result = ExecutionResult(
            success=False,
            error=last_error,
            duration_ms=duration_ms,
        )
        await self._record_job(intent, model, result, user_id=user_id, failed=True)
        return result

    async def _record_job(
        self,
        intent: LLMIntentSpec,
        model: LLMModelSpec,
        result: ExecutionResult,
        *,
        user_id: str | None = None,
        failed: bool = False,
    ) -> None:
        """Record an AIJob via the service if available."""
        if not self._ai_job_service:
            return
        try:
            job_data = {
                "intent": intent.name,
                "model": model.model_id,
                "provider": model.provider.value,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "cost_usd": str(result.cost_usd) if result.cost_usd else None,
                "duration_ms": result.duration_ms,
                "status": "failed" if failed else "completed",
                "user_id": user_id,
                "error_message": result.error,
            }
            resp = await self._ai_job_service.execute(action="create", data=job_data)
            if resp and isinstance(resp, dict):
                result.job_id = str(resp.get("id", ""))
        except Exception:
            logger.warning("Failed to record AIJob for intent '%s'", intent.name, exc_info=True)

    def list_intents(self) -> list[dict[str, Any]]:
        """Return serialisable summaries of all declared intents."""
        return [
            {
                "name": i.name,
                "title": i.title,
                "description": i.description,
                "model_ref": i.model_ref,
                "timeout_seconds": i.timeout_seconds,
                "has_retry": i.retry is not None,
                "has_pii_policy": i.pii is not None and i.pii.scan,
            }
            for i in self._appspec.llm_intents
        ]

    def list_models(self) -> list[dict[str, Any]]:
        """Return serialisable summaries of all declared models."""
        return [
            {
                "name": m.name,
                "title": m.title,
                "provider": m.provider.value,
                "model_id": m.model_id,
                "tier": m.tier.value,
                "max_tokens": m.max_tokens,
            }
            for m in self._appspec.llm_models
        ]
