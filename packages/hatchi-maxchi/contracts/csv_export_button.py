"""HYPERPART: csv-export-button — list-region CSV download control.

Dual-lock unit is the button root. Endpoint, filename, and download
helper attrs are host-owned. Class ``.dz-list-csv-button`` is the stable
substrate root (``_emit_csv_export_button``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="csv-export-button",
    root=".dz-list-csv-button",
    nodes=(Node(".dz-list-csv-button", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
