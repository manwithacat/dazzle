"""
DAZZLE Ejection Toolchain v0.7.2.

Provides a path from DNR runtime to standalone generated code
when projects outgrow the native runtime or have deployment
constraints requiring traditional application structure.

Usage:
    dazzle eject              # Generate standalone code
    dazzle eject --backend    # Backend only
    dazzle eject --frontend   # Frontend only
    dazzle eject --dry-run    # Preview without writing
"""

from .config import (
    EjectionBackendConfig,
    EjectionCIConfig,
    EjectionConfig,
    EjectionFrontendConfig,
    EjectionOutputConfig,
    EjectionTestingConfig,
    load_ejection_config,
)
from .generator import CompositeGenerator, Generator, GeneratorResult
from .openapi import generate_openapi, openapi_to_json, openapi_to_yaml
from .runner import EJECTION_VERSION, EjectionResult, EjectionRunner, VerificationResult

__all__ = [
    # Config
    "EjectionConfig",
    "EjectionBackendConfig",
    "EjectionFrontendConfig",
    "EjectionTestingConfig",
    "EjectionCIConfig",
    "EjectionOutputConfig",
    "load_ejection_config",
    # Generator
    "Generator",
    "GeneratorResult",
    "CompositeGenerator",
    # Runner
    "EjectionRunner",
    "EjectionResult",
    "VerificationResult",
    "EJECTION_VERSION",
    # OpenAPI
    "generate_openapi",
    "openapi_to_json",
    "openapi_to_yaml",
]
