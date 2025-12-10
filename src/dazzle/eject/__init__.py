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
    EjectionConfig,
    EjectionBackendConfig,
    EjectionFrontendConfig,
    EjectionTestingConfig,
    EjectionCIConfig,
    EjectionOutputConfig,
    load_ejection_config,
)
from .runner import EjectionRunner, EjectionResult, VerificationResult, EJECTION_VERSION
from .openapi import generate_openapi, openapi_to_json, openapi_to_yaml

__all__ = [
    "EjectionConfig",
    "EjectionBackendConfig",
    "EjectionFrontendConfig",
    "EjectionTestingConfig",
    "EjectionCIConfig",
    "EjectionOutputConfig",
    "load_ejection_config",
    "EjectionRunner",
    "EjectionResult",
    "VerificationResult",
    "EJECTION_VERSION",
    "generate_openapi",
    "openapi_to_json",
    "openapi_to_yaml",
]
