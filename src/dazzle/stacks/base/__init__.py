"""
Base infrastructure for modular backends.

Provides:
- Hook system for pre/post-build extensibility
- Base generator classes
- Common utilities
"""

from .hooks import Hook, HookContext, HookResult, HookPhase
from .generator import Generator, GeneratorResult
from .backend import ModularBackend

__all__ = [
    "Hook",
    "HookContext",
    "HookResult",
    "HookPhase",
    "Generator",
    "GeneratorResult",
    "ModularBackend",
]
