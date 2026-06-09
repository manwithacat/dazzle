"""Result type — distinguish multiple failure modes from `None`-as-sentinel.

Counter-prior: `optional-instead-of-result`. The catalogue at
`docs/counter-priors/optional-instead-of-result.md` explains the antipattern
this shape inoculates against and the convention for composing Err types.

Pattern-matching is the canonical consumption idiom:

    match parse_event(text):
        case Ok(event):
            handle(event)
        case Err(EmptyInput()):
            log.warning("empty input — skipping")
        case Err(MalformedJson() as e):
            log.error("parse failed: %s", e.detail)

The four methods (`unwrap`, `unwrap_or`, `is_ok`, `is_err`) cover common
single-branch checks. Match handles composition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """Successful Result carrying a value."""

    value: T

    def unwrap(self) -> T:
        """Return the wrapped value. Always succeeds for Ok."""
        return self.value

    def unwrap_or(self, default: T) -> T:
        """Return the wrapped value. The `default` is unused for Ok."""
        return self.value

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class Err[E]:
    """Failed Result carrying an error value."""

    error: E

    def unwrap(self) -> NoReturn:
        """Raise `UnwrapError`. Use `match` or `unwrap_or` for safety."""
        raise UnwrapError(self.error)

    def unwrap_or[T2](self, default: T2) -> T2:
        """Return the `default`. The wrapped error is discarded.

        The method-local type variable T2 is independent of E — Err knows
        only the error's type, not the value type of the matching Ok.
        """
        return default

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True


type Result[T, E] = Ok[T] | Err[E]


class UnwrapError(Exception):
    """Raised by `Err.unwrap()`. Carries the wrapped error as `.error`."""

    def __init__(self, error: object) -> None:
        super().__init__(f"called unwrap() on an Err value: {error!r}")
        self.error = error
