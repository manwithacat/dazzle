"""Wrapper types for htmx attribute values.

These exist so that fields like `hx_target: TargetSelector | None` in primitives
carry validation at construction time, not at template-render time. A
TargetSelector that is constructed has been parsed and is structurally valid.
"""

import re
from dataclasses import dataclass

_DANGEROUS_SCHEMES = frozenset({"javascript", "data", "vbscript"})
_TARGET_KEYWORD = re.compile(r"^(this|closest [a-z][a-z0-9-]*|find [a-z][a-z0-9-]*|next|previous)$")
_TARGET_ID = re.compile(r"^#[A-Za-z][A-Za-z0-9_-]*$")
_TARGET_CLASS = re.compile(r"^\.[A-Za-z][A-Za-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class URL:
    """A validated URL for use in htmx attributes.

    Accepts relative paths (`/tasks/42`) and absolute http/https URLs. Rejects
    `javascript:`, `data:`, and `vbscript:` schemes which are XSS vectors.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("URL cannot be empty")
        if ":" in self.value:
            scheme = self.value.split(":", 1)[0].lower()
            if scheme in _DANGEROUS_SCHEMES:
                raise ValueError(f"disallowed scheme {scheme!r} in URL")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class TargetSelector:
    """An htmx target selector. One of: `#id`, `.class`, or a keyword form
    (`this`, `closest <tag>`, `find <tag>`, `next`, `previous`).
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("TargetSelector cannot be empty")
        if not (
            _TARGET_KEYWORD.match(self.value)
            or _TARGET_ID.match(self.value)
            or _TARGET_CLASS.match(self.value)
        ):
            raise ValueError(f"invalid target selector {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class HxTrigger:
    """An htmx trigger spec. Currently a thin wrapper around the trigger
    string (e.g. `click`, `keyup changed delay:500ms`). Validation here is
    light — only that the string is non-empty. Future versions may parse
    the trigger DSL more strictly."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("HxTrigger cannot be empty")

    def __str__(self) -> str:
        return self.value
