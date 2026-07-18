"""Markdown report renderer for ``dazzle qa trial`` runs.

The trial harness produces friction observations and a verdict. This
module formats them into a prose-forward markdown report intended for
human reading, not machine consumption.

Output shape:

.. code-block:: text

   # Trial: <scenario-name>
   *as <user_identity first line> — <timestamp>*

   ## Verdict
   > <one-paragraph verdict>

   ## Friction observations (<n>)

   ### <category> — <title-derived-from-description>
   > <description>
   **Severity:** <low/medium/high>
   **Where:** <url>
   **Evidence:** <evidence>

Each section is deliberately loose. The triager will decide which
items become issues and which are "correct by design."
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.qa.signing_verifier import SigningOutcome

_CATEGORY_ORDER = ("bug", "missing", "confusion", "aesthetic", "praise", "other")
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_CLUSTER_SIMILARITY_THRESHOLD = 0.65
# TR-32: praise rephrases more freely than friction; lower SequenceMatcher
# floor and rely on token Jaccard so "Issue Board is great" / "filters on
# the Issue Board make triage easy" still collapse when URL+evidence align.
_PRAISE_SIMILARITY_THRESHOLD = 0.50
_TOKEN_JACCARD_THRESHOLD = 0.45
_PRAISE_TOKEN_JACCARD_THRESHOLD = 0.38
# #1073 — Secondary collapse pass keyed on shared evidence rather than
# category/description. Catches the cross-category dedup miss observed
# in cycles 3, 112, and 120 where the same DOM excerpt was filed under
# different categories (bug/missing/confusion/other) with varied wording.
_EVIDENCE_PREFIX_LEN = 80
_EVIDENCE_SOFT_RATIO = 0.80
_STOPWORDS = frozenset(
    """
    a an the and or but if then else when while for of on in to from by with
    as at is are was were be been being this that these those it its i me my
    we our you your they them their really very just also more most such
    """.split()
)


@dataclass
class TrialReport:
    """Assembled trial output ready for rendering."""

    scenario_name: str
    user_identity_headline: str
    verdict: str
    friction: list[dict[str, Any]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    step_count: int = 0
    duration_seconds: float = 0.0
    tokens_used: int = 0
    outcome: str = ""
    signing_outcomes: dict[str, Any] | None = None
    # Gen-2 structured decision fields (optional; empty when agent omitted).
    recommend: str = ""
    criteria_scores: list[dict[str, str]] = field(default_factory=list)
    pilot_blockers_summary: str = ""


def _first_line(text: str) -> str:
    """Return the first non-empty line of ``text``, stripped."""
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _title_from_description(desc: str, max_chars: int = 80) -> str:
    """Derive a short heading from a friction description.

    Uses the first sentence (split on ``. ``) and truncates if needed.
    Preserves case — a business-user-framed description may start with
    a proper noun or first-person pronoun.
    """
    desc = desc.strip()
    if not desc:
        return "(no description)"
    head = desc.split(". ", 1)[0].rstrip(".")
    if len(head) > max_chars:
        head = head[: max_chars - 1].rstrip() + "…"
    return head


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _token_set(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", _norm_ws(text))
    return {t for t in tokens if len(t) > 2 and t not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _descriptions_similar(a: str, b: str, *, category: str) -> bool:
    """True when two observation descriptions are near-duplicates.

    Praise uses a softer floor (TR-32) because positive framings rephrase
    more while still pointing at the same surface.
    """
    a_n, b_n = _norm_ws(a), _norm_ws(b)
    if not a_n or not b_n:
        return False
    thr = _PRAISE_SIMILARITY_THRESHOLD if category == "praise" else _CLUSTER_SIMILARITY_THRESHOLD
    if SequenceMatcher(None, a_n, b_n).ratio() >= thr:
        return True
    j_thr = _PRAISE_TOKEN_JACCARD_THRESHOLD if category == "praise" else _TOKEN_JACCARD_THRESHOLD
    return _jaccard(_token_set(a_n), _token_set(b_n)) >= j_thr


def _evidence_similar(a: str, b: str) -> bool:
    """DOM evidence match — exact prefix or soft full-string similarity."""
    a_n, b_n = _norm_ws(a), _norm_ws(b)
    if not a_n or not b_n:
        return False
    if a_n[:_EVIDENCE_PREFIX_LEN] == b_n[:_EVIDENCE_PREFIX_LEN]:
        return True
    return SequenceMatcher(None, a_n[:200], b_n[:200]).ratio() >= _EVIDENCE_SOFT_RATIO


def _cluster_friction(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse near-duplicate friction entries.

    Two-pass collapse (#1073, TR-32):

    1. **Same-category pass**: groups entries with the same ``category``
       and ``url`` whose descriptions are similar via SequenceMatcher
       and/or token Jaccard (praise uses softer floors).
    2. **Cross-category evidence pass**: collapses surviving clusters
       that share the same ``url`` + similar ``evidence`` (prefix or soft
       ratio). Fires when the agent split one observable phenomenon
       across multiple categories (`missing` + `other` + `confusion`)
       because the description phrasing varied, even though the DOM
       evidence is the same phenomenon.

    The first entry in each group becomes canonical and gets a
    ``similar_count`` field; the rest are dropped from the rendered
    report. Raw JSON transcripts still include every entry.
    """
    # Pass 1 — same-category, description-similarity clustering.
    clusters: list[dict[str, Any]] = []
    for entry in items:
        category = entry.get("category", "other")
        url = (entry.get("url") or "").strip()
        description = entry.get("description") or ""

        matched = False
        for canonical in clusters:
            if canonical.get("category") != category:
                continue
            if (canonical.get("url") or "").strip() != url:
                continue
            if _descriptions_similar(
                canonical.get("description") or "",
                description,
                category=str(category),
            ):
                canonical["similar_count"] = canonical.get("similar_count", 1) + 1
                matched = True
                break

        if not matched:
            clusters.append(dict(entry))

    # Pass 2 — cross-category collapse keyed on (url, similar evidence).
    if not clusters:
        return clusters

    collapsed: list[dict[str, Any]] = []
    for canonical in clusters:
        url = (canonical.get("url") or "").strip()
        evidence = canonical.get("evidence") or ""
        # An entry with empty url or evidence has no cross-category dedup
        # signal — pass it through unmolested.
        if not url or not _norm_ws(evidence):
            collapsed.append(canonical)
            continue
        matched = False
        for prior in collapsed:
            prior_url = (prior.get("url") or "").strip()
            if prior_url != url:
                continue
            if _evidence_similar(prior.get("evidence") or "", evidence):
                prior["similar_count"] = prior.get("similar_count", 1) + canonical.get(
                    "similar_count", 1
                )
                matched = True
                break
        if not matched:
            collapsed.append(canonical)

    return collapsed


def _sort_friction(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort friction entries by category, then severity, preserving
    insertion order within ties."""

    def key(entry: dict[str, Any]) -> tuple[int, int]:
        cat = entry.get("category", "other")
        sev = entry.get("severity", "medium")
        cat_idx = _CATEGORY_ORDER.index(cat) if cat in _CATEGORY_ORDER else len(_CATEGORY_ORDER)
        sev_idx = _SEVERITY_ORDER.get(sev, 1)
        return (cat_idx, sev_idx)

    return sorted(items, key=key)


def render_trial_report(report: TrialReport) -> str:
    """Render a :class:`TrialReport` as markdown."""
    lines: list[str] = []

    lines.append(f"# Trial: {report.scenario_name}")
    identity = report.user_identity_headline or "evaluator"
    ts = report.generated_at.strftime("%Y-%m-%d %H:%M")
    lines.append(f"*as {identity} — {ts}*")
    lines.append("")

    # Verdict first — the reader wants the bottom line up top.
    if report.verdict:
        lines.append("## Verdict")
        lines.append("")
        if report.recommend:
            lines.append(f"**Recommend:** `{report.recommend}`")
            lines.append("")
        for para in report.verdict.strip().split("\n\n"):
            lines.append(f"> {para.strip()}")
        lines.append("")
        if report.pilot_blockers_summary:
            lines.append(f"**Pilot blockers:** {report.pilot_blockers_summary}")
            lines.append("")
    else:
        lines.append("## Verdict")
        lines.append("")
        lines.append("*(no verdict recorded — run ended before `done`)*")
        lines.append("")

    # Gen-2 adoption criteria scores (when agent provided them).
    if report.criteria_scores:
        lines.append("## Adoption criteria")
        lines.append("")
        for row in report.criteria_scores:
            crit = row.get("criterion", "?")
            score = row.get("score", "untested")
            note = (row.get("note") or "").strip()
            if note:
                lines.append(f"- **{crit}** — `{score}`: {note}")
            else:
                lines.append(f"- **{crit}** — `{score}`")
        lines.append("")

    # Run metadata — compact, one line.
    meta_bits = []
    if report.step_count:
        meta_bits.append(f"{report.step_count} steps")
    if report.duration_seconds:
        meta_bits.append(f"{report.duration_seconds:.0f}s")
    if report.tokens_used:
        meta_bits.append(f"{report.tokens_used:,} tokens")
    if report.outcome:
        meta_bits.append(f"outcome={report.outcome}")
    if report.recommend:
        meta_bits.append(f"recommend={report.recommend}")
    if meta_bits:
        lines.append(f"*Run: {' · '.join(meta_bits)}*")
        lines.append("")

    # Friction observations.
    raw_count = len(report.friction)
    friction = _sort_friction(_cluster_friction(list(report.friction)))
    dedup_suffix = (
        f" · {raw_count - len(friction)} near-duplicates clustered"
        if len(friction) < raw_count
        else ""
    )
    lines.append(f"## Friction observations ({len(friction)}{dedup_suffix})")
    lines.append("")

    if not friction:
        lines.append(
            "*(no friction recorded — the trial either went smoothly or ended "
            "before anything was flagged)*"
        )
        lines.append("")
    else:
        last_category: str | None = None
        for entry in friction:
            category = entry.get("category", "other")
            severity = entry.get("severity", "medium")
            description = entry.get("description", "").strip()
            url = entry.get("url", "").strip()
            evidence = entry.get("evidence", "").strip()

            if category != last_category:
                lines.append(f"### {category}")
                lines.append("")
                last_category = category

            title = _title_from_description(description)
            lines.append(f"**{title}**")
            lines.append("")
            if description and description != title:
                lines.append(f"> {description}")
                lines.append("")
            meta: list[str] = [f"*severity:* {severity}"]
            if url:
                meta.append(f"*where:* `{url}`")
            if entry.get("blocks_pilot"):
                meta.append("*blocks_pilot:* yes")
            fva = (entry.get("framework_vs_app") or "").strip()
            if fva and fva != "unclear":
                meta.append(f"*scope:* {fva}")
            similar = entry.get("similar_count", 1)
            if similar > 1:
                meta.append(f"*reported:* ×{similar}")
            lines.append(" · ".join(meta))
            lines.append("")
            if evidence:
                lines.append("```")
                # Trim evidence to keep the report readable; full evidence is
                # still in the JSON transcript for deep dives.
                snippet = evidence if len(evidence) < 600 else evidence[:597] + "..."
                lines.append(snippet)
                lines.append("```")
                lines.append("")

    # Signing outcomes — opt-in block; only rendered when present.
    if report.signing_outcomes:
        so = report.signing_outcomes
        lines.append("## Signing Outcomes")
        lines.append("")
        lines.append(f"- **detected:** {so.get('detected')}")
        lines.append(f"- **expected outcome (inferred):** {so.get('expected_outcome_inferred')}")
        functional = so.get("functional") or {}
        lines.append(f"- **functional:** {functional}")
        sig_integrity = so.get("signature_integrity") or {}
        lines.append(f"- **signature integrity:** {sig_integrity}")
        latency = so.get("latency_ms") or {}
        lines.append(f"- **latency (ms):** {latency}")
        lines.append("")

    return "\n".join(lines)


def trial_abort_message(outcome: str, error: str | None, step_count: int = 0) -> str | None:
    """Non-None when the trial must exit nonzero (#1375).

    A transcript with ``outcome == "error"`` means the agent loop died —
    LLM failure (billing/auth/CLI), observer crash, or a failed initial
    navigation. Downstream automation (the /improve trials lane) reads
    the exit code; "Trial complete. 0 friction observation(s)" + exit 0
    here books an infrastructure failure as a clean PASS.
    """
    if outcome != "error":
        return None
    detail = error or "unknown agent-loop error"
    ran = f"after {step_count} completed step(s)" if step_count else "before any step completed"
    return f"Trial ABORTED {ran}: {detail}"


def build_trial_report(
    *,
    scenario_name: str,
    user_identity: str,
    friction: list[dict[str, Any]],
    verdict: str,
    step_count: int = 0,
    duration_seconds: float = 0.0,
    tokens_used: int = 0,
    outcome: str = "",
    signing_outcome: SigningOutcome | None = None,
    recommend: str = "",
    criteria_scores: list[dict[str, str]] | None = None,
    pilot_blockers_summary: str = "",
) -> TrialReport:
    """Convenience builder — pulls the one-line identity headline
    from the multi-line user_identity block."""
    signing_outcomes: dict[str, Any] | None = None
    if signing_outcome is not None:
        signing_outcomes = asdict(signing_outcome)
    return TrialReport(
        scenario_name=scenario_name,
        user_identity_headline=_first_line(user_identity),
        verdict=verdict,
        friction=friction,
        step_count=step_count,
        duration_seconds=duration_seconds,
        tokens_used=tokens_used,
        outcome=outcome,
        signing_outcomes=signing_outcomes,
        recommend=recommend or "",
        criteria_scores=list(criteria_scores or []),
        pilot_blockers_summary=pilot_blockers_summary or "",
    )
