"""HYPERPART: date-range — paired From/To native date inputs + htmx.

Dual-lock unit is the region root. HTMX endpoint and region target are
host-owned; both inputs share ``hx-include="closest .date-range-bar"``.
``dz-date-range.js`` blocks inverted From>To before the exchange (cycle 2122).

Leftover honesty (cycle 2139): each bound has an ISO companion
(``data-dz-date-iso``, no ``name`` — the native ``type=date`` is the
submitted / hx-include value). Typed leftover junk (``2026-06-01zzz``,
``zzz``, ``June 1``) must not invent a bound — the date stays put and
both controls fail custom validity so submit / hx-get cannot post the
previous date as if the leftover were accepted. Empty ISO on blur
restores from the native date.

Leftover honesty (cycle 2180): each bound ``hx-get`` must echo
leftover-honest ``include_closed`` / ``as_of``. Bare
``hx-get="{endpoint}"`` + ``hx-include="closest .date-range-bar"``
dropped them and invented open-only / current after a bound
change. Leftover junk (``zzz``, ``2abc``, ``maybe``,
``not-a-date``) must not invent. Valid ``true`` / YYYY-MM-DD
still ride hx-get. Rest-state gallery is unchanged (oral #33).
Not leftover list include_closed / related-tab as_of / DETAIL
as_of onto the edit form.
"""

from __future__ import annotations

import html

from pydantic import BaseModel

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="date-range",
    root="[data-dz-date-range]",
    nodes=(
        Node(
            "[data-dz-date-range]",
            attrs={"data-dz-date-range": Present()},
        ),
        Node("[data-dz-date-iso]", attrs={"data-dz-date-iso": Present()}),
    ),
)


class DateRange(BaseModel):
    """From/To date filter bar.

    - ``region_name`` → id namespace for inputs + default hx-target
    - ``endpoint`` → hx-get URL
    - ``date_from`` / ``date_to`` → ISO date values (empty = unset)
    - ``target`` → optional hx-target override (default ``#region-{region_name}``)
    - ``include_closed`` / ``as_of`` → leftover-honest temporal (cycle 2180)
    """

    region_name: str = "region"
    endpoint: str = ""
    date_from: str = ""
    date_to: str = ""
    target: str = ""
    include_closed: str = ""
    as_of: str = ""


EXEMPLARS: list[DateRange] = [
    DateRange(
        region_name="invoices",
        endpoint="/mock/search",
        date_from="2026-06-01",
        date_to="2026-06-30",
        target="#hm-dr-out",
    ),
    DateRange(region_name="empty", endpoint="/app/region"),
]


def _leftover_honest_temporal(include_closed: str, as_of: str) -> str:
    """Valid ``true`` / YYYY-MM-DD ride; leftover junk omits (cycle 2180)."""
    parts: list[str] = []
    ic = str(include_closed or "").strip().lower()
    if ic in ("true", "1", "yes"):
        parts.append("include_closed=true")
    ao = str(as_of or "").strip()
    if ao:
        from datetime import date as _date

        try:
            _date.fromisoformat(ao)
        except (ValueError, TypeError):
            ao = ""
        else:
            parts.append(f"as_of={html.escape(ao, quote=True)}")
    return "&amp;".join(parts)


def _bound(
    rname: str,
    bound: str,
    name: str,
    value: str,
    endpoint: str,
    target: str,
    label: str,
) -> str:
    iso_label = html.escape(f"{label} ISO date", quote=True)
    return (
        f'<label class="dz-date-range-label" for="date-{bound}-{rname}">{label}</label>'
        f'<span class="dz-date-range-group">'
        f'<input type="date" id="date-{bound}-{rname}" name="{name}" '
        f'value="{value}" class="dz-date-range-input" '
        f'hx-get="{endpoint}" hx-target="{target}" hx-swap="innerHTML" '
        f'hx-include="closest .date-range-bar">'
        f'<input data-dz-date-iso class="dz-date-range-iso" type="text" '
        f'spellcheck="false" autocomplete="off" '
        f'aria-label="{iso_label}" value="{value}">'
        f"</span>"
    )


def render(d: DateRange) -> str:
    """Model → date-range picker bar."""
    rname = html.escape(d.region_name, quote=True)
    endpoint = html.escape(d.endpoint, quote=True)
    qs = _leftover_honest_temporal(
        getattr(d, "include_closed", ""),
        getattr(d, "as_of", ""),
    )
    if qs:
        endpoint = f"{endpoint}&amp;{qs}" if "?" in endpoint else f"{endpoint}?{qs}"
    target = html.escape(d.target or f"#region-{d.region_name}", quote=True)
    date_from = html.escape(d.date_from, quote=True)
    date_to = html.escape(d.date_to, quote=True)
    return (
        f'<div class="dz-date-range-picker date-range-bar" data-dz-date-range>'
        f"{_bound(rname, 'from', 'date_from', date_from, endpoint, target, 'From')}"
        f"{_bound(rname, 'to', 'date_to', date_to, endpoint, target, 'To')}"
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "DateRange",
    "EXEMPLARS",
    "render",
]
