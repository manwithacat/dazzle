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

__all__ = ["Interaction", "InteractionResult", "run_walk"]
