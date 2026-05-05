"""Wrapper types for htmx attribute values.

These exist so that fields like `hx_target: TargetSelector | None` in primitives
carry validation at construction time, not at template-render time. A
TargetSelector that is constructed has been parsed and is structurally valid.
"""

import re
from dataclasses import dataclass

# Allowed schemes for htmx URLs. Any URL with a scheme not in this set is
# rejected. Relative paths (no scheme) are always permitted. This is a strict
# allowlist — adding a new scheme requires a deliberate code change.
_ALLOWED_SCHEMES = frozenset({"http", "https", "mailto"})
_TARGET_KEYWORD = re.compile(
    r"^(this|next|previous|"
    r"closest [A-Za-z0-9_.#\[\]=\"'-]+|"
    r"find [A-Za-z0-9_.#\[\]=\"'-]+)$"
)
_TARGET_ID = re.compile(r"^#[A-Za-z][A-Za-z0-9_-]*$")
_TARGET_CLASS = re.compile(r"^\.[A-Za-z][A-Za-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class URL:
    """A validated URL for use in htmx attributes.

    Accepts relative paths (`/tasks/42`, `?q=1`, `#fragment`) and absolute URLs
    with a scheme in `_ALLOWED_SCHEMES` (http, https, mailto). Rejects any
    other scheme — including `javascript:`, `data:`, `vbscript:`, `file:` —
    which prevents XSS and information-disclosure vectors. Leading whitespace
    is rejected so `\tjavascript:...` or ` JAVASCRIPT:...` cannot bypass the
    check via a browser tolerance.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("URL cannot be empty")
        if self.value != self.value.strip():
            raise ValueError(f"URL cannot have leading or trailing whitespace: {self.value!r}")
        if ":" in self.value:
            scheme = self.value.split(":", 1)[0].lower()
            if scheme not in _ALLOWED_SCHEMES:
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
        if not self.value or not self.value.strip():
            raise ValueError("HxTrigger cannot be empty or whitespace-only")

    def __str__(self) -> str:
        return self.value
