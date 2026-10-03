"""The validation-result shape every spec loader accumulates into.

Three loaders — ``core/sitespec_loader``, ``core/themespec_loader`` and
``pitch/loader`` — each defined their own ``*ValidationResult`` class with
byte-identical ``__init__``, ``add_error``, ``add_warning`` and ``is_valid``.
``dazzle fitness clones`` reported it as an exact-body cluster (#1747).

The asymmetry was the real cost, not the duplication: only the two ``core/``
copies carried docstrings and a ``__repr__``, and only ``sitespec_loader``
explained the one semantic question anyone reading the code would have —
whether a warning invalidates the result. Three copies of an accumulator that
nobody documented is three places for the next loader to diverge.

``core/validation/`` is AppSpec *semantic* validation and is deliberately not the
home for this: that package checks an AppSpec, this accumulates the outcome of
loading a spec file.
"""

from __future__ import annotations


class ValidationResult:
    """Errors and warnings accumulated while loading or validating a spec.

    Subclass and add whatever the specific loader needs. ``errors`` and
    ``warnings`` are plain lists of messages; callers that care about structure
    should raise or return a typed error instead of accumulating prose.
    """

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def add_error(self, message: str) -> None:
        """Record an error. Any error makes the result invalid."""
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        """Record a warning. Warnings never invalidate the result."""
        self.warnings.append(message)

    @property
    def is_valid(self) -> bool:
        """True when there are no errors.

        Warnings are deliberately not fatal — a loader that cannot resolve an
        optional field should warn and carry on, not refuse the file.
        """
        return len(self.errors) == 0

    def __repr__(self) -> str:
        return f"{type(self).__name__}(errors={len(self.errors)}, warnings={len(self.warnings)})"
