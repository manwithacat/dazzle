"""Seed runner subsystem.

Auto-seeds reference data from entity ``seed_template`` declarations at
application startup (v0.38.0, #428).
"""

import logging

from dazzle.http.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class SeedSubsystem:
    name = "seed"

    def startup(self, ctx: SubsystemContext) -> None:
        has_seeds = any(e.seed_template for e in ctx.appspec.domain.entities)
        if not has_seeds:
            return

        appspec = ctx.appspec
        repositories = ctx.repositories

        from dazzle.http.runtime.lifespan_hooks import register_lifespan_hook

        async def _run_seeds() -> None:
            try:
                from dazzle.http.runtime.seed_runner import run_seed_templates

                count = await run_seed_templates(appspec, repositories)
                if count:
                    logger.info("Seed runner: %d reference data row(s) ensured", count)
            except Exception:
                logger.warning("Seed runner failed", exc_info=True)

        register_lifespan_hook(ctx.app, startup=_run_seeds)

    def shutdown(self) -> None:
        pass
