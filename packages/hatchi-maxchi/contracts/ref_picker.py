"""HYPERPART: ref-picker — related-entity select shell.

Dual-lock unit is the picker root. Label, options, and ``data-ref-api``
population are host-owned. Class ``.dz-ref-picker`` is the stable
substrate root (``_emit_ref_picker``). Distinct from combobox (static
options) and search-select (remote typeahead).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="ref-picker",
    root=".dz-ref-picker",
    nodes=(Node(".dz-ref-picker", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
