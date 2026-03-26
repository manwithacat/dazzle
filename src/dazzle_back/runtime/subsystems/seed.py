"""Seed runner subsystem.

Auto-seeds reference data from entity ``seed_template`` declarations at
application startup (v0.38.0, #428).
"""

import logging

from dazzle_back.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class SeedSubsystem:
    name = "seed"

    def startup(self, ctx: SubsystemContext) -> None:
        has_seeds = any(e.seed_template for e in ctx.appspec.domain.entities)
        if not has_seeds:
            return

        appspec = ctx.appspec
        repositories = ctx.repositories

        @ctx.app.on_event("startup")
        async def _run_seeds() -> None:
            try:
                from dazzle_back.runtime.seed_runner import run_seed_templates

                count = await run_seed_templates(appspec, repositories)
                if count:
                    logger.info("Seed runner: %d reference data row(s) ensured", count)
            except Exception:
                logger.warning("Seed runner failed", exc_info=True)

    def shutdown(self) -> None:
        pass
