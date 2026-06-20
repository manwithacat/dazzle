"""End-to-end audit-history region renderer (#956 cycle 9).

The integration glue: combines cycle-7's `load_history` (RBAC +
fetch + decode + group) with an inline typed-HTML render of the
``HistoryChange`` list into a single async callable that detail-page
renderers (full surface-integration is a follow-up cycle) can invoke
directly.

Phase 4 (v0.67.58): switched from Jinja `workspace/regions/audit_history.html`
to a direct-emission renderer using `html.escape`. The template was a
single-consumer 60-line file; inlining keeps the audit-history surface
on the typed substrate without standing up a full `AuditHistory`
primitive + renderer registration.

Design notes
------------

* Returns a rendered HTML string, not a fragment-with-headers
  Response — so the caller can embed it inside a larger surface
  template, return it directly as an HTMX swap, or stash it in
  ``request.state`` for the workspace renderer to pick up.
* Returns the empty-state markup (rather than an empty string) when
  there's no audit_spec / no rows / RBAC denies — the empty branch
  already handles that and the consistent shape keeps callers simple.
* All cycle-6/7 best-effort guarantees flow through: a service
  exception lands as an empty list at the loader, which renders as
  the empty-state — no caller-visible failure mode.
"""

from __future__ import annotations

import html
import logging
from collections.abc import Iterable
from typing import Any

from dazzle.http.runtime.audit_visibility import find_audit_spec, load_history

logger = logging.getLogger(__name__)


_EMPTY_REGION = (
    '<section class="dz-region dz-audit-history" aria-label="Change history">'
    '<p class="dz-audit-history__empty">No history yet.</p>'
    "</section>"
)


def _render_field(change_op: str, f: Any) -> str:
    name = html.escape(str(getattr(f, "field_name", "") or ""), quote=False)
    before = getattr(f, "decoded_before", None)
    after = getattr(f, "decoded_after", None)
    before_html = (
        f'<span class="dz-audit-history__value dz-audit-history__value--before">'
        f"{html.escape(str(before), quote=False) if before is not None else ''}"
        f"</span>"
    )
    after_html = (
        f'<span class="dz-audit-history__value dz-audit-history__value--after">'
        f"{html.escape(str(after), quote=False) if after is not None else ''}"
        f"</span>"
    )
    if change_op == "create":
        value_html = after_html
    elif change_op == "delete":
        value_html = before_html
    else:
        value_html = (
            f"{before_html}"
            f'<span class="dz-audit-history__arrow" aria-hidden="true">→</span>'
            f"{after_html}"
        )
    return (
        f'<li class="dz-audit-history__field">'
        f'<span class="dz-audit-history__field-name">{name}</span>'
        f"{value_html}"
        f"</li>"
    )


def _render_change(change: Any) -> str:
    by_user_id = getattr(change, "by_user_id", None)
    if by_user_id:
        head_by = (
            f'<span class="dz-audit-history__by">{html.escape(str(by_user_id), quote=False)}</span>'
        )
    else:
        head_by = '<span class="dz-audit-history__by dz-audit-history__by--system">system</span>'

    op = str(getattr(change, "operation", "") or "")
    op_attr = html.escape(op, quote=True)
    op_text = html.escape(op, quote=False)
    head_op = f'<span class="dz-audit-history__op dz-audit-history__op--{op_attr}">{op_text}</span>'

    at = getattr(change, "at", None)
    if at:
        at_attr = html.escape(str(at), quote=True)
        at_text = html.escape(str(at), quote=False)
        head_at = f'<time class="dz-audit-history__at" datetime="{at_attr}">{at_text}</time>'
    else:
        head_at = ""

    fields_html = "".join(_render_field(op, f) for f in getattr(change, "fields", []) or [])

    return (
        f'<li class="dz-audit-history__change">'
        f'<header class="dz-audit-history__change-head">{head_by}{head_op}{head_at}</header>'
        f'<ul class="dz-audit-history__fields" role="list">{fields_html}</ul>'
        f"</li>"
    )


def _render_history_html(history: Iterable[Any]) -> str:
    """Inline-render the audit-history region to HTML (Phase 4, v0.67.58).

    Replaces the legacy `workspace/regions/audit_history.html` Jinja
    template. Each `HistoryChange` has `by_user_id`, `operation`, `at`,
    and `fields` (each with `field_name`, `decoded_before`,
    `decoded_after`); the renderer matches the legacy CSS class names
    (`dz-audit-history__*`) so existing stylesheets continue to apply
    without changes."""
    changes = list(history)
    if not changes:
        return _EMPTY_REGION
    items_html = "".join(_render_change(c) for c in changes)
    return (
        '<section class="dz-region dz-audit-history" aria-label="Change history">'
        f'<ol class="dz-audit-history__list" role="list">{items_html}</ol>'
        "</section>"
    )


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
    and the typed inline-HTML renderer (v0.67.58) into one call.

    Returns the rendered HTML string. Always returns valid HTML — when
    no audit_spec / RBAC denies / no rows, the empty-state branch fires
    (so callers don't need a separate "is there history?" check before
    deciding whether to render the section).
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
        return _render_history_html(history)
    except Exception:
        logger.warning(
            "Audit-history region render failed for %s/%s",
            entity_type,
            entity_id,
            exc_info=True,
        )
        return _EMPTY_REGION
