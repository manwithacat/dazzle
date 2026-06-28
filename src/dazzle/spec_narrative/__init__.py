"""DSL → stakeholder specification narrative.

Stage 1 (deterministic): extract a fact-only ``SpecBrief`` from an AppSpec.
Stage 2 (agent-driven): the ``/spec-narrate`` skill renders the brief to prose.
"""

from dazzle.spec_narrative.brief import build_brief
from dazzle.spec_narrative.models import SpecBrief

__all__ = ["SpecBrief", "build_brief"]
