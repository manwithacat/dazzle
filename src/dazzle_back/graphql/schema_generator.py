"""
Schema Generator - Convert BackendSpec to GraphQL schema.

Generates Strawberry GraphQL types from EntitySpec definitions.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

from dazzle_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

# Strawberry is optional - check availability
try:
    import strawberry
    from strawberry import ID

    STRAWBERRY_AVAILABLE = True
except ImportError:
    STRAWBERRY_AVAILABLE = False
    strawberry = None  # type: ignore
    ID = str  # type: ignore

if TYPE_CHECKING:
    from dazzle_back.specs import BackendSpec


class SchemaGenerator:
    """
    Generate Strawberry GraphQL types from BackendSpec.

    This generator creates:
    - Entity types (GraphQL object types)
    - Input types (for mutations)
    - Enum types (from field enum values)
    - Connection types (for pagination)

    Example:
        generator = SchemaGenerator(backend_spec)
        types = generator.generate_types()
        # types["Task"] is a Strawberry type for Task entity
    """

    def __init__(self, spec: BackendSpec) -> None:
        """
        Initialize the schema generator.

        Args:
            spec: BackendSpec to generate types from
        """
        if not STRAWBERRY_AVAILABLE:
            raise RuntimeError(
                "Strawberry is not installed. Install with: pip install strawberry-graphql"
            )
        self.spec = spec
        self._types: dict[str, type] = {}
        self._input_types: dict[str, type] = {}
        self._enum_types: dict[str, type] = {}

    def generate_types(self) -> dict[str, type]:
        """
        Generate all GraphQL types from the spec.

        Returns:
            Dictionary mapping entity names to Strawberry types
        """
        # First pass: generate enum types
        for entity in self.spec.entities:
            self._generate_enums_for_entity(entity)

        # Second pass: generate entity types
        for entity in self.spec.entities:
            self._generate_entity_type(entity)

        # Third pass: generate input types
        for entity in self.spec.entities:
            self._generate_input_types(entity)

        return self._types

    def get_type(self, name: str) -> type | None:
        """Get a generated type by name."""
        return self._types.get(name)

    def get_input_type(self, name: str) -> type | None:
        """Get a generated input type by name."""
        return self._input_types.get(name)

    def get_enum_type(self, name: str) -> type | None:
        """Get a generated enum type by name."""
        return self._enum_types.get(name)

    @property
    def types(self) -> dict[str, type]:
        """All generated entity types."""
        return self._types

    @property
    def input_types(self) -> dict[str, type]:
        """All generated input types."""
        return self._input_types

    @property
    def enum_types(self) -> dict[str, type]:
        """All generated enum types."""
        return self._enum_types

    def _generate_enums_for_entity(self, entity: EntitySpec) -> None:
        """Generate enum types for an entity's enum fields."""
        for field in entity.fields:
            if field.type.kind == "enum" and field.type.enum_values:
                enum_name = f"{entity.name}{_pascal_case(field.name)}Enum"
                if enum_name not in self._enum_types:
                    self._enum_types[enum_name] = self._create_enum_type(
                        enum_name, field.type.enum_values
                    )

    def _create_enum_type(self, name: str, values: list[str]) -> type:
        """Create a Strawberry enum type."""
        # Create Python enum
        enum_dict = {v.upper(): v for v in values}
        python_enum = Enum(name, enum_dict)

        # Create Strawberry enum
        return strawberry.enum(python_enum)

    def _generate_entity_type(self, entity: EntitySpec) -> None:
        """Generate a Strawberry type for an entity."""
        # Build field annotations
        annotations: dict[str, Any] = {}
        defaults: dict[str, Any] = {}

        # Always add id field
        annotations["id"] = ID

        for field in entity.fields:
            if field.name == "id":
                continue  # Already added

            py_type = self._field_type_to_python(entity, field)

            # Handle optional fields
            if not field.required:
                py_type = py_type | None
                defaults[field.name] = None

            annotations[field.name] = py_type

            # Handle defaults
            if field.default is not None:
                defaults[field.name] = field.default

        # Create the class dynamically
        type_dict: dict[str, Any] = {"__annotations__": annotations}
        type_dict.update(defaults)

        # Create the type
        entity_type = type(entity.name, (), type_dict)

        # Apply strawberry.type decorator
        self._types[entity.name] = strawberry.type(entity_type)

    def _generate_input_types(self, entity: EntitySpec) -> None:
        """Generate input types for create and update mutations."""
        # Create input type
        self._input_types[f"{entity.name}CreateInput"] = self._create_input_type(
            entity, f"{entity.name}CreateInput", for_create=True
        )

        # Update input type (all fields optional)
        self._input_types[f"{entity.name}UpdateInput"] = self._create_input_type(
            entity, f"{entity.name}UpdateInput", for_create=False
        )

    def _create_input_type(self, entity: EntitySpec, name: str, for_create: bool) -> type:
        """Create an input type for mutations."""
        annotations: dict[str, Any] = {}
        defaults: dict[str, Any] = {}

        for field in entity.fields:
            # Skip auto-generated fields
            if field.name in ("id", "created_at", "updated_at"):
                continue

            py_type = self._field_type_to_python(entity, field, for_input=True)

            # For update, all fields are optional
            # For create, use field.required
            is_optional = not for_create or not field.required
            if is_optional:
                py_type = py_type | None
                defaults[field.name] = None

            annotations[field.name] = py_type

            if field.default is not None:
                defaults[field.name] = field.default

        type_dict: dict[str, Any] = {"__annotations__": annotations}
        type_dict.update(defaults)

        input_type = type(name, (), type_dict)
        return strawberry.input(input_type)

    def _field_type_to_python(
        self,
        entity: EntitySpec,
        field: FieldSpec,
        for_input: bool = False,
    ) -> type:
        """Convert a FieldType to a Python type annotation."""
        field_type = field.type

        if field_type.kind == "scalar":
            return self._scalar_to_python(field_type)

        elif field_type.kind == "enum":
            enum_name = f"{entity.name}{_pascal_case(field.name)}Enum"
            return self._enum_types.get(enum_name, str)

        elif field_type.kind == "ref":
            if for_input:
                # For input types, refs are IDs
                return ID
            else:
                # For output types, could be nested type or ID
                # Default to ID for simplicity, can be enhanced with DataLoader
                return ID

        return str  # Fallback

    def _scalar_to_python(self, field_type: FieldType) -> type:
        """Convert a scalar FieldType to Python type."""
        if not field_type.scalar_type:
            return str

        mapping: dict[ScalarType, type] = {
            ScalarType.STR: str,
            ScalarType.TEXT: str,
            ScalarType.INT: int,
            ScalarType.DECIMAL: Decimal,
            ScalarType.BOOL: bool,
            ScalarType.DATE: date,
            ScalarType.DATETIME: datetime,
            ScalarType.UUID: ID,
            ScalarType.EMAIL: str,
            ScalarType.URL: str,
            ScalarType.JSON: strawberry.scalars.JSON,
            ScalarType.FILE: str,  # URL to file
            ScalarType.IMAGE: str,  # URL to image
            ScalarType.RICHTEXT: str,  # HTML/Markdown content
        }

        return mapping.get(field_type.scalar_type, str)


def _pascal_case(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def generate_schema_sdl(spec: BackendSpec) -> str:
    """
    Generate GraphQL SDL (Schema Definition Language) from BackendSpec.

    This is useful for documentation and schema-first development.

    Args:
        spec: BackendSpec to generate schema from

    Returns:
        GraphQL SDL string
    """
    lines: list[str] = []

    # Generate enum types
    for entity in spec.entities:
        for field in entity.fields:
            if field.type.kind == "enum" and field.type.enum_values:
                enum_name = f"{entity.name}{_pascal_case(field.name)}Enum"
                lines.append(f"enum {enum_name} {{")
                for value in field.type.enum_values:
                    lines.append(f"  {value.upper()}")
                lines.append("}")
                lines.append("")

    # Generate entity types
    for entity in spec.entities:
        description = entity.description or f"{entity.name} entity"
        lines.append(f'"""{description}"""')
        lines.append(f"type {entity.name} {{")
        lines.append("  id: ID!")

        for field in entity.fields:
            if field.name == "id":
                continue

            gql_type = _field_type_to_graphql(entity, field)
            required_mark = "!" if field.required else ""

            field_desc = field.label or field.name
            lines.append(f'  """{field_desc}"""')
            lines.append(f"  {field.name}: {gql_type}{required_mark}")

        lines.append("}")
        lines.append("")

    # Generate input types
    for entity in spec.entities:
        # Create input
        lines.append(f"input {entity.name}CreateInput {{")
        for field in entity.fields:
            if field.name in ("id", "created_at", "updated_at"):
                continue
            gql_type = _field_type_to_graphql(entity, field, for_input=True)
            required_mark = "!" if field.required else ""
            lines.append(f"  {field.name}: {gql_type}{required_mark}")
        lines.append("}")
        lines.append("")

        # Update input
        lines.append(f"input {entity.name}UpdateInput {{")
        for field in entity.fields:
            if field.name in ("id", "created_at", "updated_at"):
                continue
            gql_type = _field_type_to_graphql(entity, field, for_input=True)
            lines.append(f"  {field.name}: {gql_type}")
        lines.append("}")
        lines.append("")

    # Generate Query type
    lines.append("type Query {")
    for entity in spec.entities:
        entity_lower = _camel_case(entity.name)
        lines.append(f"  {entity_lower}(id: ID!): {entity.name}")
        lines.append(f"  {entity_lower}s(limit: Int, offset: Int): [{entity.name}!]!")
    lines.append("}")
    lines.append("")

    # Generate Mutation type
    lines.append("type Mutation {")
    for entity in spec.entities:
        entity_lower = _camel_case(entity.name)
        lines.append(f"  create{entity.name}(input: {entity.name}CreateInput!): {entity.name}!")
        lines.append(
            f"  update{entity.name}(id: ID!, input: {entity.name}UpdateInput!): {entity.name}!"
        )
        lines.append(f"  delete{entity.name}(id: ID!): Boolean!")
    lines.append("}")

    return "\n".join(lines)


def _field_type_to_graphql(entity: EntitySpec, field: FieldSpec, for_input: bool = False) -> str:
    """Convert a FieldType to GraphQL type string."""
    field_type = field.type

    if field_type.kind == "scalar":
        return _scalar_to_graphql(field_type)

    elif field_type.kind == "enum":
        return f"{entity.name}{_pascal_case(field.name)}Enum"

    elif field_type.kind == "ref":
        return "ID"

    return "String"


def _scalar_to_graphql(field_type: FieldType) -> str:
    """Convert a scalar FieldType to GraphQL type string."""
    if not field_type.scalar_type:
        return "String"

    mapping: dict[ScalarType, str] = {
        ScalarType.STR: "String",
        ScalarType.TEXT: "String",
        ScalarType.INT: "Int",
        ScalarType.DECIMAL: "Float",
        ScalarType.BOOL: "Boolean",
        ScalarType.DATE: "String",  # ISO date string
        ScalarType.DATETIME: "String",  # ISO datetime string
        ScalarType.UUID: "ID",
        ScalarType.EMAIL: "String",
        ScalarType.URL: "String",
        ScalarType.JSON: "JSON",
        ScalarType.FILE: "String",
        ScalarType.IMAGE: "String",
        ScalarType.RICHTEXT: "String",
    }

    return mapping.get(field_type.scalar_type, "String")


def _camel_case(name: str) -> str:
    """Convert PascalCase to camelCase."""
    if not name:
        return name
    return name[0].lower() + name[1:]
