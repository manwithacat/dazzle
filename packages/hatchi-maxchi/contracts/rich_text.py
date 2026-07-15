"""HYPERPART: rich-text — progressive-enhancement editor shell.

Dual-lock unit is the widget root. Label chrome, hidden value input, and
toolbar/options attrs are host-owned. Selector
``[data-dz-widget="richtext"]`` is the stable substrate root
(``_emit_rich_text``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="rich-text",
    root='[data-dz-widget="richtext"]',
    nodes=(Node('[data-dz-widget="richtext"]', attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
