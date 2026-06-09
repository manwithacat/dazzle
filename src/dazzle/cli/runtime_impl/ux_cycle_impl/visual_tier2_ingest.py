"""Backlog ingestion for Tier 2 visual-QA subagent runs.

Sibling to :mod:`subagent_ingest` (framework-ux's PROP/EX rows). This
module owns the example-apps lane's ``visual_quality`` rows: parses a
subagent ``findings.json`` (the JSON the CC subagent writes during the
``visual_tier2_subagent`` strategy), allocates numeric row IDs, dedups
against existing rows, sorts by severity (high → medium → low), and
appends rows to the ``## Lane: example-apps`` section of
``dev_docs/improve-backlog.md``.

The lane's normal OBSERVE → ENHANCE → BUILD → VERIFY cycle then drains
the rows one per cycle. Dedup means re-runs of the same drift reinforce
an existing row (``seen=K`` increments) instead of cloning it.

Why this lives in ``ux_cycle_impl`` alongside ``subagent_ingest``: same
substrate (CC subagent), same lifecycle (called by an `/improve` lane
playbook after the subagent finishes), same backlog file. Keeping the
two ingest helpers next to each other makes the patterns easy to
compare and evolve.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

_LANE_HEADING = "## Lane: example-apps"
_LANE_END_SENTINEL = re.compile(r"^---\s*$")
_LANE_NEXT_HEADING = re.compile(r"^## Lane: ")
# Numeric row IDs in the example-apps section: `| 1 | ...`, `| 100 | ...`
_NUMERIC_ROW_ID_RE = re.compile(r"^\|\s*(\d+)\s*\|", re.MULTILINE)

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# Content-signature stopwords. The Tier 2 subagent re-words the same
# finding across runs ("Metrics and Team Metrics sections" vs "Metrics
# and Team Metrics regions (top of page)"). Stripping these high-
# frequency words from the token bag means we dedup on the semantic
# content rather than the framing — see #1080 for the failure that
# motivated this.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "card",
        "cards",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "no",
        "not",
        "of",
        "on",
        "or",
        "page",
        "region",
        "regions",
        "section",
        "sections",
        "the",
        "this",
        "to",
        "top",
        "bottom",
        "was",
        "were",
        "with",
        "without",
    }
)
_TOKEN_RE = re.compile(r"[a-z0-9_]{2,}")
# Jaccard threshold above which two content signatures are considered the
# same finding. Tuned against cycle 144 data: the LLM frequently rewords
# the same drift with substantially different surface vocab ("cards"
# vs "regions", "empty" vs "blank"), so the threshold is set low (0.3).
# The (app, category) filter applied upstream prevents cross-class
# look-alikes from colliding even when the body words overlap.
_DUP_JACCARD_THRESHOLD = 0.3


@dataclass(frozen=True)
class _DedupKey:
    """Identifies a finding for dedup against existing rows.

    Location is truncated to mirror what humans use when scanning rows —
    the full location text often contains a coordinate or timestamp that
    differs across captures of the same drift.
    """

    app: str
    category: str
    location_prefix: str  # location[:60].lower()


def _content_signature(text: str) -> frozenset[str]:
    """Lowercase, stopword-strip, tokenise. Used as a fuzzy-match key
    when the exact ``(app, category, location_prefix)`` key misses."""
    tokens = _TOKEN_RE.findall(text.lower())
    return frozenset(t for t in tokens if t not in _STOPWORDS and len(t) > 2)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class VisualTier2IngestResult:
    """Summary of what :func:`ingest_visual_findings` did."""

    rows_added: int = 0
    rows_reinforced: int = 0  # existing row's ``seen=K`` bumped
    starting_row_id: int = 0
    warnings: list[str] = field(default_factory=list)


def _next_row_id(section_text: str) -> int:
    """Highest numeric row ID in the example-apps section, plus 1."""
    matches = _NUMERIC_ROW_ID_RE.findall(section_text)
    return (max(int(m) for m in matches) + 1) if matches else 1


def _existing_dedup_keys(section_text: str) -> set[_DedupKey]:
    """Build dedup keys from existing rows.

    Row shape: ``| <id> | <app> | <gap_type> | <description> | <status> | ...``
    The visual_quality rows we write embed the category as a leading
    bracket tag in the description column (``[<category>] <desc> at <location>``).
    """
    keys: set[_DedupKey] = set()
    for line in section_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        # cells[0] is empty from the leading pipe; data starts at index 1.
        if len(cells) < 5:
            continue
        # Match only visual_quality rows so we don't accidentally dedup
        # against unrelated rows that happen to start with `[`.
        if cells[3] != "visual_quality":
            continue
        app = cells[2]
        description = cells[4]
        match = re.match(r"^\[([a-z_]+)\]\s*(.*?)\s+at\s+(.+)$", description)
        if not match:
            continue
        category = match.group(1)
        location = match.group(3)
        keys.add(_DedupKey(app=app, category=category, location_prefix=location[:60].lower()))
    return keys


def _existing_signatures(section_text: str) -> list[tuple[_DedupKey, frozenset[str]]]:
    """Build (dedup_key, content_signature) pairs for every visual_quality
    row. Used by the fuzzy-match second pass when the exact key misses —
    see #1080."""
    sigs: list[tuple[_DedupKey, frozenset[str]]] = []
    for line in section_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 5 or cells[3] != "visual_quality":
            continue
        app = cells[2]
        description = cells[4]
        match = re.match(r"^\[([a-z_]+)\]\s*(.*?)\s+at\s+(.+)$", description)
        if not match:
            continue
        category = match.group(1)
        body = match.group(2)
        location = match.group(3)
        key = _DedupKey(app=app, category=category, location_prefix=location[:60].lower())
        sig = _content_signature(f"{body} {location}")
        sigs.append((key, sig))
    return sigs


def _find_fuzzy_match(
    sigs: list[tuple[_DedupKey, frozenset[str]]],
    app: str,
    category: str,
    finding_sig: frozenset[str],
) -> _DedupKey | None:
    """Return the dedup key of the existing visual_quality row whose content
    signature has the highest Jaccard overlap with *finding_sig* — but only
    if the overlap clears :data:`_DUP_JACCARD_THRESHOLD` and the row's app +
    category match the finding's. Categories are constrained so cross-class
    look-alikes (e.g. an `alignment` row and an `empty_state` row that share
    body words like "region" / "blank") don't collide."""
    best_score = 0.0
    best_key: _DedupKey | None = None
    for key, sig in sigs:
        if key.app != app or key.category != category:
            continue
        score = _jaccard(finding_sig, sig)
        if score > best_score:
            best_score = score
            best_key = key
    return best_key if best_score >= _DUP_JACCARD_THRESHOLD else None


def _split_backlog_around_lane(backlog_text: str) -> tuple[str, str, str]:
    """Split into (before_lane, lane_section, after_lane).

    The lane section runs from its ``## Lane: example-apps`` heading
    through the *trailing* ``---`` separator that closes the section
    (the one followed by ``## Lane: trials``). If no such separator is
    found we fall back to the next ``## Lane:`` heading.

    Returns three substrings whose concatenation equals *backlog_text*.
    """
    lines = backlog_text.splitlines(keepends=True)
    lane_start: int | None = None
    lane_end: int | None = None
    for i, line in enumerate(lines):
        if line.startswith(_LANE_HEADING):
            lane_start = i
            continue
        if (
            lane_start is not None
            and _LANE_NEXT_HEADING.match(line)
            and not line.startswith(_LANE_HEADING)
        ):
            # The lane section ended somewhere before this heading. The
            # actual end is the last `---` separator that appears
            # *between* the lane heading and this next heading.
            for j in range(i - 1, lane_start, -1):
                if _LANE_END_SENTINEL.match(lines[j].rstrip("\n")):
                    lane_end = j
                    break
            else:
                lane_end = i
            break
    if lane_start is None:
        raise ValueError(f"Could not find '{_LANE_HEADING}' in backlog")
    if lane_end is None:
        # No following lane heading — section runs to EOF.
        lane_end = len(lines)
    before = "".join(lines[:lane_start])
    section = "".join(lines[lane_start:lane_end])
    after = "".join(lines[lane_end:])
    return before, section, after


def _format_row(
    row_id: int,
    app: str,
    finding: dict[str, str],
    screenshot_path: str,
    timestamp: str,
) -> str:
    description = f"[{finding['category']}] {finding['description']} at {finding['location']}"
    notes = f"seen=1, screenshot={screenshot_path}, ts={timestamp}"
    return f"| {row_id} | {app} | visual_quality | {description} | PENDING | 0 | {notes} |\n"


def _reinforce_existing_row(section: str, key: _DedupKey) -> tuple[str, bool]:
    """If a row matching *key* exists, increment its ``seen=K`` counter.

    Returns the (possibly updated) section text and True if a row was
    reinforced.
    """
    seen_re = re.compile(r"seen=(\d+)")
    out_lines: list[str] = []
    reinforced = False
    for line in section.splitlines(keepends=True):
        if reinforced or not line.startswith("|"):
            out_lines.append(line)
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 5 or cells[3] != "visual_quality":
            out_lines.append(line)
            continue
        app = cells[2]
        description = cells[4]
        match = re.match(r"^\[([a-z_]+)\]\s*(.*?)\s+at\s+(.+)$", description)
        if not match:
            out_lines.append(line)
            continue
        if (
            app == key.app
            and match.group(1) == key.category
            and match.group(3)[:60].lower() == key.location_prefix
        ):
            line = seen_re.sub(
                lambda m: f"seen={int(m.group(1)) + 1}",
                line,
                count=1,
            )
            reinforced = True
        out_lines.append(line)
    return "".join(out_lines), reinforced


def ingest_visual_findings(
    findings_path: Path,
    manifest_path: Path,
    backlog_path: Path,
) -> VisualTier2IngestResult:
    """Ingest one Tier 2 subagent run's findings into the backlog.

    Args:
        findings_path: JSON file the subagent wrote. Schema: list of
            objects with keys ``app``, ``category``, ``severity``,
            ``location``, ``description``, ``suggestion``.
        manifest_path: The capture manifest the subagent evaluated.
            Used to look up the source screenshot path for each finding.
        backlog_path: ``dev_docs/improve-backlog.md`` (mutated in place).

    Returns:
        :class:`VisualTier2IngestResult` summarising rows added /
        reinforced and any warnings.
    """
    result = VisualTier2IngestResult()
    raw_findings = json.loads(findings_path.read_text(encoding="utf-8"))
    if not isinstance(raw_findings, list):
        result.warnings.append(
            f"findings file {findings_path} did not contain a JSON array — skipping"
        )
        return result

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Build screenshot lookup keyed by (app, persona, workspace).
    screenshot_index: dict[tuple[str, str, str], str] = {}
    for app_entry in manifest.get("apps", []):
        app = app_entry.get("app", "")
        for s in app_entry.get("screens", []):
            screenshot_index[(app, s.get("persona", ""), s.get("workspace", ""))] = s.get(
                "screenshot", ""
            )

    # Sort findings by severity (high first), then app for stable order.
    raw_findings.sort(
        key=lambda f: (
            _SEVERITY_ORDER.get(str(f.get("severity", "low")).lower(), 99),
            str(f.get("app", "")),
            str(f.get("category", "")),
        )
    )

    backlog_text = backlog_path.read_text(encoding="utf-8")
    before, section, after = _split_backlog_around_lane(backlog_text)

    next_id = _next_row_id(section)
    result.starting_row_id = next_id

    existing_keys = _existing_dedup_keys(section)
    existing_signatures = _existing_signatures(section)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_rows: list[str] = []
    for f in raw_findings:
        app = str(f.get("app", "")) or "unknown"
        category = str(f.get("category", ""))
        location = str(f.get("location", ""))
        if not category or not location:
            result.warnings.append(f"skipping finding with missing category/location: {f!r}")
            continue
        key = _DedupKey(app=app, category=category, location_prefix=location[:60].lower())
        if key in existing_keys:
            section, did_reinforce = _reinforce_existing_row(section, key)
            if did_reinforce:
                result.rows_reinforced += 1
            continue
        # Fuzzy second-pass (#1080): same finding restated with different
        # wording across runs. Match on stopword-stripped token-bag Jaccard
        # within (app, category).
        description = str(f.get("description", ""))
        fuzzy_sig = _content_signature(f"{description} {location}")
        fuzzy_match = _find_fuzzy_match(existing_signatures, app, category, fuzzy_sig)
        if fuzzy_match is not None:
            section, did_reinforce = _reinforce_existing_row(section, fuzzy_match)
            if did_reinforce:
                result.rows_reinforced += 1
                continue

        # Prefer the screenshot path the subagent attached to this finding.
        # Fall back to a manifest lookup by (persona, workspace) if present,
        # finally to "first screenshot for the app" so older finding shapes
        # don't lose all context.
        screenshot = str(f.get("screenshot", "") or "")
        if not screenshot:
            persona = str(f.get("persona", ""))
            workspace = str(f.get("workspace", ""))
            screenshot = screenshot_index.get((app, persona, workspace), "")
        if not screenshot:
            for (s_app, _, _), path in screenshot_index.items():
                if s_app == app:
                    screenshot = path
                    break

        new_rows.append(_format_row(next_id, app, f, screenshot, timestamp))
        existing_keys.add(key)
        existing_signatures.append((key, fuzzy_sig))
        next_id += 1

    if not new_rows:
        backlog_path.write_text(before + section + after, encoding="utf-8")
        return result

    # Append new rows. The section ends with a blank line followed by `---\n`
    # (and possibly more blank lines). Insert new rows right before the
    # trailing whitespace + separator.
    section_lines = section.splitlines(keepends=True)
    insert_at = len(section_lines)
    while insert_at > 0:
        candidate = section_lines[insert_at - 1].rstrip("\n")
        if candidate == "" or _LANE_END_SENTINEL.match(candidate):
            insert_at -= 1
            continue
        break
    new_section = (
        "".join(section_lines[:insert_at]) + "".join(new_rows) + "".join(section_lines[insert_at:])
    )
    backlog_path.write_text(before + new_section + after, encoding="utf-8")
    result.rows_added = len(new_rows)
    return result
