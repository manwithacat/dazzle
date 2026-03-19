"""Subsystem plugin architecture for DazzleBackendApp.

Each subsystem encapsulates a discrete feature (channels, events, SLA, etc.)
behind a common ``SubsystemPlugin`` protocol.  ``DazzleBackendApp.build()``
iterates ``self.subsystems`` in order, calling ``startup()`` on each, then
calls ``shutdown()`` in reverse order on app teardown.

Startup errors are caught by each plugin individually — a failing subsystem
logs a warning but never aborts the overall startup sequence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from fastapi import FastAPI

    from dazzle.core.ir import AppSpec
    from dazzle_back.runtime.server import ServerConfig
    from dazzle_back.runtime.service_generator import CRUDService


@dataclass
class SubsystemContext:
    """Shared runtime state passed to every subsystem plugin.

    Subsystems receive this object at startup time. They may read any field and
    may write back references to objects they own (e.g. ``channel_manager``,
    ``process_manager``) so that sibling subsystems or callers can inspect them.
    """

    app: FastAPI
    appspec: AppSpec
    config: ServerConfig
    services: dict[str, Any]
    repositories: dict[str, Any]
    entities: list[Any]
    channels: list[Any]
    # Database manager — set by DazzleBackendApp after _setup_database()
    db_manager: Any | None = None
    # Mutable outputs — subsystems write these so other subsystems can read them
    channel_manager: Any | None = None
    event_framework: Any | None = None
    process_manager: Any | None = None
    process_adapter: Any | None = None
    sla_manager: Any | None = None
    llm_queue: Any | None = None
    # Auth middleware — set by DazzleBackendApp before subsystem startup
    auth_middleware: Any | None = None
    # Misc flags forwarded from config for convenience
    enable_auth: bool = False
    enable_test_mode: bool = False

    # Auth — set by DazzleBackendApp._setup_auth() before subsystems run
    auth_store: Any | None = None
    auth_dep: Any | None = None  # FastAPI Depends for required auth
    optional_auth_dep: Any | None = None  # FastAPI Depends for optional auth
    auth_config: Any | None = None  # AuthConfig from manifest
    database_url: str = ""  # for subsystems needing DB access

    # Integration — set by integrations subsystem
    integration_mgr: Any | None = None

    # Workspace — set by workspace subsystem
    workspace_builder: Any | None = None

    # Audit — set by DazzleBackendApp._setup_routes, read by system_routes subsystem
    audit_logger: Any | None = None

    # Config forwarded from ServerConfig
    security_profile: str = "basic"
    project_root: Any | None = None


@runtime_checkable
class SubsystemPlugin(Protocol):
    """Protocol implemented by every subsystem module.

    ``name`` is used only for logging.  ``startup()`` is called once during
    ``DazzleBackendApp.build()`` (synchronously — it may register async FastAPI
    ``on_event`` handlers but must not itself be a coroutine).  ``shutdown()``
    is available for explicit teardown; most plugins prefer registering an
    ``on_event("shutdown")`` handler instead.
    """

    name: str

    def startup(self, ctx: SubsystemContext) -> None:
        """Initialise this subsystem.  Must not raise — log and return on error."""
        ...

    def shutdown(self) -> None:
        """Tear down this subsystem (optional — prefer on_event handlers)."""
        ...


__all__ = ["SubsystemContext", "SubsystemPlugin"]
