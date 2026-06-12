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

from dataclasses import asdict, dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.qa.signing_verifier import SigningOutcome

_CATEGORY_ORDER = ("bug", "missing", "confusion", "aesthetic", "praise", "other")
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_CLUSTER_SIMILARITY_THRESHOLD = 0.65
# #1073 — Secondary collapse pass keyed on shared evidence rather than
# category/description. Catches the cross-category dedup miss observed
# in cycles 3, 112, and 120 where the same DOM excerpt was filed under
# different categories (bug/missing/confusion/other) with varied wording.
_EVIDENCE_PREFIX_LEN = 80


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


def _cluster_friction(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse near-duplicate friction entries.

    Two-pass collapse (#1073):

    1. **Same-category pass**: groups entries with the same ``category``
       and ``url`` whose descriptions have a ``SequenceMatcher`` ratio
       above the threshold. The original v0.57.83 algorithm.
    2. **Cross-category evidence pass**: collapses surviving clusters
       that share the same ``url`` + ``evidence`` prefix (first 80 chars,
       normalised). Fires when the agent split one observable phenomenon
       across multiple categories (`missing` + `other` + `confusion`)
       because the description phrasing varied, even though the DOM
       evidence is identical. Symptom from cycle 120 ops_dashboard run.

    The first entry in each group becomes canonical and gets a
    ``similar_count`` field; the rest are dropped from the rendered
    report. Raw JSON transcripts still include every entry.
    """
    # Pass 1 — same-category, description-similarity clustering.
    clusters: list[dict[str, Any]] = []
    for entry in items:
        category = entry.get("category", "other")
        url = (entry.get("url") or "").strip()
        description = (entry.get("description") or "").strip().lower()

        matched = False
        for canonical in clusters:
            if canonical.get("category") != category:
                continue
            if (canonical.get("url") or "").strip() != url:
                continue
            canonical_desc = (canonical.get("description") or "").strip().lower()
            ratio = SequenceMatcher(None, canonical_desc, description).ratio()
            if ratio >= _CLUSTER_SIMILARITY_THRESHOLD:
                canonical["similar_count"] = canonical.get("similar_count", 1) + 1
                matched = True
                break

        if not matched:
            clusters.append(dict(entry))

    # Pass 2 — cross-category collapse keyed on (url, evidence prefix).
    # Evidence is the DOM excerpt the agent attached; identical evidence
    # means identical observation regardless of category framing.
    if not clusters:
        return clusters

    def _evidence_key(entry: dict[str, Any]) -> tuple[str, str]:
        url = (entry.get("url") or "").strip()
        evidence = (entry.get("evidence") or "").strip().lower()
        return (url, evidence[:_EVIDENCE_PREFIX_LEN])

    collapsed: list[dict[str, Any]] = []
    for canonical in clusters:
        key = _evidence_key(canonical)
        # An entry with empty url or evidence has no cross-category dedup
        # signal — pass it through unmolested.
        if not key[0] or not key[1]:
            collapsed.append(canonical)
            continue
        matched = False
        for prior in collapsed:
            if _evidence_key(prior) == key:
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
        for para in report.verdict.strip().split("\n\n"):
            lines.append(f"> {para.strip()}")
        lines.append("")
    else:
        lines.append("## Verdict")
        lines.append("")
        lines.append("*(no verdict recorded — run ended before `done`)*")
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
    )
