"""Agent closed-loop control plane (#1605) — **no MCP dependency**.

Pure JSON builders for dual-lock pilots that install ``dazzle-dsl[signing]``
without the ``mcp`` extra. MCP handlers and CLI both call this package.
"""

from __future__ import annotations

from dazzle.agent_loop.core import (
    PLAYBOOK_DOMAIN_LOGIC,
    binding_wall,
    build_context,
    build_playbook,
    prove_stories,
)

__all__ = [
    "PLAYBOOK_DOMAIN_LOGIC",
    "binding_wall",
    "build_context",
    "build_playbook",
    "prove_stories",
]
