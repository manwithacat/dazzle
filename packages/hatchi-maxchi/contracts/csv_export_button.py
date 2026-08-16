"""HYPERPART: csv-export-button — list-region CSV download control.

Dual-lock unit is the button root. Endpoint, filename, and download
helper attrs are host-owned. Class ``.dz-list-csv-button`` is the stable
substrate root (``_emit_csv_export_button``).

Leftover honesty (cycle 2174): ``data-dz-csv-endpoint`` must echo
leftover-honest ``include_closed`` / ``as_of``. The bare path dropped
them and invented open-only / current CSV. Leftover junk (``zzz``,
``2abc``, ``maybe``, ``not-a-date``) must not invent. Valid ``true`` /
YYYY-MM-DD still ride the download. Rest-state gallery is unchanged
(oral #33). Not leftover sort-header echo. Not leftover list
include_closed / related-tab as_of / DETAIL as_of onto the edit form.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="csv-export-button",
    root=".dz-list-csv-button",
    nodes=(Node(".dz-list-csv-button", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
