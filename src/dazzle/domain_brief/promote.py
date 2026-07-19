"""Promote checklist — when AGENT_DOMAIN may drive DSL hand-author."""

from __future__ import annotations

from typing import Any

from dazzle.domain_brief.gaps import GapsReport, score_gaps
from dazzle.domain_brief.models import AgentDomain


def promote_checklist(domain: AgentDomain) -> dict[str, Any]:
    """Return promote readiness + ordered DSL authoring steps."""
    report: GapsReport = score_gaps(domain)
    steps: list[str] = []
    if report.ready_to_promote:
        steps = [
            "1. Author personas with STABLE id_hint values "
            f"({', '.join(p.id_hint for p in domain.personas)}).",
            "2. Author entities for grounded nouns only "
            f"({', '.join(n.name for n in domain.nouns if n.status == 'grounded')}).",
            "3. Add status lifecycles where lifecycle_hint is non-empty.",
            "4. Author workspaces/desks from domain.desks; bind filters with owner_field_hint "
            "+ current_user (never invent chrome fields).",
            "5. Seed demo_spine stories under dsl/seeds/demo_data using STABLE_PERSONA_USER_IDS.",
            "6. dazzle validate → serve → demo reset-and-load → product_quality score.",
            "7. Do not re-run bootstrap as SSOT (counter-prior bootstrap_pollution).",
        ]
    return {
        "ready": report.ready_to_promote,
        "gaps": report.to_dict(),
        "dsl_steps": steps,
        "knowledge": [
            "knowledge(operation='concept', term='entity')",
            "knowledge(operation='concept', term='persona')",
            "knowledge(operation='concept', term='workspace')",
            "knowledge(operation='concept', term='demo_identity')",
            "knowledge(operation='counter_prior', id='bootstrap_pollution')",
            "knowledge(operation='workflow', workflow='first_principles_demo')",
        ],
        "warning": (
            "AGENT_DOMAIN is cognition draft. DSL is runtime SSOT. "
            "Never copy ungrounded nouns into entity blocks."
        ),
    }
