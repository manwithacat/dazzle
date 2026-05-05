"""Escape-hatch primitives — the explicit way out of the typed system.

`RawHTML` accepts an arbitrary HTML string and emits it verbatim. Used for
Jinja interop (Plan 3) and for the rare "this is too custom to model" case.
A lint count of `RawHTML(...)` occurrences per surface tracks migration
progress; downstream apps that have not migrated will have many, fully-
migrated example apps will have zero.

`Slot` names a hole in a Fragment tree that is filled later. Used by the
renderer for delayed/streamed content. Not a free-form escape — the slot
name must match the substitution map at render time.
"""

import re
from dataclasses import dataclass

_VALID_SLOT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class RawHTML:
    """Verbatim HTML emission. The audit-visible escape hatch.

    WARNING: bypasses HTML escaping. The caller is responsible for ensuring
    `html` is safe to inject — never construct from untrusted input (user-
    supplied strings, request data, DB content rendered as HTML). Prefer
    typed Fragment primitives; reserve RawHTML for trusted pre-rendered
    output (Jinja interop, static assets).

    Occurrences are lint-counted per surface as a migration-progress metric;
    fully Fragment-native surfaces have zero RawHTML uses.
    """

    html: str

    def __post_init__(self) -> None:
        if not isinstance(self.html, str):
            raise TypeError(f"RawHTML expects str, got {type(self.html).__name__}")


@dataclass(frozen=True, slots=True)
class Slot:
    """A named hole filled at render time."""

    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError(f"Slot expects str name, got {type(self.name).__name__}")
        if not _VALID_SLOT_NAME.match(self.name):
            raise ValueError(f"invalid slot name {self.name!r}")
