"""
DNR-Back Runtime

Native backend runtime implementation (FastAPI + Pydantic).

This module provides:
- Model generation (Pydantic models from EntitySpec)
- Service generation (domain logic stubs from ServiceSpec)
- Route generation (FastAPI routes from EndpointSpec)
- Runtime server creation

Example usage:
    >>> from dazzle_dnr_back.specs import BackendSpec
    >>> from dazzle_dnr_back.runtime import create_app, run_app
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

from dazzle_dnr_back.runtime.model_generator import (
    generate_entity_model,
    generate_all_entity_models,
    generate_create_schema,
    generate_update_schema,
    generate_list_response_schema,
)

from dazzle_dnr_back.runtime.service_generator import (
    BaseService,
    CRUDService,
    CustomService,
    ServiceFactory,
    ServiceContext,
)

from dazzle_dnr_back.runtime.route_generator import (
    RouteGenerator,
    generate_crud_routes,
)

from dazzle_dnr_back.runtime.server import (
    DNRBackendApp,
    create_app,
    run_app,
    create_app_from_dict,
    create_app_from_json,
)


__all__ = [
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
    # Server
    "DNRBackendApp",
    "create_app",
    "run_app",
    "create_app_from_dict",
    "create_app_from_json",
]
