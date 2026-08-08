"""HYPERPART: toggle_group — segmented control on native radios.

Dual-lock unit is the fieldset/radiogroup root. Segment labels and checked
state are host-owned. Class ``.dz-toggle-group`` is the stable substrate root.

Dazzle form path (2026-08-08): ``widget=toggle_group`` → ``ToggleGroupField`` →
``FragmentRenderer._emit_toggle_group_field``. Distinct from contracts/toggle.py.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="toggle_group",
    root=".dz-toggle-group",
    nodes=(Node(".dz-toggle-group", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
