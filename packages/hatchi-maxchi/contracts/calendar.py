"""HYPERPART: calendar — simple event list keyed by view.

Dual-lock unit is the region root. Event rows are host-owned HTML
or built from the model list.
"""

from __future__ import annotations

import html
from typing import Literal

from pydantic import BaseModel, Field

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="calendar",
    root="[data-dz-calendar]",
    nodes=(
        Node(
            "[data-dz-calendar]",
            attrs={"data-dz-calendar": Present()},
        ),
    ),
)

CalendarView = Literal["day", "week", "month"]


class CalendarEvent(BaseModel):
    """One calendar event row."""

    label: str
    when: str = ""  # ISO date/datetime for <time datetime>


class Calendar(BaseModel):
    """Calendar event list shell.

    - ``view`` → day|week|month (modifier class)
    - ``events`` → ordered (label, when) rows
    - ``body_html`` → optional trusted override of the ``<ul>`` body
    """

    view: CalendarView = "month"
    events: list[CalendarEvent] = Field(default_factory=list)
    body_html: str = Field(
        default="",
        description="Trusted override for inner list markup.",
    )


EXEMPLARS: list[Calendar] = [
    Calendar(
        view="month",
        events=[
            CalendarEvent(label="Sprint review", when="2026-07-15"),
            CalendarEvent(label="Retro", when="2026-07-16"),
        ],
    ),
    Calendar(view="week", events=[]),
]


def render(c: Calendar) -> str:
    """Model → calendar region root."""
    view = c.view if c.view in ("day", "week", "month") else "month"
    view_esc = html.escape(view, quote=True)
    if c.body_html.strip():
        inner = c.body_html
    else:
        items = "".join(
            f'<li class="dz-calendar__event">'
            f'<time datetime="{html.escape(ev.when, quote=True)}">'
            f"{html.escape(ev.when)}</time> {html.escape(ev.label)}"
            f"</li>"
            for ev in c.events
        )
        inner = f"<ul>{items}</ul>"
    return f'<div class="dz-calendar dz-calendar--view-{view_esc}" data-dz-calendar>{inner}</div>'


__all__ = [
    "DOM_CONTRACT",
    "Calendar",
    "CalendarEvent",
    "CalendarView",
    "EXEMPLARS",
    "render",
]
