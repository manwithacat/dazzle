"""Data models for capability discovery."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExampleRef:
    """One place an example app demonstrates a capability.

    ``app`` + ``context`` is the whole reference. It deliberately carries no
    ``file``/``line``: those were produced by scanning an app's DSL for the
    first line containing a capability's option value, which is *a* place the
    capability appears and not *the* place the described field is — every field
    using ``widget=picker`` in an app was cited at the same first-match line.
    A pointer that looks authoritative and is wrong is worse than a context
    string an agent can grep (#1755).
    """

    app: str
    context: str


@dataclass(frozen=True)
class Relevance:
    """One contextual reference to a Dazzle capability that may be applicable.

    Rules emit these per *occurrence* — a rule that fires on 14 fields emits 14
    items. Consumers read :class:`RelevanceGroup`, which folds them by
    capability (see :func:`dazzle.core.discovery.engine.fold_relevance`).
    """

    context: str
    capability: str
    category: str
    examples: list[ExampleRef]
    kg_entity: str
    # Opt-in capability id required to surface this proactively (#1342 Phase 2).
    # None = ungated (always surfaced). When set and the capability isn't active,
    # the proactive surface drops the item (still discoverable via direct query).
    gated_by: str | None = None


@dataclass(frozen=True)
class RelevanceGroup:
    """Every place a capability applies in one project, as one item.

    A rule's raw output is per-occurrence, and every occurrence carried the
    same full exemplar list. On `examples/fieldtest_hub` that was 35 entries
    describing 8 capabilities, 416 exemplar rows for 18 distinct usages — 87%
    of the `dazzle lint` payload, repeated verbatim. Grouping by capability
    and capping each list turns that into 8 entries and ~5 KB.

    Every list is capped and every cap is reported (``contexts_truncated`` /
    ``examples_truncated`` with ``examples_total``): a slice that does not
    announce itself is a silent lie.
    """

    capability: str
    category: str
    kg_entity: str
    occurrences: int
    contexts: list[str]
    contexts_truncated: bool
    examples: list[ExampleRef]
    examples_total: int
    examples_truncated: bool
    gated_by: str | None = None
