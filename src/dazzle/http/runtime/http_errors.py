"""Shared HTTP error helpers for generated + custom routes.

Leaf module — imports only ``fastapi.HTTPException`` so any route/handler module
can import it without forming a cycle.
"""

from typing import Any

from fastapi import HTTPException


def require_found[T](value: T | None, detail: Any = "Not found") -> T:
    """Return ``value``, or raise ``404`` when it is ``None`` — the fetch-or-404 guard.

    Replaces the copy-pasted ``if x is None: raise HTTPException(404, "Not found")``
    that every read/update/delete handler repeated, so the 404 contract (and any
    future tweak to its detail/shape) lives in exactly one place. Also narrows the
    type from ``T | None`` to ``T`` for the caller. ``detail`` is ``Any`` (FastAPI's
    own type) so structured/dict details are supported, not just strings.
    """
    if value is None:
        raise HTTPException(status_code=404, detail=detail)
    return value
