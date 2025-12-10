"""
FastAPI application entry point generation.

Generates main application file and configuration from AppSpec.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from dazzle.eject.generator import GeneratorResult

from .utils import snake_case

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec


def generate_config_module(app_name: str) -> str:
    """Generate configuration module."""
    return (
        dedent('''
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
    ''')
        .format(app_name=app_name)
        .strip()
    )


def generate_app_module(spec: AppSpec) -> str:
    """Generate main application entry point."""
    # Collect router imports
    router_imports = []
    router_includes = []
    for entity in spec.domain.entities:
        snake = snake_case(entity.name)
        router_imports.append(f"from .routers.{snake} import router as {snake}_router")
        router_includes.append(f'app.include_router({snake}_router, prefix="/api")')

    router_imports_str = "\n".join(router_imports)
    router_includes_str = "\n".join(router_includes)

    return dedent(f'''
        """
        {spec.title or spec.name} FastAPI Application.
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
                title="{spec.title or spec.name}",
                version="{spec.version}",
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
    ''').strip()


class AppGenerator:
    """Generates application entry point for FastAPI adapter."""

    def __init__(self, spec, output_dir: Path, write_file_fn, ensure_dir_fn):
        self.spec = spec
        self.output_dir = output_dir
        self.backend_dir = output_dir / "backend"
        self._write_file = write_file_fn
        self._ensure_dir = ensure_dir_fn

    def generate_config(self) -> GeneratorResult:
        """Generate configuration module."""
        result = GeneratorResult()

        config_path = self.backend_dir / "config.py"
        content = generate_config_module(self.spec.name)

        self._write_file(config_path, content)
        result.add_file(config_path)

        # Also create __init__.py
        init_path = self.backend_dir / "__init__.py"
        self._write_file(init_path, '"""Generated FastAPI backend."""\n')
        result.add_file(init_path)

        return result

    def generate_app(self) -> GeneratorResult:
        """Generate main application entry point."""
        result = GeneratorResult()

        content = generate_app_module(self.spec)

        app_path = self.backend_dir / "app.py"
        self._write_file(app_path, content)
        result.add_file(app_path)

        return result
