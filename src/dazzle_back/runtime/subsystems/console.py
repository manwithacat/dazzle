"""Founder Console subsystem.

Mounts the /_console/ control plane routes for spec versioning, deploy
history, and rollback management (v0.26.0).
"""

from __future__ import annotations

import logging

from dazzle_back.runtime.subsystems import SubsystemContext

logger = logging.getLogger("dazzle.server")


class ConsoleSubsystem:
    name = "console"

    def startup(self, ctx: SubsystemContext) -> None:
        if not ctx.config.enable_console:
            return

        try:
            from dazzle_back.runtime.console_routes import create_console_routes
            from dazzle_back.runtime.deploy_history import DeployHistoryStore
            from dazzle_back.runtime.deploy_routes import create_deploy_routes
            from dazzle_back.runtime.ops_database import OpsDatabase
            from dazzle_back.runtime.rollback_manager import RollbackManager
            from dazzle_back.runtime.spec_versioning import SpecVersionStore

            if not ctx.config.database_url:
                logger.info("Console requires DATABASE_URL — skipping")
                return

            ops_db = OpsDatabase(database_url=ctx.config.database_url)
            spec_version_store = SpecVersionStore(ops_db)
            deploy_history_store = DeployHistoryStore(ops_db)

            spec_version_store.save_version(ctx.appspec)

            rollback_manager = RollbackManager(
                spec_version_store=spec_version_store,
                deploy_history_store=deploy_history_store,
            )

            console_router = create_console_routes(
                ops_db=ops_db,
                appspec=ctx.appspec,
                spec_version_store=spec_version_store,
                deploy_history_store=deploy_history_store,
            )
            ctx.app.include_router(console_router)

            deploy_router = create_deploy_routes(
                deploy_history_store=deploy_history_store,
                spec_version_store=spec_version_store,
                rollback_manager=rollback_manager,
                appspec=ctx.appspec,
            )
            ctx.app.include_router(deploy_router)

            logger.info("Founder Console initialized at /_console/")

        except ImportError as exc:
            logger.debug("Console not available: %s", exc)
        except Exception as exc:
            logger.warning("Failed to init console: %s", exc)

    def shutdown(self) -> None:
        pass
