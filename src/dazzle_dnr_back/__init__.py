"""
Dazzle Native Runtime - Backend (DNR-Back)

Framework-agnostic backend specification and runtime for Dazzle applications.

This package provides:
- BackendSpec: Complete backend specification types (entities, services, endpoints)
- Runtime: Native backend runtime (Pydantic models + FastAPI services)
- Converters: Transform Dazzle AppSpec to BackendSpec
"""

__version__ = "0.9.4"

from dazzle_dnr_back.specs.backend_spec import BackendSpec

__all__ = ["BackendSpec"]
