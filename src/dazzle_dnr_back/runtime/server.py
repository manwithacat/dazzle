"""
Runtime server - creates and runs a FastAPI application from BackendSpec.

This module provides the main entry point for running a DNR-Back application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from dazzle_dnr_back.runtime.auth import AuthMiddleware, AuthStore, create_auth_routes
from dazzle_dnr_back.runtime.file_routes import create_file_routes, create_static_file_routes
from dazzle_dnr_back.runtime.file_storage import FileService, create_local_file_service
from dazzle_dnr_back.runtime.migrations import MigrationPlan, auto_migrate
from dazzle_dnr_back.runtime.model_generator import (
    generate_all_entity_models,
    generate_create_schema,
    generate_update_schema,
)
from dazzle_dnr_back.runtime.repository import DatabaseManager, RepositoryFactory
from dazzle_dnr_back.runtime.service_generator import CRUDService, ServiceFactory
from dazzle_dnr_back.runtime.service_loader import ServiceLoader
from dazzle_dnr_back.specs import BackendSpec

# FastAPI is optional - use TYPE_CHECKING for type hints
if TYPE_CHECKING:
    from fastapi import FastAPI


# =============================================================================
# Server Configuration
# =============================================================================


@dataclass
class ServerConfig:
    """
    Configuration for DNRBackendApp.

    Groups all initialization options into a single object for cleaner APIs.
    """

    # Database settings
    db_path: Path = field(default_factory=lambda: Path(".dazzle/data.db"))
    use_database: bool = True

    # Authentication settings
    enable_auth: bool = False
    auth_db_path: Path = field(default_factory=lambda: Path(".dazzle/auth.db"))

    # File upload settings
    enable_files: bool = False
    files_path: Path = field(default_factory=lambda: Path(".dazzle/uploads"))
    files_db_path: Path = field(default_factory=lambda: Path(".dazzle/files.db"))

    # Development/testing settings
    enable_test_mode: bool = False
    services_dir: Path = field(default_factory=lambda: Path("services"))


# Runtime import
try:
    from fastapi import FastAPI as _FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from dazzle_dnr_back.runtime.route_generator import RouteGenerator

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    _FastAPI = None  # type: ignore
    CORSMiddleware = None  # type: ignore
    RouteGenerator = None  # type: ignore


# =============================================================================
# Application Builder
# =============================================================================


class DNRBackendApp:
    """
    DNR Backend Application.

    Creates a complete FastAPI application from a BackendSpec.
    """

    def __init__(
        self,
        spec: BackendSpec,
        config: ServerConfig | None = None,
        *,
        # Legacy parameters for backwards compatibility
        db_path: str | Path | None = None,
        use_database: bool | None = None,
        enable_auth: bool | None = None,
        auth_db_path: str | Path | None = None,
        enable_files: bool | None = None,
        files_path: str | Path | None = None,
        files_db_path: str | Path | None = None,
        enable_test_mode: bool | None = None,
        services_dir: str | Path | None = None,
    ):
        """
        Initialize the backend application.

        Args:
            spec: Backend specification
            config: Server configuration object (preferred)

            Legacy parameters (use config instead):
            db_path: Path to SQLite database (default: .dazzle/data.db)
            use_database: Whether to use SQLite persistence (default: True)
            enable_auth: Whether to enable authentication (default: False)
            auth_db_path: Path to auth database (default: .dazzle/auth.db)
            enable_files: Whether to enable file uploads (default: False)
            files_path: Path for file storage (default: .dazzle/uploads)
            files_db_path: Path to file metadata database (default: .dazzle/files.db)
            enable_test_mode: Whether to enable /__test__/* endpoints (default: False)
            services_dir: Path to domain service stubs directory (default: services/)
        """
        if not FASTAPI_AVAILABLE:
            raise RuntimeError(
                "FastAPI is not installed. Install with: pip install fastapi uvicorn"
            )

        # Use config if provided, otherwise build from legacy parameters
        if config is None:
            config = ServerConfig()

        # Override config with any explicit legacy parameters
        self.spec = spec
        self._db_path = Path(db_path) if db_path else config.db_path
        self._use_database = use_database if use_database is not None else config.use_database
        self._enable_auth = enable_auth if enable_auth is not None else config.enable_auth
        self._auth_db_path = Path(auth_db_path) if auth_db_path else config.auth_db_path
        self._enable_files = enable_files if enable_files is not None else config.enable_files
        self._files_path = Path(files_path) if files_path else config.files_path
        self._files_db_path = Path(files_db_path) if files_db_path else config.files_db_path
        self._enable_test_mode = (
            enable_test_mode if enable_test_mode is not None else config.enable_test_mode
        )
        self._services_dir = Path(services_dir) if services_dir else config.services_dir
        self._app: FastAPI | None = None
        self._models: dict[str, type[BaseModel]] = {}
        self._schemas: dict[str, dict[str, type[BaseModel]]] = {}
        self._services: dict[str, Any] = {}
        self._repositories: dict[str, Any] = {}
        self._db_manager: DatabaseManager | None = None
        self._auth_store: AuthStore | None = None
        self._auth_middleware: AuthMiddleware | None = None
        self._file_service: FileService | None = None
        self._last_migration: MigrationPlan | None = None
        self._start_time: datetime | None = None
        self._service_loader: ServiceLoader | None = None

    def build(self) -> FastAPI:
        """
        Build the FastAPI application.

        Returns:
            FastAPI application instance
        """
        # Create FastAPI app
        self._app = _FastAPI(
            title=self.spec.name,
            description=self.spec.description or f"DNR Backend: {self.spec.name}",
            version=self.spec.version,
        )

        # Add CORS middleware
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Generate models
        self._models = generate_all_entity_models(self.spec.entities)

        # Generate schemas (create/update)
        for entity in self.spec.entities:
            self._schemas[entity.name] = {
                "create": generate_create_schema(entity),
                "update": generate_update_schema(entity),
            }

        # Initialize database if enabled
        if self._use_database:
            self._db_manager = DatabaseManager(self._db_path)

            # Auto-migrate: creates tables and applies schema changes
            self._last_migration = auto_migrate(
                self._db_manager,
                self.spec.entities,
                record_history=True,
            )

            repo_factory = RepositoryFactory(self._db_manager, self._models)
            self._repositories = repo_factory.create_all_repositories(self.spec.entities)

        # Extract state machines from entities
        state_machines = {
            entity.name: entity.state_machine
            for entity in self.spec.entities
            if entity.state_machine
        }

        # Create services
        factory = ServiceFactory(self._models, state_machines)
        self._services = factory.create_all_services(
            self.spec.services,
            self._schemas,
        )

        # Wire up repositories to services
        # Match services to repositories by their target entity
        if self._use_database:
            for _service_name, service in self._services.items():
                if isinstance(service, CRUDService):
                    # Get the entity name from the service
                    entity_name = service.entity_name
                    repo = self._repositories.get(entity_name)
                    if repo:
                        service.set_repository(repo)

        # Initialize auth if enabled (needed before route generation)
        get_auth_context = None
        if self._enable_auth:
            self._auth_store = AuthStore(self._auth_db_path)
            self._auth_middleware = AuthMiddleware(self._auth_store)
            auth_router = create_auth_routes(self._auth_store)
            self._app.include_router(auth_router)
            # Create auth context getter for routes
            get_auth_context = self._auth_middleware.get_auth_context

        # Extract entity access specs from entity metadata
        entity_access_specs: dict[str, dict[str, Any]] = {}
        for entity in self.spec.entities:
            if entity.metadata and "access" in entity.metadata:
                entity_access_specs[entity.name] = entity.metadata["access"]

        # Generate routes
        service_specs = {svc.name: svc for svc in self.spec.services}
        route_generator = RouteGenerator(
            services=self._services,
            models=self._models,
            schemas=self._schemas,
            entity_access_specs=entity_access_specs,
            get_auth_context=get_auth_context,
        )
        router = route_generator.generate_all_routes(
            self.spec.endpoints,
            service_specs,
        )

        # Include router
        self._app.include_router(router)

        # Initialize file uploads if enabled
        if self._enable_files:
            self._file_service = create_local_file_service(
                base_path=self._files_path,
                db_path=self._files_db_path,
                base_url="/files",
            )
            create_file_routes(self._app, self._file_service)
            create_static_file_routes(
                self._app,
                base_path=str(self._files_path),
                url_prefix="/files",
            )

        # Initialize test routes if enabled
        if self._enable_test_mode and self._use_database and self._db_manager:
            # Lazy import to avoid FastAPI dependency at module load
            from dazzle_dnr_back.runtime.test_routes import create_test_routes

            test_router = create_test_routes(
                db_manager=self._db_manager,
                repositories=self._repositories,
                entities=self.spec.entities,
            )
            self._app.include_router(test_router)

        # Initialize debug routes (always available when database is enabled)
        if self._use_database and self._db_manager:
            from dazzle_dnr_back.runtime.debug_routes import create_debug_routes

            self._start_time = datetime.now()
            debug_router = create_debug_routes(
                spec=self.spec,
                db_manager=self._db_manager,
                entities=self.spec.entities,
                start_time=self._start_time,
            )
            self._app.include_router(debug_router)

        # Load domain service stubs
        self._service_loader = ServiceLoader(services_dir=self._services_dir)
        try:
            self._service_loader.load_services()
        except Exception:
            # Services are optional - log but don't fail startup
            pass

        # Add domain service routes if any services loaded
        if self._service_loader and self._service_loader.services:
            service_loader = self._service_loader  # Capture for closure

            @self._app.get("/_dnr/services", tags=["System"])
            async def list_domain_services() -> dict[str, Any]:
                """List loaded domain service stubs."""
                services = []
                for service_id, loaded in service_loader.services.items():
                    services.append(
                        {
                            "id": service_id,
                            "module_path": str(loaded.module_path),
                            "has_result_type": loaded.result_type is not None,
                        }
                    )
                return {"services": services, "count": len(services)}

            @self._app.post("/_dnr/services/{service_id}/invoke", tags=["System"])
            async def invoke_domain_service(
                service_id: str, payload: dict[str, Any] | None = None
            ) -> dict[str, Any]:
                """Invoke a domain service stub."""
                if not service_loader.has_service(service_id):
                    return {"error": f"Service not found: {service_id}"}
                try:
                    result = service_loader.invoke(service_id, **(payload or {}))
                    return {"result": result}
                except Exception as e:
                    return {"error": str(e)}

        # Add health check
        @self._app.get("/health", tags=["System"])
        async def health_check() -> dict[str, str]:
            return {"status": "healthy", "app": self.spec.name}

        # Add spec endpoint
        @self._app.get("/spec", tags=["System"])
        async def get_spec() -> dict[str, Any]:
            return self.spec.model_dump()

        # Add database info endpoint
        db_path = str(self._db_path) if self._use_database else None
        auth_db_path = str(self._auth_db_path) if self._enable_auth else None
        files_path = str(self._files_path) if self._enable_files else None
        files_db_path = str(self._files_db_path) if self._enable_files else None
        last_migration = self._last_migration
        auth_enabled = self._enable_auth
        files_enabled = self._enable_files

        @self._app.get("/db-info", tags=["System"])
        async def db_info() -> dict[str, Any]:
            migration_info = None
            if last_migration:
                migration_info = {
                    "steps_executed": len(last_migration.safe_steps),
                    "warnings": last_migration.warnings,
                    "has_pending_destructive": last_migration.has_destructive,
                }
            return {
                "database_enabled": self._use_database,
                "database_path": db_path,
                "tables": [e.name for e in self.spec.entities],
                "last_migration": migration_info,
                "auth_enabled": auth_enabled,
                "auth_database_path": auth_db_path,
                "files_enabled": files_enabled,
                "files_path": files_path,
                "files_database_path": files_db_path,
            }

        return self._app

    @property
    def app(self) -> FastAPI | None:
        """Get the FastAPI application (None if not built)."""
        return self._app

    @property
    def models(self) -> dict[str, type[BaseModel]]:
        """Get generated Pydantic models."""
        return self._models

    @property
    def services(self) -> dict[str, Any]:
        """Get service instances."""
        return self._services

    def get_service(self, name: str) -> Any | None:
        """Get a service by name."""
        return self._services.get(name)

    @property
    def auth_store(self) -> AuthStore | None:
        """Get the auth store (None if auth not enabled)."""
        return self._auth_store

    @property
    def auth_middleware(self) -> AuthMiddleware | None:
        """Get the auth middleware (None if auth not enabled)."""
        return self._auth_middleware

    @property
    def auth_enabled(self) -> bool:
        """Check if authentication is enabled."""
        return self._enable_auth

    @property
    def file_service(self) -> FileService | None:
        """Get the file service (None if files not enabled)."""
        return self._file_service

    @property
    def files_enabled(self) -> bool:
        """Check if file uploads are enabled."""
        return self._enable_files

    @property
    def test_mode_enabled(self) -> bool:
        """Check if test mode is enabled."""
        return self._enable_test_mode

    @property
    def repositories(self) -> dict[str, Any]:
        """Get repository instances."""
        return self._repositories

    @property
    def service_loader(self) -> ServiceLoader | None:
        """Get the domain service loader (None if not initialized)."""
        return self._service_loader


# =============================================================================
# Convenience Functions
# =============================================================================


def create_app(
    spec: BackendSpec,
    db_path: str | Path | None = None,
    use_database: bool = True,
    enable_auth: bool = False,
    auth_db_path: str | Path | None = None,
    enable_files: bool = False,
    files_path: str | Path | None = None,
    files_db_path: str | Path | None = None,
    enable_test_mode: bool = False,
    services_dir: str | Path | None = None,
) -> FastAPI:
    """
    Create a FastAPI application from a BackendSpec.

    This is the main entry point for creating a DNR-Back application.

    Args:
        spec: Backend specification
        db_path: Path to SQLite database (default: .dazzle/data.db)
        use_database: Whether to use SQLite persistence (default: True)
        enable_auth: Whether to enable authentication (default: False)
        auth_db_path: Path to auth database (default: .dazzle/auth.db)
        enable_files: Whether to enable file uploads (default: False)
        files_path: Path for file storage (default: .dazzle/uploads)
        files_db_path: Path to file metadata database (default: .dazzle/files.db)
        enable_test_mode: Whether to enable /__test__/* endpoints (default: False)
        services_dir: Path to domain service stubs directory (default: services/)

    Returns:
        FastAPI application

    Example:
        >>> from dazzle_dnr_back.specs import BackendSpec
        >>> spec = BackendSpec(name="my_app", ...)
        >>> app = create_app(spec)
        >>> # Run with uvicorn: uvicorn mymodule:app
    """
    builder = DNRBackendApp(
        spec,
        db_path=db_path,
        use_database=use_database,
        enable_auth=enable_auth,
        auth_db_path=auth_db_path,
        enable_files=enable_files,
        files_path=files_path,
        files_db_path=files_db_path,
        enable_test_mode=enable_test_mode,
        services_dir=services_dir,
    )
    return builder.build()


def run_app(
    spec: BackendSpec,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    db_path: str | Path | None = None,
    use_database: bool = True,
    enable_auth: bool = False,
    auth_db_path: str | Path | None = None,
    enable_files: bool = False,
    files_path: str | Path | None = None,
    files_db_path: str | Path | None = None,
    enable_test_mode: bool = False,
    services_dir: str | Path | None = None,
) -> None:
    """
    Run a DNR-Back application.

    Args:
        spec: Backend specification
        host: Host to bind to
        port: Port to bind to
        reload: Enable auto-reload (for development)
        db_path: Path to SQLite database (default: .dazzle/data.db)
        use_database: Whether to use SQLite persistence (default: True)
        enable_auth: Whether to enable authentication (default: False)
        auth_db_path: Path to auth database (default: .dazzle/auth.db)
        enable_files: Whether to enable file uploads (default: False)
        files_path: Path for file storage (default: .dazzle/uploads)
        files_db_path: Path to file metadata database (default: .dazzle/files.db)
        enable_test_mode: Whether to enable /__test__/* endpoints (default: False)
        services_dir: Path to domain service stubs directory (default: services/)

    Example:
        >>> from dazzle_dnr_back.specs import BackendSpec
        >>> spec = BackendSpec(name="my_app", ...)
        >>> run_app(spec)  # Starts server on http://127.0.0.1:8000
    """
    try:
        import uvicorn
    except ImportError:
        raise RuntimeError("uvicorn is not installed. Install with: pip install uvicorn")

    app = create_app(
        spec,
        db_path=db_path,
        use_database=use_database,
        enable_auth=enable_auth,
        auth_db_path=auth_db_path,
        enable_files=enable_files,
        files_path=files_path,
        files_db_path=files_db_path,
        enable_test_mode=enable_test_mode,
        services_dir=services_dir,
    )
    uvicorn.run(app, host=host, port=port, reload=reload)


# =============================================================================
# App from JSON/Dict
# =============================================================================


def create_app_from_dict(spec_dict: dict[str, Any]) -> FastAPI:
    """
    Create a FastAPI application from a dictionary specification.

    Useful for loading specs from JSON files or API responses.

    Args:
        spec_dict: Dictionary representation of BackendSpec

    Returns:
        FastAPI application
    """
    spec = BackendSpec.model_validate(spec_dict)
    return create_app(spec)


def create_app_from_json(json_path: str) -> FastAPI:
    """
    Create a FastAPI application from a JSON file.

    Args:
        json_path: Path to JSON file containing BackendSpec

    Returns:
        FastAPI application
    """
    import json
    from pathlib import Path

    spec_dict = json.loads(Path(json_path).read_text())
    return create_app_from_dict(spec_dict)
