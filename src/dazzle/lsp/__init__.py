"""
DAZZLE Language Server Protocol implementation.

Provides IDE features for DAZZLE DSL:
- Go-to-definition
- Hover documentation
- Completion
- Document symbols
- Diagnostics
"""

from .server import start_server

__all__ = ["start_server"]
