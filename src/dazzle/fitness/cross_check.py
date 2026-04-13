"""Cross-check — coverage and over-implementation findings.

Takes spec capabilities (from ``spec_extractor``) and DSL stories and
emits ``Finding`` records in the ``coverage`` axis:

  - ``story_drift``: a spec capability with no matching story.
  - ``spec_stale``: a DSL story with no matching spec capability.

The v1 match is a shallow lexical token-overlap heuristic. v1.1 may
upgrade to embedding similarity.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import uuid4

from dazzle.fitness.models import EvidenceEmbedded, Finding
from dazzle.fitness.spec_extractor import Capability


def _tokens(text: str) -> set[str]:
    return {t.lower().strip() for t in text.replace("-", " ").split() if t.strip()}


def _similar(a: str, b: str) -> bool:
    """Shallow lexical match - v1.1 may upgrade to embedding similarity.

    A match requires strictly more than half of the smaller phrase's
    tokens to appear on the other side. This keeps single-word domain
    nouns (e.g., "ticket") from creating false matches between
    unrelated phrases like "triage incoming ticket" and "close ticket".
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    overlap = ta & tb
    return len(overlap) / min(len(ta), len(tb)) > 0.5


def cross_check_capabilities(
    spec_capabilities: Sequence[Capability],
    stories: Sequence[Any],
    run_id: str,
    now: datetime,
) -> list[Finding]:
    """Compare spec capabilities against DSL stories.

    Each story is duck-typed: it must expose ``title`` and ``persona``
    attributes. Missing attributes are tolerated via ``getattr`` defaults
    so that both the real DSL ``StorySpec`` and test stubs work.
    """
    findings: list[Finding] = []

    # Coverage: spec capability -> no matching story
    for cap in spec_capabilities:
        matched = any(_similar(cap.capability, getattr(s, "title", "")) for s in stories)
        if not matched:
            findings.append(
                Finding(
                    id=f"FIND-{uuid4().hex[:8]}",
                    created=now,
                    run_id=run_id,
                    cycle=None,
                    axis="coverage",
                    locus="story_drift",
                    severity="medium",
                    persona=cap.persona,
                    capability_ref=f"spec:{cap.capability}",
                    expected=(
                        f"A DSL story implementing '{cap.capability}' for persona '{cap.persona}'"
                    ),
                    observed="No matching story found",
                    evidence_embedded=EvidenceEmbedded(
                        expected_ledger_step={},
                        diff_summary=[],
                        transcript_excerpt=[],
                    ),
                    disambiguation=False,
                    low_confidence=False,
                    status="PROPOSED",
                    route="soft",  # coverage findings default soft
                    fix_commit=None,
                    alternative_fix=None,
                )
            )

    # Over-impl: story -> no matching spec capability
    for s in stories:
        title = getattr(s, "title", "")
        persona = getattr(s, "persona", "?")
        matched = any(_similar(title, cap.capability) for cap in spec_capabilities)
        if not matched:
            findings.append(
                Finding(
                    id=f"FIND-{uuid4().hex[:8]}",
                    created=now,
                    run_id=run_id,
                    cycle=None,
                    axis="coverage",
                    locus="spec_stale",
                    severity="low",
                    persona=persona,
                    capability_ref=f"story:{title}",
                    expected=(f"Spec clause implying '{title}' for persona '{persona}'"),
                    observed="No matching spec clause found",
                    evidence_embedded=EvidenceEmbedded(
                        expected_ledger_step={},
                        diff_summary=[],
                        transcript_excerpt=[],
                    ),
                    disambiguation=False,
                    low_confidence=False,
                    status="PROPOSED",
                    route="soft",
                    fix_commit=None,
                    alternative_fix=None,
                )
            )

    return findings
