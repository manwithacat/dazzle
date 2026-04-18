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

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

_CATEGORY_ORDER = ("bug", "missing", "confusion", "aesthetic", "praise", "other")
_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


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
    friction = _sort_friction(list(report.friction))
    lines.append(f"## Friction observations ({len(friction)})")
    lines.append("")

    if not friction:
        lines.append(
            "*(no friction recorded — the trial either went smoothly or ended "
            "before anything was flagged)*"
        )
        lines.append("")
        return "\n".join(lines)

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

    return "\n".join(lines)


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
) -> TrialReport:
    """Convenience builder — pulls the one-line identity headline
    from the multi-line user_identity block."""
    return TrialReport(
        scenario_name=scenario_name,
        user_identity_headline=_first_line(user_identity),
        verdict=verdict,
        friction=friction,
        step_count=step_count,
        duration_seconds=duration_seconds,
        tokens_used=tokens_used,
        outcome=outcome,
    )
