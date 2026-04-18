"""INTERACTION_WALK harness — scripted gestures + state diffs.

Each submodule implements one :class:`Interaction` — a scripted gesture
against a live Dazzle workspace (drag a card, click Add, Tab to
reach a primary action) that returns a typed :class:`InteractionResult`
describing what happened.

Design doc: ``docs/proposals/interaction-walk-harness.md``.
Tracking issue: https://github.com/manwithacat/dazzle/issues/800.
"""

from __future__ import annotations

from dazzle.testing.ux.interactions.base import (
    Interaction,
    InteractionResult,
    run_walk,
)
from dazzle.testing.ux.interactions.card_add import CardAddInteraction
from dazzle.testing.ux.interactions.card_drag import CardDragInteraction
from dazzle.testing.ux.interactions.card_remove_reachable import (
    CardRemoveReachableInteraction,
)

__all__ = [
    "CardAddInteraction",
    "CardDragInteraction",
    "CardRemoveReachableInteraction",
    "Interaction",
    "InteractionResult",
    "run_walk",
]
