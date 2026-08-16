"""HYPERPART: activity-feed — who-did-what row unit.

One row is the dual-lock unit. The feed list is layout furniture; validate
rows with ``require_root`` on the row root.

``description`` is plain text (escaped). Optional ``actor`` renders a leading
span inside the bubble. Optional ``actor_html`` is trusted ``present()``
markup (person × timeline_meta Avatar) and replaces the escaped span when
set. Optional ``drill_url`` wraps description in a hub link (same #1303
class as timeline title / list row). Gallery exemplars stay plain ``actor``
(rest-state unchanged).
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field, field_validator

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="activity-feed",
    root="[data-dz-activity-row]",
    nodes=(
        Node(
            "[data-dz-activity-row]",
            attrs={"data-dz-activity-row": Present()},
        ),
    ),
)

_DOT_SVG = (
    '<svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">'
    '<circle cx="10" cy="10" r="6"/>'
    "</svg>"
)


class ActivityRow(BaseModel):
    """One activity feed row.

    - ``time_str`` → already-formatted relative/absolute time
    - ``actor`` → optional who-did-it span (empty = omit)
    - ``actor_html`` → trusted present() Avatar markup; wins over ``actor``
    - ``description`` → action text
    - ``drill_url`` → when set, description becomes an ``<a href>`` hub drill
      (host gates EDIT paths when UPDATE denied)
    """

    time_str: str
    description: str
    actor: str = ""
    actor_html: str = Field(
        default="",
        description="Trusted present() markup; when set, replaces the escaped actor span.",
    )
    drill_url: str = Field(
        default="",
        description="Optional hub URL; description becomes a link when set.",
    )

    @field_validator("description")
    @classmethod
    def _description_nonempty(cls, v: str) -> str:
        if not (v or "").strip():
            raise ValueError("ActivityRow requires a non-empty description")
        return v


EXEMPLARS: list[ActivityRow] = [
    ActivityRow(time_str="09:41", actor="Ada", description="approved the refund."),
    ActivityRow(
        time_str="09:12",
        actor="System",
        description="flagged the account for review.",
    ),
    ActivityRow(time_str="yesterday", description="Nightly export completed."),
]


def render(row: ActivityRow) -> str:
    """Model → one ``<li>`` activity row."""
    time_s = html.escape(row.time_str)
    actor_html = ""
    trusted = (row.actor_html or "").strip()
    if trusted:
        actor_html = f'<span class="dz-activity-actor">{trusted}</span> '
    elif row.actor:
        actor_html = f'<span class="dz-activity-actor">{html.escape(row.actor)}</span> '
    desc = html.escape(row.description)
    if row.drill_url:
        href = html.escape(row.drill_url, quote=True)
        # Empty drill_url stays byte-stable plain text (no anchor).
        desc_html = f'<a href="{href}" data-dz-activity-drill>{desc}</a>'
    else:
        desc_html = desc
    # Trailing space after bubble open class mirrors Dazzle emitter legacy.
    return (
        f'<li class="dz-activity-row" data-dz-activity-row>'
        f'<span class="dz-activity-dot">{_DOT_SVG}</span>'
        f'<div class="dz-activity-row-inner">'
        f'<div class="dz-activity-time">{time_s}</div>'
        f'<div class="dz-activity-bubble" >'
        f"{actor_html}{desc_html}"
        f"</div>"
        f"</div>"
        f"</li>"
    )


__all__ = [
    "DOM_CONTRACT",
    "ActivityRow",
    "EXEMPLARS",
    "render",
]
