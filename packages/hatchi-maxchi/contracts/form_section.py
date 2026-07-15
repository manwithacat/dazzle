"""HYPERPART: form-section — labelled field group inside a form stack.

Dual-lock unit is the section root. Title, note, and nested fields are
host-owned. Class ``.dz-form-section`` is the stable substrate root
(``_emit_form_section``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="form-section",
    root=".dz-form-section",
    nodes=(Node(".dz-form-section", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
