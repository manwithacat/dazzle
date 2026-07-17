"""Data-representation judgement substrate (#1617).

Named hatch patterns + decide / classify / prove so agents choose
sanctioned shapes instead of dual-locking Rails poly or inventing host
open-via. No MCP dependency (same posture as ``agent_loop``).
"""

from __future__ import annotations

from dazzle.representation.classify import classify_appspec, classify_project
from dazzle.representation.decide import decide_representation
from dazzle.representation.patterns import PATTERN_CATALOGUE, PatternId, list_patterns
from dazzle.representation.prove import prove_representation, prove_representation_project

__all__ = [
    "PATTERN_CATALOGUE",
    "PatternId",
    "classify_appspec",
    "classify_project",
    "decide_representation",
    "list_patterns",
    "prove_representation",
    "prove_representation_project",
]
