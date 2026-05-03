"""End-to-end audit-history region renderer (#956 cycle 9).

The integration glue: combines cycle-7's `load_history` (RBAC +
fetch + decode + group) with cycle-8's `audit_history.html` template
into a single async callable that detail-page renderers (full
surface-integration is a follow-up cycle) can invoke directly.

Design notes
------------

* Returns a rendered HTML string, not a fragment-with-headers
  Response — so the caller can embed it inside a larger surface
  template, return it directly as an HTMX swap, or stash it in
  ``request.state`` for the workspace renderer to pick up.
* Returns the empty-state markup (rather than an empty string) when
  there's no audit_spec / no rows / RBAC denies — the template's
  empty branch already handles that and the consistent shape keeps
  callers simple.
* All cycle-6/7 best-effort guarantees flow through: a service
  exception lands as an empty list at the loader, which renders as
  the empty-state — no caller-visible failure mode.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from dazzle_back.runtime.audit_visibility import find_audit_spec, load_history

logger = logging.getLogger(__name__)


async def render_audit_history_region(
    *,
    audit_service: Any,
    audits: Iterable[Any],
    entity_type: str,
    entity_id: str,
    viewer_personas: Iterable[str],
    limit: int = 200,
) -> str:
    """Render the audit-history region for one entity row.

    Combines ``find_audit_spec`` (cycle 7), ``load_history`` (cycle 7),
    and the cycle-8 ``audit_history.html`` template into one call.

    Returns the rendered HTML string. Always returns valid HTML — when
    no audit_spec / RBAC denies / no rows, the template's empty-state
    branch fires (so callers don't need a separate "is there
    history?" check before deciding whether to render the section).
    """
    audit_spec = find_audit_spec(audits, entity_type)
    history = await load_history(
        audit_service=audit_service,
        audit_spec=audit_spec,
        entity_type=entity_type,
        entity_id=entity_id,
        viewer_personas=viewer_personas,
        limit=limit,
    )

    try:
        from dazzle_ui.runtime.template_renderer import render_fragment

        return render_fragment("workspace/regions/audit_history.html", audit_history=history)
    except Exception:
        # Template rendering must never break the detail page.
        # Return the minimal empty markup so the surface still has
        # a valid region body even if the template path is broken.
        logger.warning(
            "Audit-history region render failed for %s/%s",
            entity_type,
            entity_id,
            exc_info=True,
        )
        return (
            '<section class="dz-region dz-audit-history" aria-label="Change history">'
            '<p class="dz-audit-history__empty">No history yet.</p>'
            "</section>"
        )
