"""
OpenAPI schema generation from AppSpec.

Generates OpenAPI 3.1 specifications from DAZZLE AppSpec,
including all entities, endpoints, and business logic metadata.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec, EntitySpec, FieldSpec
    from dazzle.core.ir.surfaces import SurfaceSpec


def generate_openapi(spec: AppSpec) -> dict[str, Any]:
    """
    Generate OpenAPI 3.1 specification from AppSpec.

    Args:
        spec: The application specification

    Returns:
        OpenAPI 3.1 specification as a dictionary
    """
    openapi: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": spec.name,
            "description": spec.title or f"API for {spec.name}",
            "version": "1.0.0",
        },
        "servers": [{"url": "http://localhost:8000", "description": "Development server"}],
        "paths": {},
        "components": {
            "schemas": {},
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                }
            },
        },
        "tags": [],
    }

    # Build surface list projections: entity_name → [field_names]
    list_projections = _build_list_projections(getattr(spec, "surfaces", []))

    # Generate schemas for all entities
    for entity in spec.domain.entities:
        _add_entity_schemas(openapi, entity, list_projections.get(entity.name))
        _add_entity_paths(openapi, entity)
        openapi["tags"].append(
            {
                "name": entity.name,
                "description": entity.title or f"Operations for {entity.name}",
            }
        )

    return openapi


def _build_list_projections(
    surfaces: list[SurfaceSpec],
) -> dict[str, list[str]]:
    """Extract projected field names from list-mode surfaces.

    Returns a mapping of ``{entity_name: [field_names]}`` for entities
    that have a list surface with explicit field declarations.
    """
    projections: dict[str, list[str]] = {}
    for surface in surfaces:
        entity_ref = getattr(surface, "entity_ref", None)
        if not entity_ref or entity_ref in projections:
            continue
        if surface.mode != "list" or not surface.sections:
            continue
        field_names: list[str] = []
        for section in surface.sections:
            for element in section.elements:
                if element.field_name not in field_names:
                    field_names.append(element.field_name)
        if field_names:
            # Always include id for list items
            if "id" not in field_names:
                field_names.insert(0, "id")
            projections[entity_ref] = field_names
    return projections


def _add_entity_schemas(
    openapi: dict[str, Any],
    entity: EntitySpec,
    list_projection: list[str] | None = None,
) -> None:
    """Add schemas for an entity (Base, Create, Update, Read, ListItem)."""
    schemas = openapi["components"]["schemas"]
    entity_name = entity.name

    # Base schema (all fields)
    base_schema = _entity_to_schema(entity, include_id=True)
    schemas[entity_name] = base_schema

    # Create schema (no id, no read-only fields)
    create_schema = _entity_to_schema(entity, include_id=False, for_create=True)
    schemas[f"{entity_name}Create"] = create_schema

    # Update schema (all optional, no read-only)
    update_schema = _entity_to_schema(entity, include_id=False, all_optional=True)
    schemas[f"{entity_name}Update"] = update_schema

    # Read schema (includes id and relationships)
    read_schema = _entity_to_schema(entity, include_id=True)
    schemas[f"{entity_name}Read"] = read_schema

    # List item schema — projected subset when surface defines projections
    if list_projection:
        list_item_schema = _entity_to_schema(
            entity, include_id=True, only_fields=set(list_projection)
        )
        schemas[f"{entity_name}ListItem"] = list_item_schema
        list_item_ref = f"#/components/schemas/{entity_name}ListItem"
    else:
        list_item_ref = f"#/components/schemas/{entity_name}Read"

    # List response schema
    schemas[f"{entity_name}List"] = {
        "type": "array",
        "items": {"$ref": list_item_ref},
    }

    # Add enum schemas for enum fields
    for field in entity.fields:
        if field.type.kind.value == "enum" and field.type.enum_values:
            schemas[f"{entity_name}{_pascal_case(field.name)}"] = {
                "type": "string",
                "enum": field.type.enum_values,
                "description": f"Values for {entity_name}.{field.name}",
            }


def _entity_to_schema(
    entity: EntitySpec,
    include_id: bool = True,
    for_create: bool = False,
    all_optional: bool = False,
    only_fields: set[str] | None = None,
) -> dict[str, Any]:
    """Convert entity to JSON Schema."""
    from dazzle.core.ir import FieldModifier

    properties: dict[str, Any] = {}
    required: list[str] = []

    for field in entity.fields:
        # Skip ID for create schemas
        if field.name == "id" and not include_id:
            continue

        # Skip read-only fields for create
        if for_create and field.name in ("created_at", "updated_at"):
            continue

        # Skip fields not in the projection set
        if only_fields is not None and field.name not in only_fields:
            continue

        prop_schema = _field_to_schema(field, entity.name)
        properties[field.name] = prop_schema

        # Track required fields
        is_required = FieldModifier.REQUIRED in field.modifiers
        if is_required and not all_optional and field.default is None:
            required.append(field.name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }

    if required:
        schema["required"] = required

    if entity.title:
        schema["description"] = entity.title

    return schema


def _field_to_schema(field: FieldSpec, entity_name: str) -> dict[str, Any]:
    """Convert a field to JSON Schema property."""
    from dazzle.core.ir import FieldModifier

    schema: dict[str, Any] = {}

    # Map DAZZLE types to JSON Schema types
    type_mapping: dict[str, dict[str, Any]] = {
        "uuid": {"type": "string", "format": "uuid"},
        "str": {"type": "string"},
        "text": {"type": "string"},
        "int": {"type": "integer"},
        "float": {"type": "number"},
        "decimal": {"type": "string", "format": "decimal"},
        "bool": {"type": "boolean"},
        "date": {"type": "string", "format": "date"},
        "datetime": {"type": "string", "format": "date-time"},
        "time": {"type": "string", "format": "time"},
        "json": {"type": "object"},
        "email": {"type": "string", "format": "email"},
        "url": {"type": "string", "format": "uri"},
        "phone": {"type": "string"},
        "money": {"type": "string", "format": "decimal"},
        "state": {"type": "string"},
        "image": {"type": "string", "format": "uri"},
        "file": {"type": "string", "format": "uri"},
        "ref": {"type": "string", "format": "uuid"},
        "has_many": {"type": "array"},
        "has_one": {"type": "string", "format": "uuid"},
        "embeds": {"type": "object"},
        "belongs_to": {"type": "string", "format": "uuid"},
    }

    # Get type kind from FieldType
    type_kind = field.type.kind.value

    if type_kind in type_mapping:
        schema = type_mapping[type_kind].copy()
    elif type_kind == "enum":
        schema = {
            "type": "string",
            "enum": field.type.enum_values or [],
        }
    else:
        # Default to string for unknown types
        schema = {"type": "string"}

    # Add constraints from FieldType
    if field.type.max_length:
        schema["maxLength"] = field.type.max_length

    if field.default is not None:
        schema["default"] = field.default

    # Handle nullable (not required means nullable)
    is_required = FieldModifier.REQUIRED in field.modifiers
    if not is_required:
        # OpenAPI 3.1 uses type array for nullable
        if "type" in schema:
            schema["type"] = [schema["type"], "null"]

    # Mark sensitive fields with OpenAPI extension
    if FieldModifier.SENSITIVE in field.modifiers:
        schema["x-sensitive"] = True

    return schema


def _add_entity_paths(openapi: dict[str, Any], entity: EntitySpec) -> None:
    """Add CRUD paths for an entity."""
    paths = openapi["paths"]
    entity_name = entity.name
    entity_lower = entity_name.lower()
    base_path = f"/{entity_lower}s"
    item_path = f"{base_path}/{{{entity_lower}_id}}"

    # List endpoint
    paths[base_path] = {
        "get": {
            "summary": f"List all {entity_name}s",
            "operationId": f"list_{entity_lower}s",
            "tags": [entity_name],
            "parameters": [
                {
                    "name": "skip",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 0},
                },
                {
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 100, "maximum": 1000},
                },
            ],
            "responses": {
                "200": {
                    "description": f"List of {entity_name}s",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{entity_name}List"}
                        }
                    },
                },
            },
        },
        "post": {
            "summary": f"Create a new {entity_name}",
            "operationId": f"create_{entity_lower}",
            "tags": [entity_name],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{entity_name}Create"}
                    }
                },
            },
            "responses": {
                "201": {
                    "description": f"{entity_name} created successfully",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{entity_name}Read"}
                        }
                    },
                },
                "422": {
                    "description": "Validation error",
                },
            },
        },
    }

    # Item endpoints
    paths[item_path] = {
        "get": {
            "summary": f"Get a {entity_name} by ID",
            "operationId": f"get_{entity_lower}",
            "tags": [entity_name],
            "parameters": [
                {
                    "name": f"{entity_lower}_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {
                    "description": f"{entity_name} details",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{entity_name}Read"}
                        }
                    },
                },
                "404": {
                    "description": f"{entity_name} not found",
                },
            },
        },
        "put": {
            "summary": f"Update a {entity_name}",
            "operationId": f"update_{entity_lower}",
            "tags": [entity_name],
            "parameters": [
                {
                    "name": f"{entity_lower}_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{entity_name}Update"}
                    }
                },
            },
            "responses": {
                "200": {
                    "description": f"{entity_name} updated successfully",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{entity_name}Read"}
                        }
                    },
                },
                "404": {
                    "description": f"{entity_name} not found",
                },
                "422": {
                    "description": "Validation error",
                },
            },
        },
        "delete": {
            "summary": f"Delete a {entity_name}",
            "operationId": f"delete_{entity_lower}",
            "tags": [entity_name],
            "parameters": [
                {
                    "name": f"{entity_lower}_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "204": {
                    "description": f"{entity_name} deleted successfully",
                },
                "404": {
                    "description": f"{entity_name} not found",
                },
            },
        },
    }

    # Add state transition endpoints if entity has state machine
    if entity.state_machine:
        _add_transition_paths(openapi, entity)


def _add_transition_paths(
    openapi: dict[str, Any],
    entity: EntitySpec,
) -> None:
    """Add state transition endpoints."""
    paths = openapi["paths"]
    entity_name = entity.name
    entity_lower = entity_name.lower()

    if not entity.state_machine:
        return

    for transition in entity.state_machine.transitions:
        from_state = transition.from_state
        to_state = transition.to_state
        action_name = f"{from_state}_to_{to_state}"
        action_path = f"/{entity_lower}s/{{{entity_lower}_id}}/actions/{action_name}"

        if action_path not in paths:
            paths[action_path] = {}

        paths[action_path]["post"] = {
            "summary": f"Transition {entity_name} from {from_state} to {to_state}",
            "operationId": f"{entity_lower}_{action_name}",
            "tags": [entity_name],
            "parameters": [
                {
                    "name": f"{entity_lower}_id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                }
            ],
            "responses": {
                "200": {
                    "description": "Transition successful",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{entity_name}Read"}
                        }
                    },
                },
                "400": {
                    "description": "Transition not allowed from current state",
                },
                "404": {
                    "description": f"{entity_name} not found",
                },
            },
        }


def _pascal_case(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def openapi_to_yaml(openapi: dict[str, Any]) -> str:
    """Convert OpenAPI dict to YAML string."""
    try:
        import yaml

        return yaml.dump(openapi, default_flow_style=False, sort_keys=False)
    except ImportError:
        # Fallback to JSON if PyYAML not available
        import json

        return json.dumps(openapi, indent=2)


def openapi_to_json(openapi: dict[str, Any]) -> str:
    """Convert OpenAPI dict to JSON string."""
    import json

    return json.dumps(openapi, indent=2)
