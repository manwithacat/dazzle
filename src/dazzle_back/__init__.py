"""
Dazzle Runtime - Backend (Dazzle Backend)

Framework-agnostic backend specification and runtime for Dazzle applications.

This package provides:
- Specs: Backend specification types (entities, services, endpoints)
- Runtime: Native backend runtime (Pydantic models + FastAPI services)
- Converters: Transform Dazzle AppSpec IR to backend specs

Public API
----------
CLI and MCP layers import from ``dazzle_back`` directly.  The symbols below
are lazily resolved so that the heavy runtime stack is not loaded at CLI
startup time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dazzle._version import get_version as _get_version

__version__ = _get_version()

if TYPE_CHECKING:
    from dazzle_back.converters import convert_appspec_to_backend as convert_appspec_to_backend
    from dazzle_back.converters.entity_converter import convert_entities as convert_entities
    from dazzle_back.events.tier import create_bus as create_bus
    from dazzle_back.graphql.integration import inspect_schema as inspect_schema
    from dazzle_back.graphql.integration import print_schema as print_schema
    from dazzle_back.runtime.auth import AuthStore as AuthStore
    from dazzle_back.runtime.migrations import MigrationAction as MigrationAction
    from dazzle_back.runtime.pg_backend import PostgresBackend as PostgresBackend
    from dazzle_back.runtime.sa_schema import build_metadata as build_metadata


def _get_AuthStore() -> object:  # noqa: N802
    from dazzle_back.runtime.auth import AuthStore

    return AuthStore


def _get_create_bus() -> object:
    from dazzle_back.events.tier import create_bus

    return create_bus


def _get_MigrationAction() -> object:  # noqa: N802
    from dazzle_back.runtime.migrations import MigrationAction

    return MigrationAction


def _get_PostgresBackend() -> object:  # noqa: N802
    from dazzle_back.runtime.pg_backend import PostgresBackend

    return PostgresBackend


def _get_build_metadata() -> object:
    from dazzle_back.runtime.sa_schema import build_metadata

    return build_metadata


def _get_convert_appspec_to_backend() -> object:
    from dazzle_back.converters import convert_appspec_to_backend

    return convert_appspec_to_backend


def _get_convert_entities() -> object:
    from dazzle_back.converters.entity_converter import convert_entities

    return convert_entities


def _get_inspect_schema() -> object:
    from dazzle_back.graphql.integration import inspect_schema

    return inspect_schema


def _get_print_schema() -> object:
    from dazzle_back.graphql.integration import print_schema

    return print_schema


_LOADERS: dict[str, object] = {
    "AuthStore": _get_AuthStore,
    "create_bus": _get_create_bus,
    "MigrationAction": _get_MigrationAction,
    "PostgresBackend": _get_PostgresBackend,
    "build_metadata": _get_build_metadata,
    "convert_appspec_to_backend": _get_convert_appspec_to_backend,
    "convert_entities": _get_convert_entities,
    "inspect_schema": _get_inspect_schema,
    "print_schema": _get_print_schema,
}


def __getattr__(name: str) -> object:
    """Lazy re-exports for public API surface."""
    loader = _LOADERS.get(name)
    if loader is not None:
        val = loader()  # type: ignore[operator]
        globals()[name] = val  # cache for next access
        return val
    raise AttributeError(f"module 'dazzle_back' has no attribute {name!r}")
