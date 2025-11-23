"""
OpenAPI 3.0 backend for DAZZLE.

Generates OpenAPI specifications from AppSpec.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..core import ir
from ..core.errors import BackendError
from . import Backend, BackendCapabilities

if TYPE_CHECKING:
    from ..core.changes import ChangeSet


class OpenAPIBackend(Backend):
    """
    Generate OpenAPI 3.0 specifications from DAZZLE AppSpec.

    Maps DAZZLE concepts to OpenAPI:
    - Entities → Schemas (components/schemas)
    - Surfaces (list) → GET /resource
    - Surfaces (view) → GET /resource/{id}
    - Surfaces (create) → POST /resource
    - Surfaces (edit) → PUT/PATCH /resource/{id}
    - Experiences → Operation links (operationId references)
    """

    def generate(
        self, appspec: ir.AppSpec, output_dir: Path, format: str = "yaml", **options
    ) -> None:
        """
        Generate OpenAPI 3.0 specification.

        Args:
            appspec: Validated application specification
            output_dir: Output directory for generated files
            format: Output format ("yaml" or "json")
            **options: Additional options

        Raises:
            BackendError: If generation fails
        """
        try:
            # Ensure output directory exists
            output_dir.mkdir(parents=True, exist_ok=True)

            # Build OpenAPI document
            openapi_doc = self._build_openapi_document(appspec)

            # Write output
            if format == "yaml":
                output_file = output_dir / "openapi.yaml"
                self._write_yaml(openapi_doc, output_file)
            elif format == "json":
                output_file = output_dir / "openapi.json"
                self._write_json(openapi_doc, output_file)
            else:
                raise BackendError(f"Unsupported format: {format}. Use 'yaml' or 'json'.")

        except Exception as e:
            if isinstance(e, BackendError):
                raise
            raise BackendError(f"Failed to generate OpenAPI spec: {e}")

    def generate_incremental(
        self,
        appspec: ir.AppSpec,
        output_dir: Path,
        changeset: "ChangeSet",
        format: str = "yaml",
        **options,
    ) -> None:
        """
        Generate OpenAPI 3.0 specification incrementally.

        For OpenAPI, incremental generation means:
        - If only entities/surfaces changed, regenerate the full spec (fast anyway)
        - Skip generation if no relevant changes

        Args:
            appspec: Current AppSpec
            output_dir: Output directory
            changeset: Detected changes
            format: Output format ("yaml" or "json")
            **options: Additional options

        Raises:
            BackendError: If generation fails
        """
        # For OpenAPI, incremental is simple: just regenerate if there are changes
        # The spec is small and generation is fast, so no need for complex merging

        # Check if there are any changes relevant to OpenAPI
        has_relevant_changes = (
            changeset.entities_added
            or changeset.entities_modified
            or changeset.entities_removed
            or changeset.surfaces_added
            or changeset.surfaces_modified
            or changeset.surfaces_removed
            or changeset.app_modified
        )

        if not has_relevant_changes:
            # No changes that affect OpenAPI, skip
            return

        # Regenerate full spec (fast for OpenAPI)
        self.generate(appspec, output_dir, format=format, **options)

    def get_capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            name="openapi",
            description="Generate OpenAPI 3.0 specifications from AppSpec",
            output_formats=["yaml", "json"],
            supports_incremental=True,
            requires_config=False,
        )

    def validate_config(self, format: str = "yaml", **options) -> None:
        """Validate backend configuration."""
        if format not in ("yaml", "json"):
            raise BackendError(f"Invalid format: {format}. Must be 'yaml' or 'json'.")

    def _build_openapi_document(self, appspec: ir.AppSpec) -> dict[str, Any]:
        """Build complete OpenAPI 3.0 document."""
        doc = {
            "openapi": "3.0.0",
            "info": self._build_info(appspec),
            "paths": self._build_paths(appspec),
            "components": {
                "schemas": self._build_schemas(appspec),
                "securitySchemes": self._build_security_schemes(appspec),
            },
        }

        # Add tags if we have entities
        if appspec.domain.entities:
            doc["tags"] = self._build_tags(appspec)

        return doc

    def _build_info(self, appspec: ir.AppSpec) -> dict[str, Any]:
        """Build OpenAPI info section."""
        info = {
            "title": appspec.title or appspec.name,
            "version": appspec.version,
        }

        return info

    def _build_schemas(self, appspec: ir.AppSpec) -> dict[str, Any]:
        """Build OpenAPI schemas from entities."""
        schemas = {}

        for entity in appspec.domain.entities:
            schemas[entity.name] = self._entity_to_schema(entity)

        return schemas

    def _entity_to_schema(self, entity: ir.EntitySpec) -> dict[str, Any]:
        """Convert DAZZLE entity to OpenAPI schema."""
        schema = {
            "type": "object",
            "properties": {},
        }

        if entity.title:
            schema["title"] = entity.title

        # Add fields as properties
        required_fields = []
        for field in entity.fields:
            schema["properties"][field.name] = self._field_to_property(field)

            # Track required fields
            if ir.FieldModifier.REQUIRED in field.modifiers:
                required_fields.append(field.name)

        if required_fields:
            schema["required"] = required_fields

        return schema

    def _field_to_property(self, field: ir.FieldSpec) -> dict[str, Any]:
        """Convert DAZZLE field to OpenAPI property."""
        prop: dict[str, Any] = {}

        # Map field types to OpenAPI types
        if field.type.kind == ir.FieldTypeKind.STR:
            prop["type"] = "string"
            if field.type.max_length:
                prop["maxLength"] = field.type.max_length

        elif field.type.kind == ir.FieldTypeKind.TEXT:
            prop["type"] = "string"

        elif field.type.kind == ir.FieldTypeKind.INT:
            prop["type"] = "integer"
            prop["format"] = "int64"

        elif field.type.kind == ir.FieldTypeKind.DECIMAL:
            prop["type"] = "string"
            prop["format"] = "decimal"
            if field.type.precision and field.type.scale:
                prop["description"] = f"Decimal({field.type.precision},{field.type.scale})"

        elif field.type.kind == ir.FieldTypeKind.BOOL:
            prop["type"] = "boolean"

        elif field.type.kind == ir.FieldTypeKind.DATE:
            prop["type"] = "string"
            prop["format"] = "date"

        elif field.type.kind == ir.FieldTypeKind.DATETIME:
            prop["type"] = "string"
            prop["format"] = "date-time"

        elif field.type.kind == ir.FieldTypeKind.UUID:
            prop["type"] = "string"
            prop["format"] = "uuid"

        elif field.type.kind == ir.FieldTypeKind.EMAIL:
            prop["type"] = "string"
            prop["format"] = "email"

        elif field.type.kind == ir.FieldTypeKind.ENUM:
            prop["type"] = "string"
            if field.type.enum_values:
                prop["enum"] = field.type.enum_values

        elif field.type.kind == ir.FieldTypeKind.REF:
            # Reference to another entity (use UUID for FK)
            prop["type"] = "string"
            prop["format"] = "uuid"
            if field.type.ref_entity:
                prop["description"] = f"Reference to {field.type.ref_entity}"

        else:
            # Unknown type - default to string
            prop["type"] = "string"

        return prop

    def _build_paths(self, appspec: ir.AppSpec) -> dict[str, Any]:
        """Build OpenAPI paths from surfaces."""
        paths: dict[str, Any] = {}

        for surface in appspec.surfaces:
            if not surface.entity_ref:
                # Skip surfaces without entity reference
                continue

            entity = appspec.get_entity(surface.entity_ref)
            if not entity:
                continue

            # Determine base path from entity name (pluralized, lowercase)
            base_path = f"/{self._pluralize(entity.name.lower())}"

            # Generate paths based on surface mode
            if surface.mode == ir.SurfaceMode.LIST:
                # GET /resources - list all
                if base_path not in paths:
                    paths[base_path] = {}
                paths[base_path]["get"] = self._build_list_operation(surface, entity)

            elif surface.mode == ir.SurfaceMode.VIEW:
                # GET /resources/{id} - get one
                detail_path = f"{base_path}/{{id}}"
                if detail_path not in paths:
                    paths[detail_path] = {}
                paths[detail_path]["get"] = self._build_view_operation(surface, entity)

            elif surface.mode == ir.SurfaceMode.CREATE:
                # POST /resources - create new
                if base_path not in paths:
                    paths[base_path] = {}
                paths[base_path]["post"] = self._build_create_operation(surface, entity)

            elif surface.mode == ir.SurfaceMode.EDIT:
                # PUT /resources/{id} - update existing
                detail_path = f"{base_path}/{{id}}"
                if detail_path not in paths:
                    paths[detail_path] = {}
                paths[detail_path]["put"] = self._build_edit_operation(surface, entity)

        return paths

    def _build_list_operation(
        self, surface: ir.SurfaceSpec, entity: ir.EntitySpec
    ) -> dict[str, Any]:
        """Build OpenAPI operation for list mode surface."""
        operation = {
            "summary": surface.title or f"List {entity.name} records",
            "operationId": f"list{entity.name}",
            "tags": [entity.name],
            "responses": {
                "200": {
                    "description": "Successful response",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "array",
                                "items": {"$ref": f"#/components/schemas/{entity.name}"},
                            }
                        }
                    },
                }
            },
        }

        return operation

    def _build_view_operation(
        self, surface: ir.SurfaceSpec, entity: ir.EntitySpec
    ) -> dict[str, Any]:
        """Build OpenAPI operation for view mode surface."""
        operation = {
            "summary": surface.title or f"Get {entity.name} by ID",
            "operationId": f"get{entity.name}",
            "tags": [entity.name],
            "parameters": [
                {
                    "name": "id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                    "description": f"{entity.name} ID",
                }
            ],
            "responses": {
                "200": {
                    "description": "Successful response",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{entity.name}"}
                        }
                    },
                },
                "404": {"description": f"{entity.name} not found"},
            },
        }

        return operation

    def _build_create_operation(
        self, surface: ir.SurfaceSpec, entity: ir.EntitySpec
    ) -> dict[str, Any]:
        """Build OpenAPI operation for create mode surface."""
        operation = {
            "summary": surface.title or f"Create new {entity.name}",
            "operationId": f"create{entity.name}",
            "tags": [entity.name],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/{entity.name}"}}
                },
            },
            "responses": {
                "201": {
                    "description": f"{entity.name} created successfully",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{entity.name}"}
                        }
                    },
                },
                "400": {"description": "Invalid input"},
            },
        }

        return operation

    def _build_edit_operation(
        self, surface: ir.SurfaceSpec, entity: ir.EntitySpec
    ) -> dict[str, Any]:
        """Build OpenAPI operation for edit mode surface."""
        operation = {
            "summary": surface.title or f"Update {entity.name}",
            "operationId": f"update{entity.name}",
            "tags": [entity.name],
            "parameters": [
                {
                    "name": "id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "format": "uuid"},
                    "description": f"{entity.name} ID",
                }
            ],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/{entity.name}"}}
                },
            },
            "responses": {
                "200": {
                    "description": f"{entity.name} updated successfully",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{entity.name}"}
                        }
                    },
                },
                "404": {"description": f"{entity.name} not found"},
                "400": {"description": "Invalid input"},
            },
        }

        return operation

    def _build_tags(self, appspec: ir.AppSpec) -> list[dict[str, str]]:
        """Build OpenAPI tags from entities."""
        tags = []
        for entity in appspec.domain.entities:
            tag = {"name": entity.name}
            if entity.title:
                tag["description"] = entity.title
            tags.append(tag)
        return tags

    def _build_security_schemes(self, appspec: ir.AppSpec) -> dict[str, Any]:
        """Build OpenAPI security schemes (placeholder for now)."""
        # For v0.1, we'll use a simple bearer token scheme
        return {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}}

    def _pluralize(self, name: str) -> str:
        """Simple pluralization (just add 's' for now)."""
        if name.endswith("y"):
            return name[:-1] + "ies"
        elif name.endswith("s"):
            return name + "es"
        else:
            return name + "s"

    def _write_yaml(self, doc: dict[str, Any], output_file: Path) -> None:
        """Write OpenAPI document as YAML."""
        try:
            import yaml

            with output_file.open("w") as f:
                yaml.dump(doc, f, default_flow_style=False, sort_keys=False)
        except ImportError:
            raise BackendError("PyYAML not installed. Install with: pip install pyyaml")

    def _write_json(self, doc: dict[str, Any], output_file: Path) -> None:
        """Write OpenAPI document as JSON."""
        with output_file.open("w") as f:
            json.dump(doc, f, indent=2)
