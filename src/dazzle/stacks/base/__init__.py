"""
Base infrastructure for modular backends.

Provides:
- Hook system for pre/post-build extensibility
- Base generator classes
- Common utilities
"""

from .backend import ModularBackend
from .generator import Generator, GeneratorResult
from .hooks import Hook, HookContext, HookPhase, HookResult

__all__ = [
    "Hook",
    "HookContext",
    "HookResult",
    "HookPhase",
    "Generator",
    "GeneratorResult",
    "ModularBackend",
]
