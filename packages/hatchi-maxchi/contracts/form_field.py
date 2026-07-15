"""HYPERPART: form-field — plain form field wrapper.

Dual-lock unit is the field root. Label, input, help, and a11y attrs are
host-owned. Class ``.dz-form-field`` is the stable substrate root
(``_emit_field``). Distinct from specialized widgets (combobox/tags/…).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="form-field",
    root=".dz-form-field",
    nodes=(Node(".dz-form-field", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
