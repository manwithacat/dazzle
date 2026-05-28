"""TenantResolutionMiddleware stub for #1289 slice 1.

Real implementation lands in slice 3. The stub raises NotImplementedError
at construction so any accidental mount surfaces immediately rather than
silently passing requests through.
"""

from __future__ import annotations

from typing import Any


class TenantResolutionMiddleware:  # pragma: no cover - stub
    def __init__(self, app: Any, **_kwargs: Any) -> None:
        raise NotImplementedError(
            "TenantResolutionMiddleware is not wired yet (lands in #1289 slice 3)."
        )
