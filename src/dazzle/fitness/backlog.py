"""Fitness backlog reader/writer (v1 task 15).

Durable storage for findings. The layout is a human-friendly markdown
table (one row per finding) followed by a JSON evidence envelope for
each finding — git-diff-friendly, but still machine-parseable because
each row is self-contained via ``evidence_embedded``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from dazzle.fitness.models import Finding

_HEADER = """# Fitness Backlog

Structured findings from the Agent-Led Fitness Methodology. Each row is
self-contained via `evidence_embedded` — durable after the underlying ledger
has expired.

| id | created | locus | axis | severity | persona | status | route | summary |
|----|---------|-------|------|----------|---------|--------|-------|---------|
"""

_EVIDENCE_HEADER = "\n## Evidence envelopes\n\n"


_ROW_RE = re.compile(
    r"^\| (?P<id>FIND-\w+) \| (?P<created>[^|]+) \| (?P<locus>[^|]+) \|"
    r" (?P<axis>[^|]+) \| (?P<severity>[^|]+) \| (?P<persona>[^|]+) \|"
    r" (?P<status>[^|]+) \| (?P<route>[^|]+) \| (?P<summary>[^|]*) \|$"
)


def _finding_to_row(f: Finding) -> str:
    summary = f.observed.replace("\n", " ").replace("|", "/")[:120]
    return (
        f"| {f.id} | {f.created.isoformat()} | {f.locus} | {f.axis} |"
        f" {f.severity} | {f.persona} | {f.status} | {f.route} | {summary} |"
    )


def _finding_envelope(f: Finding) -> str:
    def _default(obj: object) -> object:
        if is_dataclass(obj) and not isinstance(obj, type):
            return asdict(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, tuple):
            return list(obj)
        raise TypeError(f"cannot serialise {type(obj)!r}")

    # asdict() recurses through dataclasses but leaves tuples as tuples
    # and datetimes as datetimes — _default handles both.
    payload = json.dumps(asdict(f), default=_default, indent=2)
    return f"### {f.id}\n\n```json\n{payload}\n```\n"


def read_backlog(path: Path) -> list[dict[str, str]]:
    """Parse the table section of the backlog file into plain dicts."""
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text().splitlines():
        m = _ROW_RE.match(line.strip())
        if m:
            rows.append({k: v.strip() for k, v in m.groupdict().items()})
    return rows


def upsert_findings(path: Path, findings: list[Finding]) -> None:
    """Append any findings whose id is not already in the backlog."""
    existing = read_backlog(path)
    existing_ids = {r["id"] for r in existing}

    to_add = [f for f in findings if f.id not in existing_ids]
    if not to_add and path.exists():
        return

    if not path.exists():
        path.write_text(_HEADER)

    text = path.read_text()
    # Split into table + envelope sections
    if _EVIDENCE_HEADER.strip() in text:
        table_part, envelope_part = text.split(_EVIDENCE_HEADER, 1)
        envelope_part = _EVIDENCE_HEADER + envelope_part
    else:
        table_part = text
        envelope_part = _EVIDENCE_HEADER

    for f in to_add:
        table_part = table_part.rstrip("\n") + "\n" + _finding_to_row(f) + "\n"
        envelope_part = envelope_part.rstrip("\n") + "\n\n" + _finding_envelope(f)

    path.write_text(table_part + "\n" + envelope_part.lstrip("\n"))
