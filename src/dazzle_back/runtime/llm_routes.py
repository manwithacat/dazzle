"""REST routes for LLM intent execution.

Prefix: ``/_dazzle/llm`` — matches other internal routes
(``/_dazzle/channels``, ``/_dazzle/services``).
"""

from __future__ import annotations  # required: forward reference

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


class AsyncJobResponse(BaseModel):
    """Response for async job submission."""

    job_id: str
    status: str = "pending"


def create_llm_routes(
    executor: LLMIntentExecutor,
    queue: Any | None = None,
    ai_job_service: Any | None = None,
) -> APIRouter:
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
        intent_name: str,
        request: IntentExecuteRequest,
        async_mode: bool = False,
    ) -> IntentExecuteResponse | AsyncJobResponse:
        if async_mode and queue is not None:
            job_id = await queue.submit(
                intent_name,
                request.input_data,
                user_id=request.user_id,
            )
            return AsyncJobResponse(job_id=job_id)

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

    @router.get("/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        """Poll job status by ID."""
        if not ai_job_service:
            return {"error": "AIJob service not available", "status": "unknown"}
        try:
            import asyncio

            result = await asyncio.to_thread(
                ai_job_service.execute,
                action="read",
                record_id=job_id,
            )
            if result:
                data: dict[str, Any] = dict(result) if not isinstance(result, dict) else result
                return data
            return {"job_id": job_id, "status": "not_found"}
        except Exception:
            return {"job_id": job_id, "status": "not_found"}

    return router
