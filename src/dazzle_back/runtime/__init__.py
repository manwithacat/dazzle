"""
DNR-Back Runtime

Native backend runtime implementation (FastAPI + Pydantic).

This module provides:
- Model generation (Pydantic models from EntitySpec)
- Service generation (domain logic stubs from ServiceSpec)
- Route generation (FastAPI routes from EndpointSpec)
- Runtime server creation

Example usage:
    >>> from dazzle_back.specs import BackendSpec
    >>> from dazzle_back.runtime import create_app, run_app
    >>>
    >>> # Create spec (from DSL conversion or manual)
    >>> spec = BackendSpec(name="my_app", ...)
    >>>
    >>> # Create FastAPI app
    >>> app = create_app(spec)
    >>>
    >>> # Or run directly
    >>> run_app(spec, port=8000)
"""

from dazzle_back.runtime.access_evaluator import (
    AccessRuntimeContext,
    can_create,
    can_delete,
    can_read,
    can_update,
    evaluate_access_condition,
    evaluate_permission,
    evaluate_visibility,
    filter_visible_records,
)
from dazzle_back.runtime.migrations import (
    MigrationAction,
    MigrationError,
    MigrationExecutor,
    MigrationHistory,
    MigrationPlan,
    MigrationPlanner,
    MigrationStep,
    auto_migrate,
    plan_migrations,
)
from dazzle_back.runtime.model_generator import (
    generate_all_entity_models,
    generate_create_schema,
    generate_entity_model,
    generate_list_response_schema,
    generate_update_schema,
)
from dazzle_back.runtime.repository import (
    DatabaseManager,
    Repository,
    RepositoryFactory,
    SQLiteRepository,
)
from dazzle_back.runtime.route_generator import (
    FASTAPI_AVAILABLE,
    RouteGenerator,
    generate_crud_routes,
)
from dazzle_back.runtime.server import (
    DazzleBackendApp,
    ServerConfig,
    create_app,
    run_app,
)
from dazzle_back.runtime.service_generator import (
    BaseService,
    CRUDService,
    CustomService,
    ServiceContext,
    ServiceFactory,
)

__all__ = [
    # Access control (v0.7.0)
    "AccessRuntimeContext",
    "evaluate_access_condition",
    "evaluate_visibility",
    "evaluate_permission",
    "can_read",
    "can_create",
    "can_update",
    "can_delete",
    "filter_visible_records",
    # Model generation
    "generate_entity_model",
    "generate_all_entity_models",
    "generate_create_schema",
    "generate_update_schema",
    "generate_list_response_schema",
    # Services
    "BaseService",
    "CRUDService",
    "CustomService",
    "ServiceFactory",
    "ServiceContext",
    # Routes
    "RouteGenerator",
    "generate_crud_routes",
    "FASTAPI_AVAILABLE",
    # Server
    "DazzleBackendApp",
    "ServerConfig",
    "create_app",
    "run_app",
    # Repository
    "Repository",
    "DatabaseManager",
    "SQLiteRepository",
    "RepositoryFactory",
    # Migrations
    "MigrationAction",
    "MigrationStep",
    "MigrationPlan",
    "MigrationPlanner",
    "MigrationExecutor",
    "MigrationHistory",
    "MigrationError",
    "auto_migrate",
    "plan_migrations",
]
