"""HYPERPART: file-upload — multipart file widget shell.

Dual-lock unit is the widget root. Label chrome, FK hidden input, and
upload controller attrs are host-owned. Selector
``[data-dz-widget="file-upload"]`` is the stable substrate root
(``_emit_file_upload``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="file-upload",
    root='[data-dz-widget="file-upload"]',
    nodes=(Node('[data-dz-widget="file-upload"]', attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
