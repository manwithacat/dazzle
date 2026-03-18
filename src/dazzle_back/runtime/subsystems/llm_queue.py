"""LLM intent executor subsystem.

Initialises the LLM intent executor, job queue, trigger matcher, and REST
routes for LLM-backed field classification and intent processing (v0.38.0).
"""

from __future__ import annotations

import logging
from typing import Any

from dazzle_back.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class LLMQueueSubsystem:
    name = "llm_queue"

    def __init__(self) -> None:
        self._queue: Any | None = None

    def startup(self, ctx: SubsystemContext) -> None:
        if not ctx.appspec.llm_config:
            return
        if not ctx.appspec.llm_intents:
            return

        try:
            from dazzle_back.runtime.llm_executor import LLMIntentExecutor
            from dazzle_back.runtime.llm_queue import LLMJobQueue
            from dazzle_back.runtime.llm_routes import create_llm_routes
            from dazzle_back.runtime.llm_trigger import LLMTriggerMatcher

            ai_job_service = ctx.services.get("AIJob")
            executor = LLMIntentExecutor(ctx.appspec, ai_job_service=ai_job_service)

            llm_config = ctx.appspec.llm_config
            queue = LLMJobQueue(
                executor=executor,
                ai_job_service=ai_job_service,
                event_bus=None,
                rate_limits=llm_config.rate_limits if llm_config else None,
                concurrency=llm_config.concurrency if llm_config else None,
            )
            self._queue = queue
            ctx.llm_queue = queue

            # Register entity event trigger matcher
            has_triggers = any(i.triggers for i in ctx.appspec.llm_intents)
            if has_triggers and ctx.event_framework is not None:
                matcher = LLMTriggerMatcher(ctx.appspec, queue, services=ctx.services)
                if hasattr(ctx.event_framework, "add_handler"):
                    ctx.event_framework.add_handler(matcher.handle_event)

            router = create_llm_routes(executor, queue=queue, ai_job_service=ai_job_service)
            ctx.app.include_router(router)

            _queue = queue

            @ctx.app.on_event("startup")
            async def _startup_llm() -> None:
                await _queue.start()

            @ctx.app.on_event("shutdown")
            async def _shutdown_llm() -> None:
                await _queue.shutdown()

        except Exception as exc:
            logger.warning("Failed to init LLM queue subsystem: %s", exc)

    def shutdown(self) -> None:
        pass  # handled by FastAPI on_event("shutdown")
