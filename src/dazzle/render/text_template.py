"""Render a parsed :class:`~dazzle.core.ir.TextTemplate` against a row (#1815, #1810, #1825).

Pure: no I/O. The row is the detail-page record as the detail fetch returns
it — FK relations auto-included as dicts, so a one-hop ``{school.name}``
reads ``row["school"]["name"]`` without another query; a two-hop
``{a.b.field}`` reads the second level the detail fetch loaded because the
surface's templates name it (:func:`record_template_includes`). The result is
plain text; the HTML emitters (heading, ``<title>``, breadcrumb) escape it.
A null (or an unresolvable hop) renders as empty.
"""

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from dazzle.core.ir.surfaces import SurfaceSpec
from dazzle.core.ir.text_template import TextTemplate
from dazzle.i18n.display_locale import get_display_locale
from dazzle.render.context import BreadcrumbCrumbContext
from dazzle.render.display_names import _resolve_display_name
from dazzle.render.filters import sentence_case_words


def _relation_name(field_name: str) -> str:
    """The key an auto-included FK relation loads under (``school_id`` → ``school``)."""
    return field_name.removesuffix("_id")


def _lookup(row: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    """Walk ``path`` through ``row``'s loaded relations; ``None`` when a hop is missing."""
    value: Any = row
    for i, name in enumerate(path):
        if not isinstance(value, Mapping):
            return None
        found = value.get(name)
        if i < len(path) - 1 and not isinstance(found, Mapping):
            # An FK column stored as ``<name>_id`` loads its relation as ``<name>``.
            found = value.get(_relation_name(name))
        value = found
    return value


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
    if name == "label":
        # The DSL declares no per-value enum labels, so an enum's label is its
        # humanised value (validate pins `|label` to enum fields).
        return sentence_case_words(text)
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
        raw = _lookup(data, placeholder.path)
        if raw is None:
            continue
        text = _resolve_display_name(raw)
        for name in placeholder.filters:
            text = _apply_filter(text, raw, name)
        out.append(text)
    return "".join(out).strip()


def record_template_includes(surface: SurfaceSpec | None) -> list[str]:
    """Second-level relations the surface's templates read (#1825).

    The detail fetch auto-includes every first-level FK relation; a two-hop
    placeholder ``{a.b.field}`` (title or crumb label) also needs ``a.b``
    loaded. Returned as dotted relation paths for the row loader, which
    batches each into one query on the detail path. A row-bound crumb link
    reads only an id, which the first level already carries.
    """
    if surface is None:
        return []
    templates: list[TextTemplate] = []
    if surface.title_template is not None:
        templates.append(surface.title_template)
    trail = surface.ux.breadcrumb if surface.ux is not None else None
    if trail is not None:
        templates.extend(c.label for c in trail.crumbs)
    paths = {
        f"{_relation_name(ph.path[0])}.{_relation_name(ph.path[1])}"
        for t in templates
        for ph in t.placeholders
        if len(ph.path) > 2
    }
    return sorted(paths)


def _row_link(crumb: BreadcrumbCrumbContext, record: Mapping[str, Any]) -> str | None:
    """A row-bound crumb's URL, or ``None`` when its ref is null (plain-text crumb)."""
    if crumb.row_url is None or crumb.row_path is None:
        return crumb.url
    value = _lookup(record, crumb.row_path)
    if isinstance(value, Mapping):
        value = value.get("id")
    if value is None or str(value).strip() == "":
        return None
    return crumb.row_url.replace("{id}", quote(str(value), safe=""))


def record_page_chrome(
    title_template: TextTemplate | None,
    trail: list[BreadcrumbCrumbContext] | None,
    record: Mapping[str, Any] | None,
) -> tuple[str, list[BreadcrumbCrumbContext] | None]:
    """Per-record page chrome for a view surface (#1815, #1810, #1825).

    Returns ``(heading, trail)``: ``heading`` is the ``title:`` template
    rendered against ``record`` ("" when there is no template or it renders
    empty — the static surface title stands); ``trail`` is the authored
    breadcrumb with interpolating labels rendered and row-bound links
    resolved against the record (a null ref leaves that crumb as plain
    text), or ``None`` when nothing in it depends on the record (the
    compiled trail stands). The heading also names the document ``<title>``
    and the URL trail's leaf.
    """
    data: Mapping[str, Any] = record or {}
    heading = render_text_template(title_template, data) if title_template else ""
    rendered: list[BreadcrumbCrumbContext] | None = None
    if trail and any(c.label_template is not None or c.row_path is not None for c in trail):
        rendered = [
            c.model_copy(
                update={
                    "label": render_text_template(c.label_template, data)
                    if c.label_template is not None
                    else c.label,
                    "url": _row_link(c, data),
                }
            )
            for c in trail
        ]
    return heading, rendered
