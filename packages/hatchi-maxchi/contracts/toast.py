"""HYPERPART: toast — stack host + auto-dismiss notification unit.

Dual-lock unit is the toast root (``.dz-toast``) plus the stack host
(``#dz-toast.dz-toast-stack``). Level, auto-dismiss delay, title, message,
and optional action row are host-owned.

Server emit: ``dazzle.http.runtime.response_helpers.with_toast``.
Client emit: ``showToast`` / stack ``toast`` events (``controllers/dz-toast.js``).
"""

from __future__ import annotations

from contracts._kit import DomContract, Node, OneOf, Present

DOM_CONTRACT = DomContract(
    part="toast",
    root=".dz-toast",
    nodes=(
        Node(
            ".dz-toast",
            attrs={
                "data-dz-toast-level": OneOf("info", "success", "warning", "error"),
                "data-dz-remove-after": Present(),
            },
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
