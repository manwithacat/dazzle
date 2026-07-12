"""HYPERPART: date-range — paired From/To native date inputs + htmx.

Dual-lock unit is the region root. HTMX endpoint and region target are
host-owned; both inputs share ``hx-include="closest .date-range-bar"``.
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
    ),
)


class DateRange(BaseModel):
    """From/To date filter bar.

    - ``region_name`` → id namespace for inputs + default hx-target
    - ``endpoint`` → hx-get URL
    - ``date_from`` / ``date_to`` → ISO date values (empty = unset)
    - ``target`` → optional hx-target override (default ``#region-{region_name}``)
    """

    region_name: str = "region"
    endpoint: str = ""
    date_from: str = ""
    date_to: str = ""
    target: str = ""


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


def render(d: DateRange) -> str:
    """Model → date-range picker bar."""
    rname = html.escape(d.region_name, quote=True)
    endpoint = html.escape(d.endpoint, quote=True)
    target = html.escape(d.target or f"#region-{d.region_name}", quote=True)
    date_from = html.escape(d.date_from, quote=True)
    date_to = html.escape(d.date_to, quote=True)
    return (
        f'<div class="dz-date-range-picker date-range-bar" data-dz-date-range>'
        f'<label class="dz-date-range-label" for="date-from-{rname}">From</label>'
        f'<input type="date" id="date-from-{rname}" name="date_from" '
        f'value="{date_from}" class="dz-date-range-input" '
        f'hx-get="{endpoint}" hx-target="{target}" hx-swap="innerHTML" '
        f'hx-include="closest .date-range-bar">'
        f'<label class="dz-date-range-label" for="date-to-{rname}">To</label>'
        f'<input type="date" id="date-to-{rname}" name="date_to" '
        f'value="{date_to}" class="dz-date-range-input" '
        f'hx-get="{endpoint}" hx-target="{target}" hx-swap="innerHTML" '
        f'hx-include="closest .date-range-bar">'
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "DateRange",
    "EXEMPLARS",
    "render",
]
