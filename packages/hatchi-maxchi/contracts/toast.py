"""HYPERPART: toast — stack host + auto-dismiss notification unit.

Dual-lock unit is the toast root (``[data-dz-toast-level]`` on ``.dz-toast``)
plus the stack host (``#dz-toast.dz-toast-stack``). Level, auto-dismiss delay,
title, message, and optional action row are host-owned.

Page chrome (decision 0011 / stem ``page-chrome-toast``): viewport stack,
default TTL 8s (10s error), pause on hover/focus, leave before remove. TTL
progress bar is host-injected (not a contract-required node). Optional person
composition (``data-dz-toast-composition=person``) and sound attr are optional
slots (ssr-client-slot-parity); host swipe-dismiss is pure behaviour.

Server emit: ``dazzle.http.runtime.response_helpers.with_toast``.
Client emit: ``showToast`` / stack ``toast`` events (``controllers/dz-toast.js``).

Contract selectors use ``[data-dz-*]`` only — the kit has no CSS class engine.
"""

from __future__ import annotations

from contracts._kit import DomContract, Node, OneOf, Present

DOM_CONTRACT = DomContract(
    part="toast",
    root="[data-dz-toast-level]",
    nodes=(
        Node(
            "[data-dz-toast-level]",
            attrs={
                "data-dz-toast-level": OneOf("info", "success", "warning", "error"),
                "data-dz-remove-after": Present(),
            },
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
