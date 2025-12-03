"""
Stub Generation for DAZZLE Domain Services.

This module provides stub generation for domain service implementations.
Domain services are declared in DSL (contracts) and implemented in stubs (logic).

The stub layer is the ONLY place where Turing-complete logic may exist.
"""

from dazzle.stubs.generator import StubGenerator
from dazzle.stubs.models import (
    DomainServiceSpec,
    ServiceField,
    ServiceKind,
    StubLanguage,
)

__all__ = [
    "StubGenerator",
    "DomainServiceSpec",
    "ServiceField",
    "ServiceKind",
    "StubLanguage",
]
