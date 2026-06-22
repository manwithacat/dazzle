"""REST routes for LLM intent execution.

Prefix: ``/_dazzle/llm`` — matches other internal routes
(``/_dazzle/channels``, ``/_dazzle/services``).

#1454 note: the bare ``POST /execute/{intent_name}`` endpoint has been
permanently removed.  AI execution is governed exclusively via:
  (a) an entity ``llm_intent`` trigger, or
  (b) a process ``llm_intent`` step.
"""

from typing import Any

from fastapi import APIRouter

from dazzle.http.runtime.llm_executor import LLMIntentExecutor


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
