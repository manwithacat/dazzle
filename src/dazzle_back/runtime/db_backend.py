"""
Database backend compatibility — DEPRECATED.

This module previously provided DualBackendMixin for SQLite/PostgreSQL
dual support. All runtime modules now use PostgreSQL directly via psycopg.

The DualBackendMixin class is retained as a no-op for import compatibility
but raises RuntimeError if instantiated.
"""

from __future__ import annotations


class DualBackendMixin:
    """Deprecated — use psycopg directly."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

    def _init_backend(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError(
            "DualBackendMixin is deprecated. Use psycopg.connect(database_url) directly."
        )


class AsyncDualBackendMixin:
    """Deprecated — use psycopg async directly."""

    def _init_async_backend(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError(
            "AsyncDualBackendMixin is deprecated. Use psycopg.AsyncConnection directly."
        )
