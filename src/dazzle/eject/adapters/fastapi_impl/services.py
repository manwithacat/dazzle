"""
FastAPI service generation.

Generates business logic services from entity specifications.
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


def generate_entity_service(entity: EntitySpec) -> str:
    """Generate service class for an entity."""
    name = entity.name
    snake = snake_case(name)

    # Check for state machine and invariants
    has_state_machine = entity.state_machine is not None
    has_invariants = len(entity.invariants) > 0
    has_access = entity.access is not None

    guard_import = (
        f"\nfrom ..guards.{snake}_transitions import {name}TransitionGuard"
        if has_state_machine
        else ""
    )
    validator_import = (
        f"\nfrom ..validators.{snake}_invariants import {name}InvariantValidator"
        if has_invariants
        else ""
    )
    access_import = f"\nfrom ..access.policies import {name}AccessPolicy" if has_access else ""

    guard_init = f"\n        self.guard = {name}TransitionGuard()" if has_state_machine else ""
    validator_init = (
        f"\n        self.validator = {name}InvariantValidator()" if has_invariants else ""
    )
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


class ServiceGenerator:
    """Generates business logic services for FastAPI adapter."""

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

    def generate_services(self) -> GeneratorResult:
        """Generate business logic services."""
        result = GeneratorResult()

        services_dir = self.backend_dir / "services"
        self._ensure_dir(services_dir)

        imports = ['"""Business logic services."""\n']

        for entity in self.spec.domain.entities:
            service_content = generate_entity_service(entity)
            service_path = services_dir / f"{snake_case(entity.name)}.py"
            self._write_file(service_path, service_content)
            result.add_file(service_path)

            imports.append(f"from .{snake_case(entity.name)} import {entity.name}Service")

        # Generate __init__.py
        init_content = "\n".join(imports) + "\n"
        init_path = services_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result
