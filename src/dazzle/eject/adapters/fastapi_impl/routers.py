"""
FastAPI router generation.

Generates API routers from entity specifications.
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
    from dazzle.eject.config import EjectionBackendConfig


def generate_entity_router(entity: EntitySpec, config: EjectionBackendConfig) -> str:
    """Generate FastAPI router for an entity."""
    name = entity.name
    snake = snake_case(name)
    async_prefix = "async " if config.async_handlers else ""
    await_prefix = "await " if config.async_handlers else ""

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


class RouterGenerator:
    """Generates API routers for FastAPI adapter."""

    def __init__(
        self,
        spec: AppSpec,
        output_dir: Path,
        config: EjectionBackendConfig,
        write_file_fn: Callable[[Path, str], None],
        ensure_dir_fn: Callable[[Path], None],
    ) -> None:
        self.spec = spec
        self.output_dir = output_dir
        self.backend_dir = output_dir / "backend"
        self.config = config
        self._write_file = write_file_fn
        self._ensure_dir = ensure_dir_fn

    def generate_routers(self) -> GeneratorResult:
        """Generate API routers."""
        result = GeneratorResult()

        routers_dir = self.backend_dir / "routers"
        self._ensure_dir(routers_dir)

        imports = ['"""API routers."""\n']

        for entity in self.spec.domain.entities:
            router_content = generate_entity_router(entity, self.config)
            router_path = routers_dir / f"{snake_case(entity.name)}.py"
            self._write_file(router_path, router_content)
            result.add_file(router_path)

            imports.append(
                f"from .{snake_case(entity.name)} import router as {snake_case(entity.name)}_router"
            )

        # Generate __init__.py
        init_content = "\n".join(imports) + "\n"
        init_path = routers_dir / "__init__.py"
        self._write_file(init_path, init_content)
        result.add_file(init_path)

        return result
