"""HYPERPART: activity-feed — who-did-what row unit.

One row is the dual-lock unit. The feed list is layout furniture; validate
rows with ``require_root`` on the row root.

``description`` is plain text (escaped). Optional ``actor`` renders a leading
span inside the bubble.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, field_validator

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
    - ``description`` → action text
    """

    time_str: str
    description: str
    actor: str = ""

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
    if row.actor:
        actor_html = f'<span class="dz-activity-actor">{html.escape(row.actor)}</span> '
    # Trailing space after bubble open class mirrors Dazzle emitter legacy.
    return (
        f'<li class="dz-activity-row" data-dz-activity-row>'
        f'<span class="dz-activity-dot">{_DOT_SVG}</span>'
        f'<div class="dz-activity-row-inner">'
        f'<div class="dz-activity-time">{time_s}</div>'
        f'<div class="dz-activity-bubble" >'
        f"{actor_html}{html.escape(row.description)}"
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
