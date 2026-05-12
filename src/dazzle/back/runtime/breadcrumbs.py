"""
Breadcrumb trail derivation from URL paths.

Generates a list of Crumb objects from the current request path,
with optional label overrides for human-readable names.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Crumb:
    """A single breadcrumb entry."""

    label: str
    url: str | None = None


def build_breadcrumb_trail(
    path: str,
    label_overrides: dict[str, str] | None = None,
) -> list[Crumb]:
    """Build a breadcrumb trail from a URL path.

    Args:
        path: The current request path (e.g., ``/tasks/123/comments``).
        label_overrides: Optional mapping of path prefixes to display labels.

    Returns:
        List of Crumb objects. The last crumb has ``url=None`` (current page).
    """
    overrides = label_overrides or {}
    segments = [s for s in path.strip("/").split("/") if s]

    if not segments:
        return [Crumb(label="Home", url="/")]

    crumbs: list[Crumb] = [Crumb(label="Home", url="/")]

    for i, segment in enumerate(segments):
        accumulated = "/" + "/".join(segments[: i + 1])
        label = overrides.get(accumulated, segment.replace("-", " ").replace("_", " ").title())
        is_last = i == len(segments) - 1
        suppress_url = is_last and len(segments) > 1
        crumbs.append(Crumb(label=label, url=None if suppress_url else accumulated))

    return crumbs
