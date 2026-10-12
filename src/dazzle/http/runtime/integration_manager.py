"""Integration manager — integration executor setup.

Houses ``IntegrationManager``, previously defined inline in ``server.py``.
"""

import logging
from typing import TYPE_CHECKING, Any

from dazzle.core.ir import AppSpec

if TYPE_CHECKING:
    from fastapi import FastAPI

    from dazzle.http.runtime.pg_backend import PostgresBackend

logger = logging.getLogger(__name__)


# =============================================================================
# IntegrationManager
# =============================================================================


class IntegrationManager:
    """Manages the integration executor for DazzleBackendApp."""

    def __init__(
        self,
        *,
        app: "FastAPI",
        appspec: AppSpec,
        db_manager: "PostgresBackend | None",
        fragment_sources: dict[str, dict[str, Any]],
    ) -> None:
        self._app = app
        self._appspec = appspec
        self._db_manager = db_manager
        self._fragment_sources = fragment_sources
        self.integration_executor: Any | None = None

    def init_integration_executor(self) -> None:
        """Initialize integration action executor (v0.20.0)."""
        if not self._app:
            return

        try:
            from dazzle.http.runtime.integration_executor import IntegrationExecutor

            has_actions = False
            for integration in self._appspec.integrations:
                if getattr(integration, "actions", []):
                    has_actions = True
                    break

            if not has_actions:
                return

            self.integration_executor = IntegrationExecutor(
                app_spec=self._appspec,
                fragment_sources=self._fragment_sources,
            )

            logging.getLogger(__name__).info("Integration executor initialized")

        except ImportError as e:
            logging.getLogger(__name__).debug("Integration executor not available: %s", e)

        except Exception as e:
            logging.getLogger(__name__).warning("Failed to init integration executor: %s", e)
