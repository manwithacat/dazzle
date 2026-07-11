"""HYPERPART: profile-card — identity panel unit.

The dual-lock unit is the whole card (identity + optional stats + facts).
Region wrapper is layout furniture; validate with ``require_root`` on the card.
"""

from __future__ import annotations

import html

from pydantic import BaseModel, Field, model_validator

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="profile-card",
    root="[data-dz-profile-card]",
    nodes=(
        Node(
            "[data-dz-profile-card]",
            attrs={"data-dz-profile-card": Present()},
        ),
    ),
)


class ProfileCard(BaseModel):
    """Identity panel for one focused record.

    At least one of ``primary``, ``avatar_url``, or ``initials`` is required.
    ``stats`` is ``(label, value)`` pairs (empty value → em-dash).
    ``facts`` is free-text bullets.
    """

    primary: str = ""
    secondary: str = ""
    avatar_url: str = ""
    initials: str = ""
    stats: list[tuple[str, str]] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _identity_required(self) -> ProfileCard:
        if not (self.primary or self.avatar_url or self.initials):
            raise ValueError(
                "ProfileCard requires at least one of primary, avatar_url, or initials"
            )
        return self


EXEMPLARS: list[ProfileCard] = [
    ProfileCard(
        primary="Maya Reyes",
        secondary="Operations lead · North grid",
        initials="MR",
        stats=[
            ("Open work orders", "7"),
            ("Sites", "3"),
            ("On call", ""),
        ],
        facts=["Certified for HV switching", "Joined March 2024"],
    ),
    ProfileCard(
        primary="Jordan Dias",
        avatar_url="https://example.test/avatar.jpg",
        secondary="Ops",
    ),
]


def render(card: ProfileCard) -> str:
    """Model → profile card (with region wrapper matching Dazzle emit)."""
    if card.avatar_url:
        avatar_html = (
            f'<img src="{html.escape(card.avatar_url, quote=True)}" '
            f'alt="{html.escape(card.primary, quote=True)}" '
            f'class="dz-profile-avatar" />'
        )
    elif card.initials:
        avatar_html = (
            f'<span class="dz-profile-initials" aria-hidden="true">'
            f"{html.escape(card.initials)}</span>"
        )
    else:
        avatar_html = ""

    text_inner = ""
    if card.primary:
        text_inner += f'<h3 class="dz-profile-primary">{html.escape(card.primary)}</h3>'
    if card.secondary:
        text_inner += f'<p class="dz-profile-secondary">{html.escape(card.secondary)}</p>'
    identity_html = (
        f'<div class="dz-profile-identity">'
        f"{avatar_html}"
        f'<div class="dz-profile-text">{text_inner}</div>'
        f"</div>"
    )

    stats_html = ""
    if card.stats:
        stat_rows = "".join(
            f'<div class="dz-profile-stat">'
            f'<dt class="dz-profile-stat-label">{html.escape(label)}</dt>'
            f'<dd class="dz-profile-stat-value">'
            f"{html.escape(value) if value else '—'}</dd>"
            f"</div>"
            for label, value in card.stats
        )
        stats_html = f'<dl class="dz-profile-stats">{stat_rows}</dl>'

    facts_html = ""
    if card.facts:
        fact_items = "".join(
            f'<li class="dz-profile-fact">'
            f'<span class="dz-profile-fact-bullet" aria-hidden="true">·</span>'
            f'<span class="dz-profile-fact-text">{html.escape(fact)}</span>'
            f"</li>"
            for fact in card.facts
        )
        facts_html = f'<ul class="dz-profile-facts">{fact_items}</ul>'

    return (
        f'<div class="dz-profile-card-region">'
        f'<div class="dz-profile-card" data-dz-profile-card>'
        f"{identity_html}{stats_html}{facts_html}"
        f"</div>"
        f"</div>"
    )


__all__ = [
    "DOM_CONTRACT",
    "ProfileCard",
    "EXEMPLARS",
    "render",
]
