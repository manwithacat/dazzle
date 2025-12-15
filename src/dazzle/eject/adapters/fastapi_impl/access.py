"""
FastAPI access control generation.

Generates access control policies and request context from entity specifications.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from dazzle.eject.generator import GeneratorResult

from .utils import snake_case

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec, EntitySpec


def generate_request_context() -> str:
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


def generate_entity_access_policy(entity: EntitySpec) -> str:
    """Generate access policy for an entity."""
    name = entity.name
    snake = snake_case(name)

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


class AccessGenerator:
    """Generates access control for FastAPI adapter."""

    def __init__(
        self,
        spec: AppSpec,
        output_dir: Path,
        write_file_fn: Callable[[Path, str], None],
        ensure_dir_fn: Callable[[Path], None],
    ) -> None:
        self.spec = spec
        self.output_dir = output_dir
        self.backend_dir = output_dir / "backend"
        self._write_file = write_file_fn
        self._ensure_dir = ensure_dir_fn

    def generate_access(self) -> GeneratorResult:
        """Generate access control policies."""
        result = GeneratorResult()

        access_dir = self.backend_dir / "access"
        self._ensure_dir(access_dir)

        # Generate context module
        context_content = generate_request_context()
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
                policy = generate_entity_access_policy(entity)
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
