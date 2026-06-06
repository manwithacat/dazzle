"""Data models for capability discovery."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExampleRef:
    """A reference to a capability demonstrated in an example app."""

    app: str
    file: str
    line: int
    context: str


@dataclass(frozen=True)
class Relevance:
    """A contextual reference to a Dazzle capability that may be applicable."""

    context: str
    capability: str
    category: str
    examples: list[ExampleRef]
    kg_entity: str
    # Opt-in capability id required to surface this proactively (#1342 Phase 2).
    # None = ungated (always surfaced). When set and the capability isn't active,
    # the proactive surface drops the item (still discoverable via direct query).
    gated_by: str | None = None
