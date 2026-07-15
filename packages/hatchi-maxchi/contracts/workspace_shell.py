"""HYPERPART: workspace-shell — workspace content outer wrapper + heading.

Dual-lock unit is the workspace root. Title, primary/overflow actions, and
body slot are host-owned. Class ``.dz-workspace`` is the stable substrate
root (``_emit_workspace_shell``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="workspace-shell",
    root=".dz-workspace",
    nodes=(Node(".dz-workspace", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
