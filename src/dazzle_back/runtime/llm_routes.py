"""REST routes for LLM intent execution.

Prefix: ``/_dazzle/llm`` — matches other internal routes
(``/_dazzle/channels``, ``/_dazzle/services``).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from dazzle_back.runtime.llm_executor import ExecutionResult, LLMIntentExecutor


class IntentExecuteRequest(BaseModel):
    """Request body for ``POST /execute/{intent_name}``."""

    input_data: dict[str, Any] = {}
    user_id: str | None = None


class IntentExecuteResponse(BaseModel):
    """Response body mirroring ``ExecutionResult``."""

    success: bool
    output: str | None = None
    job_id: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: str | None = None
    duration_ms: int = 0
    error: str | None = None


def create_llm_routes(executor: LLMIntentExecutor) -> APIRouter:
    """Create LLM intent execution routes."""
    router = APIRouter(prefix="/_dazzle/llm", tags=["LLM"])

    @router.get("/intents")
    async def list_intents() -> list[dict[str, Any]]:
        return executor.list_intents()

    @router.get("/models")
    async def list_models() -> list[dict[str, Any]]:
        return executor.list_models()

    @router.post("/execute/{intent_name}", response_model=IntentExecuteResponse)
    async def execute_intent(
        intent_name: str, request: IntentExecuteRequest
    ) -> IntentExecuteResponse:
        result: ExecutionResult = await executor.execute(
            intent_name, request.input_data, user_id=request.user_id
        )
        return IntentExecuteResponse(
            success=result.success,
            output=result.output,
            job_id=result.job_id,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=str(result.cost_usd) if result.cost_usd else None,
            duration_ms=result.duration_ms,
            error=result.error,
        )

    return router
