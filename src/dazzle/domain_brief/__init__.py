"""Agent-audience domain brief pipeline.

Founder prose → AGENT_DOMAIN (researchable) → hand-author DSL → validate.

DSL remains runtime SSOT. SPECIFICATION.md remains investor prose (DSL→brief).
This package is the missing human→agent intermediate.
"""

from dazzle.domain_brief.extract import extract_from_path, extract_from_text, find_founder_brief
from dazzle.domain_brief.gaps import score_gaps
from dazzle.domain_brief.models import AgentDomain
from dazzle.domain_brief.promote import promote_checklist
from dazzle.domain_brief.research import apply_research, research_and_save
from dazzle.domain_brief.store import load_domain, save_domain

__all__ = [
    "AgentDomain",
    "apply_research",
    "extract_from_path",
    "extract_from_text",
    "find_founder_brief",
    "load_domain",
    "promote_checklist",
    "research_and_save",
    "save_domain",
    "score_gaps",
]
