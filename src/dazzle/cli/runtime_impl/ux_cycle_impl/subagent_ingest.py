"""Backlog ingestion for subagent-driven explore runs.

Automates Step 9 of the ``/ux-cycle`` Step 6 EXPLORE playbook: translate
one or more persona-runs' ``findings.json`` into ``PROP-NNN`` +
``EX-NNN`` rows appended to ``dev_docs/ux-backlog.md``.

The playbook used to do this by hand — inspect the findings, grep the
backlog for the highest existing ``PROP-NNN`` / ``EX-NNN``, write each
row manually, and dedupe. Cycles 198 and 199 proved the process works
but wastes assistant tokens on bookkeeping that's fully mechanical.

Responsibilities:
    1. Parse the backlog's existing ``PROP-`` / ``EX-`` IDs so new rows
       pick up the next free number.
    2. Dedup proposals by ``component_name`` against the existing
       "Proposed Components" table — a proposal already in the backlog
       (regardless of status) is skipped with a warning.
    3. Format a markdown table row matching the cycle 198/199 schema.
    4. Insert the new rows after the last existing data row in each
       table, preserving everything else in the file byte-for-byte.
    5. Return an ``IngestionResult`` so the caller knows what changed.

What this module does NOT do:
    - Does not write the ``ux-log.md`` narrative entry. The log entry
      is interpretive prose — manual narration stays more faithful to
      the cycle's actual shape than an auto-generated summary.
    - Does not commit. The caller decides when to stage and commit.
    - Does not touch the source ``findings.json`` files. Those are
      local-only, gitignored, and the durable record for diagnostics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dazzle.cli.runtime_impl.ux_cycle_impl.subagent_explore import (
    SubagentExploreFindings,
)

_PROP_ID_RE = re.compile(r"\|\s*PROP-(\d+)\s*\|")
_EX_ID_RE = re.compile(r"\|\s*EX-(\d+)\s*\|")
_PROP_COMPONENT_RE = re.compile(r"\|\s*PROP-\d+\s*\|\s*([a-z][a-z0-9:-]*)\s*\|")
_PROPOSED_COMPONENTS_HEADING = "## Proposed Components"
_EXPLORATION_FINDINGS_HEADING = "## Exploration Findings"


@dataclass
class PersonaRun:
    """One persona-run's findings bundled with the metadata needed to
    attribute rows in the backlog.

    ``cycle_number`` goes in each row's ``source_cycle`` column; ``run_id``
    is embedded in the notes so diagnosticians can correlate back to the
    raw ``findings.json`` on disk.
    """

    persona_id: str
    run_id: str
    findings: SubagentExploreFindings
    example_name: str


@dataclass
class IngestionResult:
    """Summary of what ``ingest_findings`` did."""

    prop_rows_added: int = 0
    ex_rows_added: int = 0
    proposals_skipped_as_duplicates: list[str] = field(default_factory=list)
    starting_prop_id: int = 0
    starting_ex_id: int = 0
    warnings: list[str] = field(default_factory=list)


def _next_prop_id(backlog_text: str) -> int:
    matches = _PROP_ID_RE.findall(backlog_text)
    return (max(int(m) for m in matches) + 1) if matches else 1


def _next_ex_id(backlog_text: str) -> int:
    matches = _EX_ID_RE.findall(backlog_text)
    return (max(int(m) for m in matches) + 1) if matches else 1


def _existing_component_names(backlog_text: str) -> set[str]:
    """Component names already listed in the Proposed Components table.

    Used for deduplication: if a subagent proposes ``kanban-board`` and
    a prior cycle already filed a ``PROP-NNN | kanban-board |`` row, we
    skip the new one instead of filing a duplicate.
    """
    return set(_PROP_COMPONENT_RE.findall(backlog_text))


def _escape_cell(text: str) -> str:
    """Make a string safe for a single markdown table cell.

    Strips newlines (so multi-line descriptions render on one row),
    collapses runs of whitespace, and escapes pipes so the row parser
    doesn't see them as column separators.
    """
    # Collapse newlines + runs of whitespace to single spaces
    single_line = " ".join(text.split())
    return single_line.replace("|", r"\|")


def _format_prop_row(
    *,
    prop_id: int,
    proposal: dict[str, Any],
    cycle_number: int,
    persona_id: str,
    run_id: str,
    example_name: str,
) -> str:
    component = _escape_cell(str(proposal.get("component_name", "<unknown>")))
    description = _escape_cell(str(proposal.get("description", "")))
    observed_on = str(proposal.get("observed_on_page", ""))
    selector = str(proposal.get("selector_hint", ""))

    # Notes include everything a later reader needs to trace the row back
    # to the raw finding: cycle number, persona+run, observed page,
    # selector hint.
    note_parts = [
        f"Cycle {cycle_number} — {example_name}/{persona_id} run {run_id}.",
    ]
    if observed_on:
        note_parts.append(f"Observed on `{observed_on}`.")
    if selector:
        note_parts.append(f"Selector: `{selector}`.")
    notes = _escape_cell(" ".join(note_parts))

    return (
        f"| PROP-{prop_id:03d} | {component} | {description} | PROPOSED "
        f"| {cycle_number} | {notes} |"
    )


def _format_ex_row(
    *,
    ex_id: int,
    observation: dict[str, Any],
    cycle_number: int,
    persona_id: str,
    run_id: str,
    example_name: str,
) -> str:
    severity = str(observation.get("severity", "minor"))
    page = str(observation.get("page", ""))
    note_text = _escape_cell(str(observation.get("note", "")))

    description_parts: list[str] = []
    if page:
        description_parts.append(f"`{page}`:")
    description_parts.append(note_text)
    description = _escape_cell(" ".join(description_parts))

    notes = _escape_cell(
        f"Cycle {cycle_number} — {example_name}/{persona_id} run {run_id}, severity={severity}."
    )

    return (
        f"| EX-{ex_id:03d} | edge-case-observation | {description} | OPEN "
        f"| {cycle_number} | {notes} |"
    )


def _insert_rows_after_table(
    backlog_lines: list[str],
    heading: str,
    id_prefix: str,
    new_rows: list[str],
) -> list[str]:
    """Insert ``new_rows`` after the last data row of the table under ``heading``.

    Matches the heading line, then scans forward to find the last line
    matching ``| <id_prefix>-NNN |``. New rows are inserted immediately
    after that line. If no existing data row is found (empty table), the
    rows are inserted after the table's separator line (the one with
    ``|---|---|`` pipes).

    Raises:
        ValueError: if the heading isn't found in the file.
    """
    if not new_rows:
        return backlog_lines

    heading_idx = next(
        (i for i, line in enumerate(backlog_lines) if line.strip() == heading),
        None,
    )
    if heading_idx is None:
        raise ValueError(f"heading {heading!r} not found in backlog")

    # Scan forward from heading for the last row matching id_prefix.
    # Stop if we hit the next ## heading (end of table section).
    last_data_row_idx: int | None = None
    separator_idx: int | None = None
    pattern = re.compile(rf"\|\s*{re.escape(id_prefix)}-\d+\s*\|")
    for i in range(heading_idx + 1, len(backlog_lines)):
        line = backlog_lines[i]
        if line.startswith("## "):
            break  # left this section
        if separator_idx is None and re.match(r"\|[-:\s|]+\|\s*$", line):
            separator_idx = i
        if pattern.search(line):
            last_data_row_idx = i

    insertion_idx: int
    if last_data_row_idx is not None:
        insertion_idx = last_data_row_idx + 1
    elif separator_idx is not None:
        insertion_idx = separator_idx + 1
    else:
        raise ValueError(
            f"could not locate table under {heading!r} (no separator or existing rows)"
        )

    return backlog_lines[:insertion_idx] + new_rows + backlog_lines[insertion_idx:]


def ingest_findings(
    backlog_path: Path,
    cycle_number: int,
    runs: list[PersonaRun],
) -> IngestionResult:
    """Append PROP + EX rows from ``runs`` into ``backlog_path``.

    Writes ``backlog_path`` in place only if at least one row was added.
    Dedups proposals against the existing "Proposed Components" table by
    ``component_name``. Does NOT dedup observations — edge-case findings
    are inherently per-run and per-persona.
    """
    text = backlog_path.read_text()
    lines = text.splitlines(keepends=True)

    next_prop = _next_prop_id(text)
    next_ex = _next_ex_id(text)
    existing_names = _existing_component_names(text)

    result = IngestionResult(
        starting_prop_id=next_prop,
        starting_ex_id=next_ex,
    )

    prop_rows: list[str] = []
    for run in runs:
        for proposal in run.findings.proposals:
            component = str(proposal.get("component_name", "")).strip()
            if not component:
                result.warnings.append(
                    f"run {run.persona_id}/{run.run_id}: dropping proposal with no component_name"
                )
                continue
            if component in existing_names:
                result.proposals_skipped_as_duplicates.append(component)
                continue
            existing_names.add(component)
            prop_rows.append(
                _format_prop_row(
                    prop_id=next_prop,
                    proposal=proposal,
                    cycle_number=cycle_number,
                    persona_id=run.persona_id,
                    run_id=run.run_id,
                    example_name=run.example_name,
                )
                + "\n"
            )
            next_prop += 1

    ex_rows: list[str] = []
    for run in runs:
        for observation in run.findings.observations:
            ex_rows.append(
                _format_ex_row(
                    ex_id=next_ex,
                    observation=observation,
                    cycle_number=cycle_number,
                    persona_id=run.persona_id,
                    run_id=run.run_id,
                    example_name=run.example_name,
                )
                + "\n"
            )
            next_ex += 1

    if not prop_rows and not ex_rows:
        return result

    updated = lines
    if prop_rows:
        updated = _insert_rows_after_table(updated, _PROPOSED_COMPONENTS_HEADING, "PROP", prop_rows)
    if ex_rows:
        updated = _insert_rows_after_table(updated, _EXPLORATION_FINDINGS_HEADING, "EX", ex_rows)

    backlog_path.write_text("".join(updated))
    result.prop_rows_added = len(prop_rows)
    result.ex_rows_added = len(ex_rows)
    return result
