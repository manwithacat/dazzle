"""HYPERPART: workspace-context — tenant/context filter select shell.

Dual-lock unit is the context root. Label text, options URL, and preference
persistence script are host-owned. Class ``.dz-workspace-context`` is the
stable substrate root (``_emit_workspace_context_selector``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="workspace-context",
    root=".dz-workspace-context",
    nodes=(Node(".dz-workspace-context", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
