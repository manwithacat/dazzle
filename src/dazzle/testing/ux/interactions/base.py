"""Base types for the INTERACTION_WALK harness.

Each v1 walk (card_drag, card_add, card_remove_reachable) implements
the :class:`Interaction` protocol and returns an :class:`InteractionResult`.
The harness is a deliberately minimal: a ``Walk`` is just
``list[Interaction]``, composed in user code and executed by
:func:`run_walk`. No registry, no magic — new walks land as new files
in this package.

See ``docs/proposals/interaction-walk-harness.md`` for the full design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from playwright.sync_api import Page


@dataclass
class InteractionResult:
    """Outcome of a single interaction.

    Attributes:
        name: The interaction identifier (matches ``Interaction.name``).
        passed: True iff the gate the interaction gates is satisfied.
        reason: Human-readable explanation of a failure. Empty on pass.
        evidence: Optional typed payload — bounding-box deltas, captured
            XHR URLs, opacity values, anything the interaction wants to
            include in its report. Kept as ``dict[str, Any]`` to avoid
            coupling the base type to every future walk's shape.
    """

    name: str
    passed: bool
    reason: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Interaction(Protocol):
    """Scripted gesture + assertion against a Playwright ``Page``.

    Implementations construct themselves with whatever inputs the walk
    needs (card IDs, region names, step counts, thresholds) and perform
    all their work in :meth:`execute`. ``name`` is used for identifying
    the interaction in reports and mapping results back to source.
    """

    name: str

    def execute(self, page: Page) -> InteractionResult:
        """Run the interaction against ``page`` and return its result.

        Must not raise on assertion failure — return a result with
        ``passed=False`` and a ``reason``. Raise only on genuinely
        unrecoverable setup errors (e.g. Page closed unexpectedly).
        """
        ...


def run_walk(page: Page, walk: list[Interaction]) -> list[InteractionResult]:
    """Execute ``walk`` against ``page`` in order, returning every result.

    Does not short-circuit on failure — callers get the full picture of
    which interactions passed and which didn't. An exception from any
    interaction propagates (we only suppress failed-assertion outcomes,
    not catastrophic errors).
    """
    return [interaction.execute(page) for interaction in walk]
