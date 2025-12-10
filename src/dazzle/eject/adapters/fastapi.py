"""
FastAPI backend adapter.

Generates a complete FastAPI application from AppSpec including:
- Pydantic models and schemas
- CRUD routers with proper typing
- State machine guards
- Invariant validators
- Access control policies
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent, indent
from typing import TYPE_CHECKING

from dazzle.stacks.base.generator import GeneratorResult
from .base import BackendAdapter, AdapterRegistry

if TYPE_CHECKING:
    from dazzle.core.ir import (
        AppSpec,
        EntitySpec,
        FieldSpec,
        FieldType,
        FieldTypeKind,
        StateMachineSpec,
        InvariantSpec,
        AccessSpec,
    )
    from dazzle.eject.config import EjectionBackendConfig


class FastAPIAdapter(BackendAdapter):
    """Generate FastAPI application from AppSpec."""

    # Type mappings from DSL to Python
    TYPE_MAPPING = {
        "str": "str",
        "text": "str",
        "int": "int",
        "decimal": "Decimal",
        "bool": "bool",
        "date": "date",
        "datetime": "datetime",
        "uuid": "UUID",
        "email": "EmailStr",
        "ref": "UUID",  # Foreign key
        "has_many": "list",  # Will be customized
        "has_one": "Optional",
        "embeds": "dict",  # Embedded object
        "belongs_to": "UUID",
    }

    def __init__(
        self,
        spec: "AppSpec",
        output_dir: Path,
        config: "EjectionBackendConfig",
    ):
        super().__init__(spec, output_dir, config)
        self.backend_dir = output_dir / "backend"

    def generate_config(self) -> GeneratorResult:
        """Generate configuration module."""
        result = GeneratorResult()

        config_path = self.backend_dir / "config.py"
        content = dedent('''
            """
            Application configuration.
            Generated from DSL - DO NOT EDIT.
            """
            from functools import lru_cache
            from pydantic_settings import BaseSettings


            class Settings(BaseSettings):
                """Application settings loaded from environment."""

                # Application
                app_name: str = "{app_name}"
                debug: bool = False

                # Database
                database_url: str = "sqlite:///./app.db"

                # Authentication
                secret_key: str = "change-me-in-production"
                access_token_expire_minutes: int = 30

                # CORS
                cors_origins: list[str] = ["http://localhost:3000"]

                class Config:
                    env_file = ".env"
                    env_file_encoding = "utf-8"


            @lru_cache
            def get_settings() -> Settings:
                """Get cached settings instance."""
                return Settings()
        ''').format(app_name=self.spec.name)

        self._write_file(config_path, content.strip())
        result.add_file(config_path)

        # Also create __init__.py
        init_path = self.backend_dir / "__init__.py"
        self._write_file(init_path, '"""Generated FastAPI backend."""\n')
        result.add_file(init_path)

        return result

    def generate_models(self) -> GeneratorResult:
        """Generate entity models."""
        result = GeneratorResult()

        models_dir = self.backend_dir / "models"
        self._ensure_dir(models_dir)

        # Generate base model
        base_content = self._generate_base_model()
        base_path = models_dir / "base.py"
        self._write_file(base_path, base_content)
        result.add_file(base_path)

        # Generate model for each entity
        imports = ['"""Entity models."""\n']
        for entity in self.spec.domain.entities:
            model_content = self._generate_entity_model(entity)
            model_path = models_dir / f"{self._snake_case(entity.name)}.py"
            self._write_file(model_path, model_content)
            result.add_file(model_path)
            imports.append(
                f"from .{self._snake_case(entity.name)} import {entity.name}"
            )

        # Generate __init__.py
        init_content = "\n".join(imports) + "\n"
        init_path = models_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result

    def _generate_base_model(self) -> str:
        """Generate base model with common fields."""
        return dedent('''
            """
            Base model with common functionality.
            Generated from DSL - DO NOT EDIT.
            """
            from datetime import datetime
            from uuid import UUID, uuid4

            from sqlalchemy import Column, DateTime, String
            from sqlalchemy.dialects.postgresql import UUID as PGUUID
            from sqlalchemy.ext.declarative import declarative_base

            Base = declarative_base()


            class TimestampMixin:
                """Mixin for created_at and updated_at fields."""

                created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
                updated_at = Column(
                    DateTime,
                    default=datetime.utcnow,
                    onupdate=datetime.utcnow,
                    nullable=False,
                )


            class UUIDMixin:
                """Mixin for UUID primary key."""

                id = Column(
                    PGUUID(as_uuid=True),
                    primary_key=True,
                    default=uuid4,
                )
        ''').strip()

    def _generate_entity_model(self, entity: "EntitySpec") -> str:
        """Generate SQLAlchemy model for an entity."""
        lines = [
            '"""',
            f"{entity.name} entity model.",
            "Generated from DSL - DO NOT EDIT.",
            '"""',
            "from datetime import date, datetime",
            "from decimal import Decimal",
            "from enum import Enum",
            "from typing import Optional",
            "from uuid import UUID",
            "",
            "from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, Numeric, Text, ForeignKey, Enum as SQLEnum",
            "from sqlalchemy.dialects.postgresql import UUID as PGUUID",
            "from sqlalchemy.orm import relationship",
            "",
            "from .base import Base, TimestampMixin",
            "",
        ]

        # Generate enums
        for field in entity.fields:
            if field.type.kind.value == "enum" and field.type.enum_values:
                enum_name = f"{entity.name}{self._pascal_case(field.name)}"
                lines.append(f"class {enum_name}(str, Enum):")
                for val in field.type.enum_values:
                    lines.append(f'    {val.upper()} = "{val}"')
                lines.append("")

        # Generate model class
        has_timestamps = any(
            f.name in ("created_at", "updated_at") for f in entity.fields
        )
        mixins = ", TimestampMixin" if has_timestamps else ""

        # Add intent as docstring if present
        if entity.intent:
            lines.append(f'class {entity.name}(Base{mixins}):')
            lines.append(f'    """')
            lines.append(f'    {entity.intent}')
            lines.append(f'    """')
        else:
            lines.append(f'class {entity.name}(Base{mixins}):')
            lines.append(f'    """{entity.title or entity.name} entity."""')

        lines.append(f'    __tablename__ = "{self._snake_case(entity.name)}s"')
        lines.append("")

        # Generate columns
        for field in entity.fields:
            # Skip timestamp fields if using mixin
            if has_timestamps and field.name in ("created_at", "updated_at"):
                continue

            column_def = self._generate_column(field, entity)
            if column_def:
                lines.append(f"    {column_def}")

        return "\n".join(lines)

    def _generate_column(self, field: "FieldSpec", entity: "EntitySpec") -> str:
        """Generate SQLAlchemy column definition."""
        kind = field.type.kind.value

        # Handle primary key
        if field.is_primary_key:
            return f'{field.name} = Column(PGUUID(as_uuid=True), primary_key=True)'

        # Handle relationships
        if kind == "ref":
            ref_entity = field.type.ref_entity
            ref_table = self._snake_case(ref_entity) + "s"
            nullable = "False" if field.is_required else "True"
            return f'{field.name}_id = Column(PGUUID(as_uuid=True), ForeignKey("{ref_table}.id"), nullable={nullable})'

        if kind in ("has_many", "has_one", "belongs_to"):
            # These are relationship fields, handled separately
            ref_entity = field.type.ref_entity
            if kind == "has_many":
                return f'{field.name} = relationship("{ref_entity}", back_populates="{self._snake_case(entity.name)}")'
            elif kind == "belongs_to":
                return f'{field.name} = relationship("{ref_entity}", back_populates="{self._snake_case(entity.name)}s")'
            return ""

        # Handle enums
        if kind == "enum":
            enum_name = f"{entity.name}{self._pascal_case(field.name)}"
            nullable = "False" if field.is_required else "True"
            default = f', default={enum_name}.{field.default.upper()}' if field.default else ""
            return f'{field.name} = Column(SQLEnum({enum_name}), nullable={nullable}{default})'

        # Handle basic types
        col_type = self._get_column_type(field.type)
        nullable = "False" if field.is_required else "True"
        default = f", default={repr(field.default)}" if field.default is not None else ""

        return f'{field.name} = Column({col_type}, nullable={nullable}{default})'

    def _get_column_type(self, field_type: "FieldType") -> str:
        """Get SQLAlchemy column type."""
        kind = field_type.kind.value

        if kind == "str":
            max_len = field_type.max_length or 255
            return f"String({max_len})"
        elif kind == "text":
            return "Text"
        elif kind == "int":
            return "Integer"
        elif kind == "decimal":
            precision = field_type.precision or 10
            scale = field_type.scale or 2
            return f"Numeric({precision}, {scale})"
        elif kind == "bool":
            return "Boolean"
        elif kind == "date":
            return "Date"
        elif kind == "datetime":
            return "DateTime"
        elif kind == "uuid":
            return "PGUUID(as_uuid=True)"
        elif kind == "email":
            return "String(255)"
        else:
            return "String(255)"

    def generate_schemas(self) -> GeneratorResult:
        """Generate Pydantic request/response schemas."""
        result = GeneratorResult()

        schemas_dir = self.backend_dir / "schemas"
        self._ensure_dir(schemas_dir)

        imports = ['"""Request/response schemas."""\n']

        for entity in self.spec.domain.entities:
            schema_content = self._generate_entity_schemas(entity)
            schema_path = schemas_dir / f"{self._snake_case(entity.name)}.py"
            self._write_file(schema_path, schema_content)
            result.add_file(schema_path)

            name = entity.name
            imports.append(
                f"from .{self._snake_case(name)} import {name}Base, {name}Create, {name}Update, {name}Read"
            )

        # Generate __init__.py
        init_content = "\n".join(imports) + "\n"
        init_path = schemas_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result

    def _generate_entity_schemas(self, entity: "EntitySpec") -> str:
        """Generate Pydantic schemas for an entity."""
        lines = [
            '"""',
            f"Pydantic schemas for {entity.name}.",
            "Generated from DSL - DO NOT EDIT.",
            '"""',
            "from datetime import date, datetime",
            "from decimal import Decimal",
            "from enum import Enum",
            "from typing import Optional",
            "from uuid import UUID",
            "",
            "from pydantic import BaseModel, Field, EmailStr, ConfigDict",
            "",
        ]

        # Generate enums (same as models)
        for field in entity.fields:
            if field.type.kind.value == "enum" and field.type.enum_values:
                enum_name = f"{entity.name}{self._pascal_case(field.name)}"
                lines.append(f"class {enum_name}(str, Enum):")
                for val in field.type.enum_values:
                    lines.append(f'    {val.upper()} = "{val}"')
                lines.append("")

        # Base schema (shared fields)
        lines.append(f"class {entity.name}Base(BaseModel):")
        if entity.intent:
            lines.append(f'    """{entity.intent}"""')
        lines.append("")

        writable_fields = [
            f for f in entity.fields
            if not f.is_primary_key
            and f.name not in ("created_at", "updated_at")
            and f.type.kind.value not in ("has_many", "has_one", "belongs_to")
        ]

        for field in writable_fields:
            field_def = self._generate_pydantic_field(field, entity)
            lines.append(f"    {field_def}")

        if not writable_fields:
            lines.append("    pass")

        lines.append("")

        # Create schema
        lines.append(f"class {entity.name}Create({entity.name}Base):")
        lines.append('    """Schema for creating a new record."""')
        lines.append("    pass")
        lines.append("")

        # Update schema (all optional)
        lines.append(f"class {entity.name}Update(BaseModel):")
        lines.append('    """Schema for updating a record."""')
        for field in writable_fields:
            field_def = self._generate_pydantic_field(field, entity, optional=True)
            lines.append(f"    {field_def}")
        if not writable_fields:
            lines.append("    pass")
        lines.append("")

        # Read schema (includes all fields)
        lines.append(f"class {entity.name}Read({entity.name}Base):")
        lines.append('    """Schema for reading a record."""')
        lines.append("    model_config = ConfigDict(from_attributes=True)")
        lines.append("")
        lines.append("    id: UUID")

        # Add computed fields as read-only
        for cf in entity.computed_fields:
            # Infer type from expression (simplified)
            lines.append(f"    {cf.name}: Optional[str] = None  # Computed field")

        # Add timestamps if present
        has_created = any(f.name == "created_at" for f in entity.fields)
        has_updated = any(f.name == "updated_at" for f in entity.fields)
        if has_created:
            lines.append("    created_at: datetime")
        if has_updated:
            lines.append("    updated_at: datetime")

        return "\n".join(lines)

    def _generate_pydantic_field(
        self,
        field: "FieldSpec",
        entity: "EntitySpec",
        optional: bool = False,
    ) -> str:
        """Generate Pydantic field definition."""
        kind = field.type.kind.value
        py_type = self._get_python_type(field, entity)

        if optional or not field.is_required:
            py_type = f"Optional[{py_type}]"

        default = ""
        if field.default is not None:
            if kind == "enum":
                enum_name = f"{entity.name}{self._pascal_case(field.name)}"
                default = f" = {enum_name}.{str(field.default).upper()}"
            elif kind == "bool":
                default = f" = {field.default}"
            elif kind == "str" or kind == "text":
                default = f' = "{field.default}"'
            else:
                default = f" = {field.default}"
        elif optional or not field.is_required:
            default = " = None"

        return f"{field.name}: {py_type}{default}"

    def _get_python_type(self, field: "FieldSpec", entity: "EntitySpec") -> str:
        """Get Python type annotation for a field."""
        kind = field.type.kind.value

        if kind == "enum":
            return f"{entity.name}{self._pascal_case(field.name)}"
        elif kind == "str":
            return "str"
        elif kind == "text":
            return "str"
        elif kind == "int":
            return "int"
        elif kind == "decimal":
            return "Decimal"
        elif kind == "bool":
            return "bool"
        elif kind == "date":
            return "date"
        elif kind == "datetime":
            return "datetime"
        elif kind == "uuid":
            return "UUID"
        elif kind == "email":
            return "EmailStr"
        elif kind == "ref":
            return "UUID"
        else:
            return "str"

    def generate_routers(self) -> GeneratorResult:
        """Generate API routers."""
        result = GeneratorResult()

        routers_dir = self.backend_dir / "routers"
        self._ensure_dir(routers_dir)

        imports = ['"""API routers."""\n']

        for entity in self.spec.domain.entities:
            router_content = self._generate_entity_router(entity)
            router_path = routers_dir / f"{self._snake_case(entity.name)}.py"
            self._write_file(router_path, router_content)
            result.add_file(router_path)

            imports.append(
                f"from .{self._snake_case(entity.name)} import router as {self._snake_case(entity.name)}_router"
            )

        # Generate __init__.py
        init_content = "\n".join(imports) + "\n"
        init_path = routers_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result

    def _generate_entity_router(self, entity: "EntitySpec") -> str:
        """Generate FastAPI router for an entity."""
        name = entity.name
        snake = self._snake_case(name)
        async_prefix = "async " if self.config.async_handlers else ""
        await_prefix = "await " if self.config.async_handlers else ""

        content = dedent(f'''
            """
            {name} API router.
            Generated from DSL - DO NOT EDIT.
            """
            from typing import Optional
            from uuid import UUID

            from fastapi import APIRouter, Depends, HTTPException, Query

            from ..schemas.{snake} import {name}Create, {name}Update, {name}Read
            from ..services.{snake} import {name}Service
            from ..access.context import get_request_context, RequestContext

            router = APIRouter(prefix="/{snake}s", tags=["{name}"])


            @router.get("", response_model=list[{name}Read])
            {async_prefix}def list_{snake}s(
                skip: int = Query(0, ge=0),
                limit: int = Query(100, ge=1, le=1000),
                context: RequestContext = Depends(get_request_context),
            ) -> list[{name}Read]:
                """List all {name} records."""
                service = {name}Service()
                return {await_prefix}service.list(skip=skip, limit=limit, context=context)


            @router.get("/{{id}}", response_model={name}Read)
            {async_prefix}def get_{snake}(
                id: UUID,
                context: RequestContext = Depends(get_request_context),
            ) -> {name}Read:
                """Get a {name} by ID."""
                service = {name}Service()
                result = {await_prefix}service.get(id, context=context)
                if result is None:
                    raise HTTPException(status_code=404, detail="{name} not found")
                return result


            @router.post("", response_model={name}Read, status_code=201)
            {async_prefix}def create_{snake}(
                data: {name}Create,
                context: RequestContext = Depends(get_request_context),
            ) -> {name}Read:
                """Create a new {name}."""
                service = {name}Service()
                return {await_prefix}service.create(data, context=context)


            @router.patch("/{{id}}", response_model={name}Read)
            {async_prefix}def update_{snake}(
                id: UUID,
                data: {name}Update,
                context: RequestContext = Depends(get_request_context),
            ) -> {name}Read:
                """Update a {name}."""
                service = {name}Service()
                result = {await_prefix}service.update(id, data, context=context)
                if result is None:
                    raise HTTPException(status_code=404, detail="{name} not found")
                return result


            @router.delete("/{{id}}", status_code=204)
            {async_prefix}def delete_{snake}(
                id: UUID,
                context: RequestContext = Depends(get_request_context),
            ) -> None:
                """Delete a {name}."""
                service = {name}Service()
                success = {await_prefix}service.delete(id, context=context)
                if not success:
                    raise HTTPException(status_code=404, detail="{name} not found")
        ''')

        return content.strip()

    def generate_services(self) -> GeneratorResult:
        """Generate business logic services."""
        result = GeneratorResult()

        services_dir = self.backend_dir / "services"
        self._ensure_dir(services_dir)

        imports = ['"""Business logic services."""\n']

        for entity in self.spec.domain.entities:
            service_content = self._generate_entity_service(entity)
            service_path = services_dir / f"{self._snake_case(entity.name)}.py"
            self._write_file(service_path, service_content)
            result.add_file(service_path)

            imports.append(
                f"from .{self._snake_case(entity.name)} import {entity.name}Service"
            )

        # Generate __init__.py
        init_content = "\n".join(imports) + "\n"
        init_path = services_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result

    def _generate_entity_service(self, entity: "EntitySpec") -> str:
        """Generate service class for an entity."""
        name = entity.name
        snake = self._snake_case(name)

        # Check for state machine and invariants
        has_state_machine = entity.state_machine is not None
        has_invariants = len(entity.invariants) > 0
        has_access = entity.access is not None

        guard_import = f"\nfrom ..guards.{snake}_transitions import {name}TransitionGuard" if has_state_machine else ""
        validator_import = f"\nfrom ..validators.{snake}_invariants import {name}InvariantValidator" if has_invariants else ""
        access_import = f"\nfrom ..access.policies import {name}AccessPolicy" if has_access else ""

        guard_init = f"\n        self.guard = {name}TransitionGuard()" if has_state_machine else ""
        validator_init = f"\n        self.validator = {name}InvariantValidator()" if has_invariants else ""
        access_init = f"\n        self.access = {name}AccessPolicy()" if has_access else ""

        validate_call = "\n        self.validator.validate(entity)" if has_invariants else ""

        content = dedent(f'''
            """
            {name} business logic service.
            Generated from DSL - DO NOT EDIT.
            """
            from typing import Optional
            from uuid import UUID

            from ..schemas.{snake} import {name}Create, {name}Update, {name}Read
            from ..access.context import RequestContext{guard_import}{validator_import}{access_import}


            class {name}Service:
                """Service for {name} operations."""

                def __init__(self):
                    """Initialize service with validators and guards."""{guard_init}{validator_init}{access_init}
                    pass

                def list(
                    self,
                    skip: int = 0,
                    limit: int = 100,
                    context: Optional[RequestContext] = None,
                ) -> list[{name}Read]:
                    """
                    List {name} records.

                    TODO: Implement database query with access filtering.
                    """
                    # TODO: Implement with SQLAlchemy session
                    return []

                def get(
                    self,
                    id: UUID,
                    context: Optional[RequestContext] = None,
                ) -> Optional[{name}Read]:
                    """
                    Get a {name} by ID.

                    TODO: Implement database lookup with access check.
                    """
                    # TODO: Implement with SQLAlchemy session
                    return None

                def create(
                    self,
                    data: {name}Create,
                    context: Optional[RequestContext] = None,
                ) -> {name}Read:
                    """
                    Create a new {name}.

                    TODO: Implement with invariant validation.
                    """
                    # TODO: Implement with SQLAlchemy session{validate_call}
                    raise NotImplementedError("Create not implemented")

                def update(
                    self,
                    id: UUID,
                    data: {name}Update,
                    context: Optional[RequestContext] = None,
                ) -> Optional[{name}Read]:
                    """
                    Update a {name}.

                    TODO: Implement with state machine guards and invariant validation.
                    """
                    # TODO: Implement with SQLAlchemy session{validate_call}
                    return None

                def delete(
                    self,
                    id: UUID,
                    context: Optional[RequestContext] = None,
                ) -> bool:
                    """
                    Delete a {name}.

                    TODO: Implement with access check.
                    """
                    # TODO: Implement with SQLAlchemy session
                    return False
        ''')

        return content.strip()

    def generate_guards(self) -> GeneratorResult:
        """Generate state machine transition guards."""
        result = GeneratorResult()

        guards_dir = self.backend_dir / "guards"
        self._ensure_dir(guards_dir)

        imports = ['"""State machine transition guards."""\n']

        for entity in self.spec.domain.entities:
            if entity.state_machine:
                guard_content = self._generate_entity_guards(entity)
                guard_path = guards_dir / f"{self._snake_case(entity.name)}_transitions.py"
                self._write_file(guard_path, guard_content)
                result.add_file(guard_path)

                imports.append(
                    f"from .{self._snake_case(entity.name)}_transitions import {entity.name}TransitionGuard"
                )

        # Generate __init__.py
        init_content = "\n".join(imports) + "\n"
        init_path = guards_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result

    def _generate_entity_guards(self, entity: "EntitySpec") -> str:
        """Generate state machine guards for an entity."""
        name = entity.name
        snake = self._snake_case(name)
        sm = entity.state_machine

        if not sm:
            return ""

        # Find the status field
        status_field = sm.status_field
        status_enum = f"{name}{self._pascal_case(status_field)}"

        # Build valid transitions map
        transitions_code = "    VALID_TRANSITIONS = {\n"
        transitions_by_from: dict[str, list[str]] = {}
        for trans in sm.transitions:
            from_state = trans.from_state
            to_state = trans.to_state
            if from_state not in transitions_by_from:
                transitions_by_from[from_state] = []
            transitions_by_from[from_state].append(to_state)

        for from_state, to_states in transitions_by_from.items():
            if from_state == "*":
                continue  # Handle wildcard separately
            to_list = ", ".join(f"{status_enum}.{s.upper()}" for s in to_states)
            transitions_code += f"        {status_enum}.{from_state.upper()}: [{to_list}],\n"
        transitions_code += "    }"

        # Build guard checks
        guard_checks = []
        for trans in sm.transitions:
            for guard in trans.guards:
                if guard.requires_field:
                    check = f'''
        if from_status == {status_enum}.{trans.from_state.upper()} and to_status == {status_enum}.{trans.to_state.upper()}:
            if entity.{guard.requires_field} is None:
                return False, "{guard.requires_field} is required for this transition"'''
                    guard_checks.append(check)
                elif guard.requires_role:
                    check = f'''
        if from_status == {status_enum}.{trans.from_state.upper()} and to_status == {status_enum}.{trans.to_state.upper()}:
            if not context.has_role("{guard.requires_role}"):
                return False, "Only {guard.requires_role} can perform this transition"'''
                    guard_checks.append(check)

        guard_checks_code = "\n".join(guard_checks) if guard_checks else ""

        content = dedent(f'''
            """
            State machine guards for {name} entity.
            Generated from DSL - DO NOT EDIT.
            """
            from ..models.{snake} import {name}, {status_enum}
            from ..access.context import RequestContext


            class TransitionError(Exception):
                """Raised when a state transition is not allowed."""
                pass


            class {name}TransitionGuard:
                """Enforce valid state transitions for {name}."""

            {transitions_code}

                def can_transition(
                    self,
                    entity: {name},
                    to_status: {status_enum},
                    context: RequestContext,
                ) -> tuple[bool, str | None]:
                    """Check if transition is allowed. Returns (allowed, error_message)."""
                    from_status = entity.{status_field}

                    # Check if transition is valid
                    valid_targets = self.VALID_TRANSITIONS.get(from_status, [])
                    if to_status not in valid_targets:
                        return False, f"Cannot transition from {{from_status}} to {{to_status}}"

                    # Check guards{guard_checks_code}

                    return True, None

                def assert_transition(
                    self,
                    entity: {name},
                    to_status: {status_enum},
                    context: RequestContext,
                ) -> None:
                    """Raise exception if transition not allowed."""
                    allowed, error = self.can_transition(entity, to_status, context)
                    if not allowed:
                        raise TransitionError(error)
        ''')

        return content.strip()

    def generate_validators(self) -> GeneratorResult:
        """Generate invariant validators."""
        result = GeneratorResult()

        validators_dir = self.backend_dir / "validators"
        self._ensure_dir(validators_dir)

        imports = ['"""Invariant validators."""\n']

        for entity in self.spec.domain.entities:
            if entity.invariants:
                validator_content = self._generate_entity_validators(entity)
                validator_path = validators_dir / f"{self._snake_case(entity.name)}_invariants.py"
                self._write_file(validator_path, validator_content)
                result.add_file(validator_path)

                imports.append(
                    f"from .{self._snake_case(entity.name)}_invariants import {entity.name}InvariantValidator"
                )

        # Generate __init__.py
        init_content = "\n".join(imports) + "\n"
        init_path = validators_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result

    def _generate_entity_validators(self, entity: "EntitySpec") -> str:
        """Generate invariant validators for an entity."""
        name = entity.name
        snake = self._snake_case(name)

        # Generate validation methods for each invariant
        validation_methods = []
        validation_calls = []

        for i, inv in enumerate(entity.invariants):
            method_name = f"validate_invariant_{i}"
            message = inv.message or "Invariant violation"
            code = inv.code or f"{name.upper()}_INVARIANT_{i}"

            # Convert expression to Python (simplified)
            expr_str = self._invariant_to_python(inv, entity)

            method = f'''
    def {method_name}(self, entity: {name}) -> None:
        """Invariant: {expr_str}"""
        if not ({expr_str}):
            raise {name}InvariantError(
                message="{message}",
                code="{code}",
            )'''
            validation_methods.append(method)
            validation_calls.append(f"        self.{method_name}(entity)")

        methods_code = "\n".join(validation_methods)
        calls_code = "\n".join(validation_calls)

        content = dedent(f'''
            """
            Invariant validators for {name} entity.
            Generated from DSL - DO NOT EDIT.
            """
            from ..models.{snake} import {name}


            class {name}InvariantError(Exception):
                """Raised when a {name} invariant is violated."""

                def __init__(self, message: str, code: str):
                    super().__init__(message)
                    self.code = code


            class {name}InvariantValidator:
                """Validate {name} invariants."""

                def validate(self, entity: {name}) -> None:
                    """Validate all invariants. Raises {name}InvariantError on failure."""
            {calls_code}
            {methods_code}

                def is_valid(self, entity: {name}) -> tuple[bool, list[str]]:
                    """Check all invariants without raising. Returns (valid, errors)."""
                    errors = []
                    try:
                        self.validate(entity)
                    except {name}InvariantError as e:
                        errors.append(f"[{{e.code}}] {{e}}")
                    return len(errors) == 0, errors
        ''')

        return content.strip()

    def _invariant_to_python(self, inv: "InvariantSpec", entity: "EntitySpec") -> str:
        """Convert invariant expression to Python code."""
        # This is a simplified implementation
        # A full implementation would properly parse the invariant expression
        expr = inv.expression

        # For now, return a placeholder that shows the structure
        # In production, this would properly convert the IR expression to Python
        return f"True  # TODO: Implement invariant check"

    def generate_access(self) -> GeneratorResult:
        """Generate access control policies."""
        result = GeneratorResult()

        access_dir = self.backend_dir / "access"
        self._ensure_dir(access_dir)

        # Generate context module
        context_content = self._generate_request_context()
        context_path = access_dir / "context.py"
        self._write_file(context_path, context_content)
        result.add_file(context_path)

        # Generate policies for entities with access rules
        policies_parts = [
            '"""',
            "Access control policies.",
            "Generated from DSL - DO NOT EDIT.",
            '"""',
            "from sqlalchemy import or_",
            "from sqlalchemy.sql import Select",
            "",
            "from .context import RequestContext",
            "",
        ]

        for entity in self.spec.domain.entities:
            if entity.access:
                policy = self._generate_entity_access_policy(entity)
                policies_parts.append(policy)
                policies_parts.append("")

        policies_content = "\n".join(policies_parts)
        policies_path = access_dir / "policies.py"
        self._write_file(policies_path, policies_content)
        result.add_file(policies_path)

        # Generate __init__.py
        init_content = '"""Access control module."""\nfrom .context import RequestContext, get_request_context\nfrom .policies import *\n'
        init_path = access_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result

    def _generate_request_context(self) -> str:
        """Generate request context module."""
        return dedent('''
            """
            Request context for access control.
            Generated from DSL - DO NOT EDIT.
            """
            from dataclasses import dataclass, field
            from typing import Optional
            from uuid import UUID

            from fastapi import Request, Depends


            @dataclass
            class RequestContext:
                """Context for the current request."""

                user_id: Optional[UUID] = None
                roles: list[str] = field(default_factory=list)
                tenant_id: Optional[UUID] = None

                @property
                def is_authenticated(self) -> bool:
                    """Check if user is authenticated."""
                    return self.user_id is not None

                def has_role(self, role: str) -> bool:
                    """Check if user has a specific role."""
                    return role in self.roles

                def has_any_role(self, *roles: str) -> bool:
                    """Check if user has any of the specified roles."""
                    return any(r in self.roles for r in roles)


            async def get_request_context(request: Request) -> RequestContext:
                """
                Extract request context from FastAPI request.

                TODO: Implement actual authentication extraction.
                """
                # TODO: Extract user from JWT token or session
                return RequestContext()
        ''').strip()

    def _generate_entity_access_policy(self, entity: "EntitySpec") -> str:
        """Generate access policy for an entity."""
        name = entity.name
        snake = self._snake_case(name)

        # Generate read/write checks (simplified)
        read_check = "True  # TODO: Implement read access check"
        write_check = "True  # TODO: Implement write access check"

        if entity.access:
            # In production, we'd properly convert the access expressions
            pass

        return dedent(f'''
            class {name}AccessPolicy:
                """Row-level security for {name} entity."""

                def can_read(self, entity, context: RequestContext) -> bool:
                    """Check if current user can read this {snake}."""
                    return {read_check}

                def can_write(self, entity, context: RequestContext) -> bool:
                    """Check if current user can write this {snake}."""
                    return {write_check}

                def filter_readable(
                    self,
                    query: Select,
                    context: RequestContext,
                ) -> Select:
                    """Apply read filters to a SQLAlchemy query."""
                    # TODO: Implement query filtering based on access rules
                    return query
        ''').strip()

    def generate_app(self) -> GeneratorResult:
        """Generate main application entry point."""
        result = GeneratorResult()

        # Collect router imports
        router_imports = []
        router_includes = []
        for entity in self.spec.domain.entities:
            snake = self._snake_case(entity.name)
            router_imports.append(f"from .routers.{snake} import router as {snake}_router")
            router_includes.append(f'app.include_router({snake}_router, prefix="/api")')

        router_imports_str = "\n".join(router_imports)
        router_includes_str = "\n".join(router_includes)

        content = dedent(f'''
            """
            {self.spec.title or self.spec.name} FastAPI Application.
            Generated from DSL - DO NOT EDIT.
            """
            from contextlib import asynccontextmanager

            from fastapi import FastAPI
            from fastapi.middleware.cors import CORSMiddleware

            from .config import get_settings

            {router_imports_str}


            @asynccontextmanager
            async def lifespan(app: FastAPI):
                """Application lifespan handler."""
                # Startup
                yield
                # Shutdown


            def create_app() -> FastAPI:
                """Create and configure the FastAPI application."""
                settings = get_settings()

                app = FastAPI(
                    title="{self.spec.title or self.spec.name}",
                    version="{self.spec.version}",
                    lifespan=lifespan,
                )

                # CORS
                app.add_middleware(
                    CORSMiddleware,
                    allow_origins=settings.cors_origins,
                    allow_credentials=True,
                    allow_methods=["*"],
                    allow_headers=["*"],
                )

                # Include routers
                {router_includes_str}

                @app.get("/health")
                async def health():
                    """Health check endpoint."""
                    return {{"status": "healthy"}}

                return app


            app = create_app()
        ''')

        app_path = self.backend_dir / "app.py"
        self._write_file(app_path, content.strip())
        result.add_file(app_path)

        return result

    # Utility methods

    def _snake_case(self, name: str) -> str:
        """Convert PascalCase to snake_case."""
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        return "".join(result)

    def _pascal_case(self, name: str) -> str:
        """Convert snake_case to PascalCase."""
        return "".join(word.capitalize() for word in name.split("_"))


# Register adapter
AdapterRegistry.register_backend("fastapi", FastAPIAdapter)
