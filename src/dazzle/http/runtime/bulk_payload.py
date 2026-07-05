"""Grid-primitive bulk payload: parsing + all-matching resolution (convergence C0b).

The HM ``grid`` primitive posts bulk actions FORM-encoded (htmx-4 FormData →
URLSearchParams): ``action``, repeated ``selected_ids`` / ``excluded_ids``,
``all_matching_selected``, plus an echo of the query the rows came from
(``q``/``search``/``sort``/``dir``/``page``/``page_size`` + filter keys).
The legacy dzTable path posts JSON ``{action, ids}``. Both shapes normalise
into :class:`BulkSelection` here.

All-matching (§15 of the primitive spec): the server NEVER trusts client ids —
it re-runs the echoed query through the same scope-filtered list core the view
used (:func:`gated_list`), strips the windowing params (``page``/``page_size``
window the DISPLAY, not the matched set), subtracts the exclusions, and feeds
the resulting ids to the caller's per-record enforcement loop.

Fail-closed rules (the C0b contract):

- an echoed ``q``/``search`` on an entity with no ``search_fields`` is
  REJECTED — silently ignoring a narrowing param would apply the action to
  MORE rows than the user was viewing;
- an unconsumable bare echo key is REJECTED for the same reason (bracket
  ``filter[field]`` keys pass through exactly as the list route applies them —
  parity with what the view showed);
- a matched set larger than ``cap`` is REJECTED ("narrow the query") rather
  than silently truncated.
"""

from dataclasses import dataclass, field
from typing import Any

from dazzle.http.runtime.access.gated import gated_list

# The four bulk-payload keys (never part of the query echo).
PAYLOAD_KEYS = frozenset({"action", "selected_ids", "all_matching_selected", "excluded_ids"})

# Echo keys that window/order the SAME matched set — ignorable for matching.
_WINDOW_KEYS = frozenset({"sort", "dir", "page", "page_size", "format"})

# Echo keys carrying the free-text search (q is the spec alias, #596).
_SEARCH_KEYS = frozenset({"q", "search"})


class BulkQueryError(ValueError):
    """A bulk query echo can't be honoured faithfully — fail closed (422)."""


@dataclass
class BulkSelection:
    """A normalised bulk request: who the action applies to."""

    action: str
    selected_ids: list[str]
    all_matching: bool
    excluded_ids: list[str]
    # The raw non-payload params — the query the rows came from.
    echo: dict[str, str] = field(default_factory=dict)


async def parse_bulk_selection(request: Any) -> BulkSelection:
    """Normalise a bulk POST body — JSON (legacy dzTable) or form (grid).

    Raises ``ValueError`` on an unparseable body; the route maps it to 400.
    """
    ctype = str(request.headers.get("content-type", ""))
    if "json" in ctype:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("JSON body must be an object")
        ids = body.get("ids")
        return BulkSelection(
            action=str(body.get("action", "") or ""),
            selected_ids=[str(i) for i in ids] if isinstance(ids, list) else [],
            all_matching=False,
            excluded_ids=[],
        )
    form = await request.form()
    echo: dict[str, str] = {}
    for key in form.keys():
        if key in PAYLOAD_KEYS:
            continue
        value = form.get(key)
        echo[key] = str(value) if value is not None else ""
    return BulkSelection(
        action=str(form.get("action") or ""),
        selected_ids=[str(v) for v in form.getlist("selected_ids")],
        all_matching=str(form.get("all_matching_selected") or "").lower() == "true",
        excluded_ids=[str(v) for v in form.getlist("excluded_ids")],
        echo=echo,
    )


def _echo_to_query(
    echo: dict[str, str],
    *,
    search_fields: list[str] | None,
    filter_fields: list[str] | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Translate the query echo into (search, user_filters) — or refuse.

    Mirrors the list route's parsing (#596: ``q`` aliases ``search``;
    ``filter[field]`` always applies; bare keys only when DSL-declared) so the
    matched set is EXACTLY what the list view showed. Anything narrowing we
    can't reproduce → :class:`BulkQueryError` (fail closed, never wider).
    """
    # Same precedence as the list route (#596: `effective_search = search or
    # q`) — the matched set must be exactly what the view showed, even for a
    # crafted POST carrying both params.
    search = (echo.get("search") or echo.get("q") or "").strip() or None
    if search and not search_fields:
        raise BulkQueryError(
            "the bulk query echoes a search but this entity has no search_fields — "
            "refusing to apply the action wider than the view"
        )
    allowed_bare = set(filter_fields or [])
    user_filters: dict[str, Any] = {}
    for key, value in echo.items():
        if key in _WINDOW_KEYS or key in _SEARCH_KEYS or not value:
            continue
        if key.startswith("filter[") and key.endswith("]"):
            user_filters[key[7:-1]] = value
        elif key in allowed_bare:
            user_filters[key] = value
        else:
            raise BulkQueryError(
                f"the bulk query echoes {key!r}, which this entity's list cannot "
                "consume — refusing to apply the action wider than the view"
            )
    return search, (user_filters or None)


async def resolve_all_matching_ids(
    *,
    service: Any,
    access: Any,
    echo: dict[str, str],
    search_fields: list[str] | None,
    filter_fields: list[str] | None,
    access_spec: dict[str, Any] | None = None,
    ref_targets: dict[str, str] | None = None,
    cap: int = 10_000,
    page_size: int = 500,
) -> list[str]:
    """Resolve the ids an all-matching bulk action applies to (pre-exclusions).

    Re-runs the echoed query through :func:`gated_list` — the SAME permit +
    scope + visibility pipeline the list view used — page by page. ``page`` /
    ``page_size`` from the echo are deliberately absent here: they window the
    display, not the matched set.

    Raises :class:`BulkQueryError` on an unconsumable echo or a matched set
    above ``cap``.
    """
    search, user_filters = _echo_to_query(
        echo, search_fields=search_fields, filter_fields=filter_fields
    )
    ids: list[str] = []
    page = 1
    while True:
        result = await gated_list(
            service,
            access,
            page=page,
            page_size=page_size,
            search=search,
            user_filters=user_filters,
            search_fields=search_fields,
            access_spec=access_spec,
            ref_targets=ref_targets,
        )
        items = result.get("items") or []
        total = int(result.get("total") or 0)
        if total > cap:
            raise BulkQueryError(
                f"the bulk query matches {total} rows — above the {cap}-row cap; narrow the query"
            )
        for item in items:
            rid = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
            if rid is not None:
                ids.append(str(rid))
        if len(items) < page_size or len(ids) >= total:
            return ids
        page += 1
