"""
Dazzle Runtime - Backend (Dazzle Backend)

Framework-agnostic backend specification and runtime for Dazzle applications.

This package provides:
- BackendSpec: Complete backend specification types (entities, services, endpoints)
- Runtime: Native backend runtime (Pydantic models + FastAPI services)
- Converters: Transform Dazzle AppSpec to BackendSpec
"""

from dazzle._version import get_version as _get_version

__version__ = _get_version()

from dazzle_back.specs.backend_spec import BackendSpec

__all__ = ["BackendSpec"]
