#!/usr/bin/env python3
"""Compact /improve state files by archiving settled rows and old cycles.

The /improve driver reads dev_docs/improve-backlog.md and dev_docs/improve-log.md
on EVERY cycle. Settled backlog rows (DONE/VERIFIED/CLEAN/RESOLVED...) and old
cycle logs are pure context burn — the driver only needs actionable rows and
recent history. This script moves the settled material to sibling archive files:

  dev_docs/improve-backlog-archive.md
  dev_docs/improve-log-archive.md

Rules:
- Backlog: per-lane archive-status sets (see ARCHIVE_STATUSES). The status column
  is located by table-header name, per table — lanes have different table shapes.
  Any row whose cell count doesn't match its header is KEPT (fail-safe: never
  archive on ambiguity). Lanes not listed in ARCHIVE_STATUSES are never touched.
- Log: keep the most recent KEEP_CYCLES `## Cycle` blocks; archive the rest.
- Idempotent: a second run is a no-op.

Usage: python scripts/improve_compact.py [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
from pathlib import Path

BACKLOG = Path("dev_docs/improve-backlog.md")
LOG = Path("dev_docs/improve-log.md")
BACKLOG_ARCHIVE = Path("dev_docs/improve-backlog-archive.md")
LOG_ARCHIVE = Path("dev_docs/improve-log-archive.md")

KEEP_CYCLES = 25

# Per-lane status values that mean "settled — safe to archive". Statuses that
# retain institutional memory the lane still consults (BLOCKED, FILED→#NNN,
# OPEN_*) are deliberately absent: they stay in the working file. Matching is
# on the status cell's leading UPPER_CASE token, so suffixed terminal states
# ("RESOLVED→#1378(v0.82.41)", "RESOLVED (this cycle)") archive too.
ARCHIVE_STATUSES: dict[str, set[str]] = {
    "framework-ux": {"DONE", "VERIFIED", "FIXED_LOCALLY", "VERIFIED_FALSE_POSITIVE"},
    "example-apps": {"DONE"},
    "trials": {
        "RESOLVED",
        "RESOLVED-VERIFIED",
        "RESOLVED-FALSE-POSITIVE",
        "NOTED",
        "LIKELY_RESOLVED",
    },
    "ux-converge": {"CLEAN"},
    # test-suite lane: collapsed cluster rows are settled once shipped.
    "test-suite": {"DONE"},
}

LANE_RE = re.compile(r"^## Lane: (.+?)\s*$")
SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|\s*$")
STATUS_TOKEN_RE = re.compile(r"[A-Z][A-Z_\-]*")


def _cells(line: str) -> list[str]:
    # Notes cells legitimately contain escaped pipes (`str \| None`) — split
    # only on unescaped ones or column counts drift and rows are never archived.
    return [c.strip() for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def _status_token(cell: str) -> str:
    m = STATUS_TOKEN_RE.match(cell)
    return (m.group(0) if m else cell).rstrip("-")


FILED_RE = re.compile(r"FILED→#(\d+)")


def closed_filed_issues(text: str) -> set[int]:
    """Return the FILED→#N issue numbers that are verifiably CLOSED on GitHub.

    A FILED row is settled once its issue closes (the fix shipped; fix-deployed
    re-verification is signal-driven, not row-driven). Best-effort: any gh
    failure means the issue is treated as open and the row is kept.
    """
    numbers = {int(n) for n in FILED_RE.findall(text)}
    closed: set[int] = set()
    for n in sorted(numbers):
        try:
            out = subprocess.run(
                ["gh", "issue", "view", str(n), "--json", "state"],
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            if json.loads(out.stdout).get("state") == "CLOSED":
                closed.add(n)
        except Exception:
            continue
    return closed


def compact_backlog(text: str, closed_issues: set[int]) -> tuple[str, dict[str, list[str]]]:
    """Return (new_backlog_text, {lane: archived_row_lines})."""
    lines = text.splitlines()
    kept: list[str] = []
    archived: dict[str, list[str]] = {}

    lane: str | None = None
    # Sections accrete multiple tables over time (work tables, summary tables,
    # observation tables), and appended rows sometimes land after an unrelated
    # table. Track every header seen in the lane; a data row is interpreted
    # against the most recent header with a MATCHING column count. No match →
    # row is kept (fail-safe).
    headers: list[tuple[list[str], int | None, str, str]] = []

    for i, line in enumerate(lines):
        m = LANE_RE.match(line)
        if m:
            lane = m.group(1)
            headers = []
            kept.append(line)
            continue

        is_table_row = line.lstrip().startswith("|")
        if is_table_row and SEPARATOR_RE.match(line.strip()):
            kept.append(line)
            continue
        if is_table_row:
            next_is_sep = i + 1 < len(lines) and SEPARATOR_RE.match(lines[i + 1].strip())
            if next_is_sep:
                # Header row: locate the status column for the table that follows.
                header_cells = _cells(line)
                status_idx = next(
                    (
                        j
                        for j, c in enumerate(header_cells)
                        if c.lower().lstrip("*").rstrip("*") == "status"
                    ),
                    None,
                )
                headers.append((header_cells, status_idx, line, lines[i + 1]))
                kept.append(line)
                continue
            # Data row.
            statuses = ARCHIVE_STATUSES.get(lane or "", set())
            if statuses:
                row_cells = _cells(line)
                # Exact column-count match wins. Failing that, accept a row with
                # SURPLUS cells if the header's status column isn't last — raw
                # pipes inside a trailing notes cell inflate the count without
                # shifting the status index. (Status-last tables, e.g. trials,
                # still require an exact match — fail-safe.)
                match = next(
                    (
                        h
                        for h in reversed(headers)
                        if len(h[0]) == len(row_cells) and h[1] is not None
                    ),
                    None,
                ) or next(
                    (
                        h
                        for h in reversed(headers)
                        if h[1] is not None and h[1] < len(h[0]) - 1 and len(row_cells) > len(h[0])
                    ),
                    None,
                )
                if match is not None:
                    _, status_idx, header_line, separator_line = match
                    assert status_idx is not None
                    status_cell = row_cells[status_idx]
                    status = _status_token(status_cell)
                    filed = FILED_RE.match(status_cell)
                    settled = status in statuses or (
                        filed is not None and int(filed.group(1)) in closed_issues
                    )
                    if settled:
                        bucket = archived.setdefault(lane or "?", [])
                        if not bucket:
                            bucket.append(header_line)
                            bucket.append(separator_line)
                        bucket.append(line)
                        continue
            kept.append(line)
            continue

        kept.append(line)

    return "\n".join(kept) + "\n", archived


def compact_log(text: str) -> tuple[str, str]:
    """Return (new_log_text, archived_text). Keeps the last KEEP_CYCLES blocks."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("## Cycle")]
    if len(starts) <= KEEP_CYCLES:
        return text, ""
    cut = starts[-KEEP_CYCLES]
    preamble_end = starts[0]
    kept = lines[:preamble_end] + lines[cut:]
    archived = lines[preamble_end:cut]
    return "\n".join(kept) + "\n", "\n".join(archived) + "\n"


def _append(path: Path, title: str, body: str) -> None:
    stamp = f"\n# {title} — archived {datetime.date.today().isoformat()}\n\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(existing + stamp + body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total_rows = 0
    if BACKLOG.exists():
        backlog_text = BACKLOG.read_text(encoding="utf-8")
        new_backlog, archived_rows = compact_backlog(
            backlog_text, closed_filed_issues(backlog_text)
        )
        total_rows = sum(len(v) - 2 for v in archived_rows.values())  # minus header+sep
        if total_rows and not args.dry_run:
            body = ""
            for lane_name, rows in archived_rows.items():
                body += f"## Lane: {lane_name}\n\n" + "\n".join(rows) + "\n\n"
            _append(BACKLOG_ARCHIVE, "Backlog rows", body)
            BACKLOG.write_text(new_backlog, encoding="utf-8")
        for lane_name, rows in archived_rows.items():
            print(f"backlog[{lane_name}]: archived {len(rows) - 2} rows")

    archived_cycles = 0
    if LOG.exists():
        new_log, archived_log = compact_log(LOG.read_text(encoding="utf-8"))
        archived_cycles = archived_log.count("## Cycle")
        if archived_log and not args.dry_run:
            _append(LOG_ARCHIVE, "Cycle log", archived_log)
            LOG.write_text(new_log, encoding="utf-8")

    mode = "DRY-RUN: would archive" if args.dry_run else "archived"
    print(f"{mode} {total_rows} backlog rows, {archived_cycles} log cycles")
    print(
        f"backlog: {BACKLOG.stat().st_size if BACKLOG.exists() else 0} bytes; log: {LOG.stat().st_size if LOG.exists() else 0} bytes"
    )


if __name__ == "__main__":
    main()
