"""
Surface converter - converts Dazzle IR SurfaceSpec to DNR BackendSpec services.

This module infers backend services from surface definitions, creating
CRUD operations based on surface modes.
"""

from dazzle.core import ir
from dazzle.core.strings import to_api_plural
from dazzle_dnr_back.specs import (
    DomainOperation,
    EndpointSpec,
    HttpMethod,
    OperationKind,
    SchemaFieldSpec,
    SchemaSpec,
    ServiceSpec,
)

# =============================================================================
# Service Generation
# =============================================================================


def _surface_mode_to_operation(mode: ir.SurfaceMode) -> OperationKind:
    """Map surface mode to domain operation kind."""
    mode_map = {
        ir.SurfaceMode.CREATE: OperationKind.CREATE,
        ir.SurfaceMode.EDIT: OperationKind.UPDATE,
        ir.SurfaceMode.VIEW: OperationKind.READ,
        ir.SurfaceMode.LIST: OperationKind.LIST,
        ir.SurfaceMode.CUSTOM: OperationKind.CUSTOM,
    }
    return mode_map.get(mode, OperationKind.CUSTOM)


def _surface_mode_to_http_method(mode: ir.SurfaceMode) -> HttpMethod:
    """Map surface mode to HTTP method."""
    method_map = {
        ir.SurfaceMode.CREATE: HttpMethod.POST,
        ir.SurfaceMode.EDIT: HttpMethod.PUT,
        ir.SurfaceMode.VIEW: HttpMethod.GET,
        ir.SurfaceMode.LIST: HttpMethod.GET,
        ir.SurfaceMode.CUSTOM: HttpMethod.POST,
    }
    return method_map.get(mode, HttpMethod.GET)


def _generate_service_name(surface: ir.SurfaceSpec) -> str:
    """Generate a service name from surface."""
    entity = surface.entity_ref or "item"
    mode = surface.mode.value

    if mode == "list":
        return f"list_{to_api_plural(entity)}"
    elif mode == "view":
        return f"get_{entity.lower()}"
    elif mode == "create":
        return f"create_{entity.lower()}"
    elif mode == "edit":
        return f"update_{entity.lower()}"
    else:
        return f"{surface.name}_operation"


def _generate_input_schema(surface: ir.SurfaceSpec, entity: ir.EntitySpec | None) -> SchemaSpec:
    """Generate input schema for a service based on surface mode."""
    fields: list[SchemaFieldSpec] = []

    if surface.mode in (ir.SurfaceMode.VIEW, ir.SurfaceMode.EDIT):
        # Need an ID to identify the record
        fields.append(SchemaFieldSpec(name="id", type="uuid", required=True))

    if surface.mode in (ir.SurfaceMode.CREATE, ir.SurfaceMode.EDIT):
        # Collect fields from surface sections
        for section in surface.sections:
            for element in section.elements:
                # Skip id field for create (auto-generated)
                if element.field_name == "id" and surface.mode == ir.SurfaceMode.CREATE:
                    continue
                # Skip auto fields
                if element.field_name in ("created_at", "updated_at"):
                    continue

                field_type = "str"  # Default
                required = True

                # Try to get type from entity
                if entity:
                    entity_field = entity.get_field(element.field_name)
                    if entity_field:
                        field_type = _map_field_type_name(entity_field.type)
                        required = entity_field.is_required

                fields.append(
                    SchemaFieldSpec(
                        name=element.field_name,
                        type=field_type,
                        required=required,
                    )
                )

    if surface.mode == ir.SurfaceMode.LIST:
        # Add pagination and filter params
        fields.extend(
            [
                SchemaFieldSpec(name="page", type="int", required=False),
                SchemaFieldSpec(name="page_size", type="int", required=False),
            ]
        )

        # Add filter fields from UX spec
        if surface.ux and surface.ux.filter:
            for filter_field in surface.ux.filter:
                fields.append(SchemaFieldSpec(name=filter_field, type="str", required=False))

    return SchemaSpec(fields=fields)


def _generate_output_schema(surface: ir.SurfaceSpec, entity: ir.EntitySpec | None) -> SchemaSpec:
    """Generate output schema for a service based on surface mode."""
    fields: list[SchemaFieldSpec] = []

    entity_name = surface.entity_ref or "Item"

    if surface.mode == ir.SurfaceMode.LIST:
        fields.extend(
            [
                SchemaFieldSpec(name="items", type=f"list[{entity_name}]", required=True),
                SchemaFieldSpec(name="total", type="int", required=True),
                SchemaFieldSpec(name="page", type="int", required=True),
                SchemaFieldSpec(name="page_size", type="int", required=True),
            ]
        )
    else:
        # Single entity output
        fields.append(SchemaFieldSpec(name=entity_name.lower(), type=entity_name, required=True))

    return SchemaSpec(fields=fields)


def _map_field_type_name(field_type: ir.FieldType) -> str:
    """Map Dazzle field type to a string type name."""
    type_map = {
        ir.FieldTypeKind.STR: "str",
        ir.FieldTypeKind.TEXT: "str",
        ir.FieldTypeKind.INT: "int",
        ir.FieldTypeKind.DECIMAL: "decimal",
        ir.FieldTypeKind.BOOL: "bool",
        ir.FieldTypeKind.DATE: "date",
        ir.FieldTypeKind.DATETIME: "datetime",
        ir.FieldTypeKind.UUID: "uuid",
        ir.FieldTypeKind.EMAIL: "email",
        ir.FieldTypeKind.ENUM: "str",  # Enums as strings
        ir.FieldTypeKind.REF: "uuid",  # References as UUIDs
    }
    return type_map.get(field_type.kind, "str")


# =============================================================================
# Service Conversion
# =============================================================================


def convert_surface_to_service(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None = None,
) -> ServiceSpec:
    """
    Convert a Dazzle IR SurfaceSpec to DNR BackendSpec ServiceSpec.

    Args:
        surface: Dazzle IR surface specification
        entity: Optional entity specification for field type inference

    Returns:
        DNR BackendSpec service specification
    """
    return ServiceSpec(
        name=_generate_service_name(surface),
        description=surface.title or f"Service for {surface.name}",
        inputs=_generate_input_schema(surface, entity),
        outputs=_generate_output_schema(surface, entity),
        domain_operation=DomainOperation(
            kind=_surface_mode_to_operation(surface.mode),
            entity=surface.entity_ref,
        ),
    )


def convert_surface_to_endpoint(
    surface: ir.SurfaceSpec,
    service_name: str,
) -> EndpointSpec:
    """
    Convert a Dazzle IR SurfaceSpec to DNR BackendSpec EndpointSpec.

    Args:
        surface: Dazzle IR surface specification
        service_name: Name of the corresponding service

    Returns:
        DNR BackendSpec endpoint specification
    """
    entity = surface.entity_ref or "items"
    entity_lower = entity.lower()

    # Generate path based on mode
    if surface.mode == ir.SurfaceMode.LIST:
        path = f"/{entity_lower}s"
    elif surface.mode == ir.SurfaceMode.CREATE:
        path = f"/{entity_lower}s"
    elif surface.mode in (ir.SurfaceMode.VIEW, ir.SurfaceMode.EDIT):
        path = f"/{entity_lower}s/{{id}}"
    else:
        path = f"/{surface.name.replace('_', '-')}"

    return EndpointSpec(
        name=f"{surface.name}_endpoint",
        service=service_name,
        method=_surface_mode_to_http_method(surface.mode),
        path=path,
        description=surface.title,
        tags=[entity] if surface.entity_ref else [],
    )


def convert_surfaces_to_services(
    surfaces: list[ir.SurfaceSpec],
    domain: ir.DomainSpec | None = None,
) -> tuple[list[ServiceSpec], list[EndpointSpec]]:
    """
    Convert a list of Dazzle IR surfaces to DNR services and endpoints.

    Args:
        surfaces: List of Dazzle IR surface specifications
        domain: Optional domain spec for entity lookup

    Returns:
        Tuple of (services, endpoints)
    """
    services: list[ServiceSpec] = []
    endpoints: list[EndpointSpec] = []

    # Track entities that have list surfaces (for adding DELETE endpoints)
    entities_with_list = set()

    for surface in surfaces:
        # Get entity if available
        entity = None
        if domain and surface.entity_ref:
            entity = domain.get_entity(surface.entity_ref)

        # Create service
        service = convert_surface_to_service(surface, entity)
        services.append(service)

        # Create endpoint
        endpoint = convert_surface_to_endpoint(surface, service.name)
        endpoints.append(endpoint)

        # Track entities with list surfaces for DELETE endpoint generation
        if surface.mode == ir.SurfaceMode.LIST and surface.entity_ref:
            entities_with_list.add(surface.entity_ref)

    # Add DELETE endpoints for entities that have list surfaces
    # This enables CRUD delete operations on entity tables
    for entity_name in entities_with_list:
        entity_lower = entity_name.lower()

        # Create delete service
        delete_service = ServiceSpec(
            name=f"delete_{entity_lower}",
            input_schema=SchemaSpec(
                fields=[SchemaFieldSpec(name="id", type="uuid", required=True)]
            ),
            output_schema=SchemaSpec(
                fields=[SchemaFieldSpec(name="deleted", type="bool", required=True)]
            ),
            domain_operation=DomainOperation(
                entity=entity_name,
                kind=OperationKind.DELETE,
            ),
            is_crud=True,
        )
        services.append(delete_service)

        # Create delete endpoint
        delete_endpoint = EndpointSpec(
            name=f"delete_{entity_lower}_endpoint",
            service=f"delete_{entity_lower}",
            method=HttpMethod.DELETE,
            path=f"/{entity_lower}s/{{id}}",
            description=f"Delete {entity_name}",
            tags=[entity_name],
        )
        endpoints.append(delete_endpoint)

    return services, endpoints
