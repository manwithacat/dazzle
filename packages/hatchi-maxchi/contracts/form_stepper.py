"""HYPERPART: form-stepper — multi-step form progress list.

Dual-lock unit is the stepper root. Step labels, state attrs, and wizard
controller seams are host-owned. Class ``.dz-form-stepper`` is the stable
substrate root (``_emit_form_stepper``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="form-stepper",
    root=".dz-form-stepper",
    nodes=(Node(".dz-form-stepper", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
