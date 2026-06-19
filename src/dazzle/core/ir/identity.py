"""Shared identity-display helper for specs / graph nodes.

Centralizes the ``getattr(x, "name", None) or getattr(x, "id", ...)`` fallback
that call sites re-derived because ``PersonaSpec`` identity is ``.id`` not ``.name``
(a known footgun) while most other specs/nodes carry ``.name``. One accessor means
the footgun lives in one place instead of being copy-pasted defensively.
"""


def spec_display_id(spec: object, default: str | None = "unknown") -> str | None:
    """Best display id for a spec/node: prefer ``.name``, then ``.id``, then ``default``.

    Pass ``default=None`` to preserve the "None when both absent" behaviour some
    callers rely on; the str default ("unknown") suits human-facing labels.
    """
    return getattr(spec, "name", None) or getattr(spec, "id", None) or default
