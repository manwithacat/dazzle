"""HYPERPART: form-stack — htmx-driven form container.

Dual-lock unit is the form root. Fields, submit, method attrs, and peek
save-and-stay seams are host-owned. Class ``.dz-form-stack`` is the stable
substrate root (``_emit_form_stack``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="form-stack",
    root=".dz-form-stack",
    nodes=(Node(".dz-form-stack", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
