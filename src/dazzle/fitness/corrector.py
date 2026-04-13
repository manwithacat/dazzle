"""Corrector — two-gate routing + alternative-generation (v1 task 17).

The corrector decides whether a finding gets auto-applied (hard route)
or held for human review (soft route), and generates fixes via two
independent LLM calls. If the primary and alternative diverge materially,
the finding is mechanically flagged as ``disambiguation=True`` — the
corrector does NOT rely on the LLM's self-reported uncertainty.

LLM interface: sync ``_LlmClient`` Protocol matching
``dazzle.llm.LLMAPIClient.complete(system_prompt, user_prompt)``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from dazzle.fitness.models import Finding

Route = Literal["hard", "soft"]
Maturity = Literal["mvp", "beta", "stable"]


@dataclass(frozen=True)
class Fix:
    """A candidate code fix produced by the corrector LLM."""

    touched_files: list[str]
    summary: str
    diff: str


class _LlmClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


def route_finding(finding: Finding, maturity: Maturity) -> Route:
    """Two-gate router.

    Gate 0: low-confidence findings always soft.
    ``spec_stale`` is always paraphrased (soft), never auto-corrected.
    Gate 1: ``maturity=stable`` kill-switch — soft everything.
    Gate 2: mechanical disambiguation — soft.
    Otherwise: hard.
    """
    if finding.low_confidence:
        return "soft"
    if finding.locus == "spec_stale":
        return "soft"
    if maturity == "stable":
        return "soft"
    if finding.disambiguation:
        return "soft"
    return "hard"


def materially_same(a: Fix, b: Fix) -> bool:
    """Two fixes are 'materially same' iff they touch the same files and
    produce equivalent diffs. Sufficient for v1's disambiguation flagging;
    semantic equivalence checks can be layered in later.
    """
    return sorted(a.touched_files) == sorted(b.touched_files) and a.diff.strip() == b.diff.strip()


_SYSTEM_PROMPT = """You are the corrector for the Agent-Led Fitness Methodology.
A fitness finding will be presented. Generate a code fix.

Return ONLY a JSON object with this shape (no prose, no fences):
  {"touched_files": ["path/..."], "summary": "...", "diff": "unified diff"}"""


def _build_user_prompt(finding: Finding, variant: str) -> str:
    return (
        f"Generate a {variant} code fix for this finding.\n\n"
        f"Finding:\n"
        f"---\n"
        f"id: {finding.id}\n"
        f"locus: {finding.locus}\n"
        f"axis: {finding.axis}\n"
        f"expected: {finding.expected}\n"
        f"observed: {finding.observed}\n"
        f"---\n"
    )


def _generate_one(finding: Finding, variant: str, llm: _LlmClient) -> Fix | None:
    response = llm.complete(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=_build_user_prompt(finding, variant),
    )
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    touched = data.get("touched_files", [])
    if not isinstance(touched, list):
        return None
    return Fix(
        touched_files=[str(f) for f in touched],
        summary=str(data.get("summary", "")),
        diff=str(data.get("diff", "")),
    )


def generate_fix(finding: Finding, llm: _LlmClient) -> tuple[Fix | None, Fix | None, Finding]:
    """Generate a primary fix plus an alternative variant.

    If both exist and differ materially, mark the finding as requiring
    disambiguation (and surface the alternative summary in
    ``alternative_fix``). Since ``Finding`` is frozen, we return an
    updated copy via ``dataclasses.replace``.
    """
    primary = _generate_one(finding, variant="best", llm=llm)
    alternative = _generate_one(finding, variant="different_approach", llm=llm)

    updated = finding
    if (
        primary is not None
        and alternative is not None
        and not materially_same(primary, alternative)
    ):
        updated = replace(
            finding,
            disambiguation=True,
            alternative_fix=alternative.summary,
        )

    return primary, alternative, updated
