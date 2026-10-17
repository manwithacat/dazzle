"""Render a parsed :class:`~dazzle.core.ir.TextTemplate` against a row (#1815, #1810).

Pure: no I/O. The row is the detail-page record as the detail fetch returns
it — FK relations auto-included as dicts, so a one-hop ``{school.name}``
reads ``row["school"]["name"]`` without another query. The result is plain
text; the HTML emitters (heading, ``<title>``, breadcrumb) escape it.
A null (or an unresolvable hop) renders as empty.
"""

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from dazzle.core.ir.text_template import TemplatePlaceholder, TextTemplate
from dazzle.i18n.display_locale import get_display_locale
from dazzle.render.context import BreadcrumbCrumbContext
from dazzle.render.display_names import _resolve_display_name


def _lookup(row: Mapping[str, Any], placeholder: TemplatePlaceholder) -> Any:
    head = placeholder.path[0]
    value = row.get(head)
    if len(placeholder.path) == 1:
        return value
    if not isinstance(value, Mapping):
        # An FK column stored as ``<name>_id`` loads its relation as ``<name>``.
        value = row.get(head.removesuffix("_id"))
    if not isinstance(value, Mapping):
        return None
    return value.get(placeholder.path[1])


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _apply_filter(text: str, raw: Any, name: str) -> str:
    if name == "upper":
        return text.upper()
    if name == "lower":
        return text.lower()
    if name == "title":
        return text.replace("_", " ").title()
    # "date" — the only other filter the parser admits.
    parsed = _as_date(raw)
    return get_display_locale().format_date_value(parsed) if parsed else text


def render_text_template(template: TextTemplate, row: Mapping[str, Any] | None) -> str:
    """Interpolate ``row`` into ``template``; whitespace-trimmed plain text."""
    data: Mapping[str, Any] = row or {}
    out: list[str] = []
    for segment in template.segments:
        placeholder = segment.placeholder
        if placeholder is None:
            out.append(segment.text)
            continue
        raw = _lookup(data, placeholder)
        if raw is None:
            continue
        text = _resolve_display_name(raw)
        for name in placeholder.filters:
            text = _apply_filter(text, raw, name)
        out.append(text)
    return "".join(out).strip()


def record_page_chrome(
    title_template: TextTemplate | None,
    trail: list[BreadcrumbCrumbContext] | None,
    record: Mapping[str, Any] | None,
) -> tuple[str, list[BreadcrumbCrumbContext] | None]:
    """Per-record page chrome for a view surface (#1815, #1810).

    Returns ``(heading, trail)``: ``heading`` is the ``title:`` template
    rendered against ``record`` ("" when there is no template or it renders
    empty — the static surface title stands); ``trail`` is
    the authored breadcrumb with interpolating labels rendered, or ``None``
    when nothing in it interpolates (the compiled trail stands). The heading
    also names the document ``<title>`` and the URL trail's leaf.
    """
    heading = render_text_template(title_template, record) if title_template else ""
    rendered: list[BreadcrumbCrumbContext] | None = None
    if trail and any(c.label_template is not None for c in trail):
        rendered = [
            c.model_copy(update={"label": render_text_template(c.label_template, record)})
            if c.label_template is not None
            else c
            for c in trail
        ]
    return heading, rendered
