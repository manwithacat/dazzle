"""Independence guardrail — Jaccard similarity between two sensors.

When two capability-producing sensors (e.g., the LLM-backed spec
extractor and a deterministic DSL walker) agree too often, their
"independent" checks have collapsed into a single signal. This module
measures that overlap and reports ``INDEPENDENCE_DEGRADED`` when it
crosses the configured threshold.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from dazzle.fitness.spec_extractor import Capability


@dataclass(frozen=True)
class IndependenceReport:
    jaccard: float
    shared: list[tuple[str, str]]
    only_a: list[tuple[str, str]]
    only_b: list[tuple[str, str]]
    threshold: float
    degraded: bool
    insufficient_data: bool


def _as_set(caps: Iterable[Capability]) -> set[tuple[str, str]]:
    return {(c.capability.strip().lower(), c.persona.strip().lower()) for c in caps}


def measure_independence(
    sensor_a: list[Capability],
    sensor_b: list[Capability],
    threshold: float,
) -> IndependenceReport:
    """Compute Jaccard similarity between two capability sensors.

    Both sensors are converted to sets of ``(capability, persona)`` tuples
    (case-insensitive). Empty inputs yield ``insufficient_data=True``.
    Jaccard strictly greater than ``threshold`` flags ``degraded=True``.
    """
    set_a = _as_set(sensor_a)
    set_b = _as_set(sensor_b)

    if not set_a and not set_b:
        return IndependenceReport(
            jaccard=0.0,
            shared=[],
            only_a=[],
            only_b=[],
            threshold=threshold,
            degraded=False,
            insufficient_data=True,
        )

    intersection = set_a & set_b
    union = set_a | set_b
    jaccard = len(intersection) / len(union) if union else 0.0

    return IndependenceReport(
        jaccard=jaccard,
        shared=sorted(intersection),
        only_a=sorted(set_a - set_b),
        only_b=sorted(set_b - set_a),
        threshold=threshold,
        degraded=jaccard > threshold,
        insufficient_data=False,
    )
