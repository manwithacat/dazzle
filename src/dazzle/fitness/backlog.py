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
from typing import Any

from dazzle.fitness.models import EvidenceEmbedded, Finding, RowChange

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


_ENVELOPE_BLOCK_RE = re.compile(
    r"^### (?P<id>\S+)\s*\n+```json\n(?P<payload>.*?)\n```",
    re.MULTILINE | re.DOTALL,
)


def read_backlog_findings(path: Path) -> list[Finding]:
    """Parse the envelope blocks in a fitness-backlog.md file into Finding objects.

    Only returns findings whose envelope block contains a valid JSON payload.
    Table-only rows with no matching envelope are ignored — those indicate
    the file was partially written or manually edited and cannot be
    reconstructed losslessly.
    """
    if not path.exists():
        return []

    text = path.read_text()
    findings: list[Finding] = []
    for m in _ENVELOPE_BLOCK_RE.finditer(text):
        try:
            payload = json.loads(m.group("payload"))
            findings.append(_payload_to_finding(payload))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError):
            continue
    return findings


def _reconstruct_row_change(entry: object) -> RowChange:
    """Rebuild a RowChange from a JSON-deserialised dict.

    dataclasses.asdict() converts RowChange.field_deltas tuple values to lists
    during serialisation. This helper restores them back to tuples so the
    dataclass's type contract holds on round-trip.
    """
    if not isinstance(entry, dict):
        raise TypeError(f"expected dict, got {type(entry).__name__}")
    field_deltas = entry.get("field_deltas") or {}
    restored = {k: tuple(v) for k, v in field_deltas.items()}
    return RowChange(
        table=entry["table"],
        row_id=entry["row_id"],
        kind=entry["kind"],
        semantic_repr=entry.get("semantic_repr", ""),
        field_deltas=restored,
    )


def _payload_to_finding(payload: dict[str, object]) -> Finding:
    """Reconstruct a Finding from the JSON envelope payload."""
    # Cast to dict[str, Any] — if ev is not a dict, .get() raises AttributeError which
    # propagates to the caller's except clause and the block is skipped.
    ev: dict[str, Any] = payload["evidence_embedded"]  # type: ignore[assignment]
    evidence = EvidenceEmbedded(
        expected_ledger_step=ev.get("expected_ledger_step") or {},
        diff_summary=[_reconstruct_row_change(e) for e in (ev.get("diff_summary") or [])],
        transcript_excerpt=ev.get("transcript_excerpt") or [],
    )
    # may raise ValueError/TypeError — caller catches
    created = datetime.fromisoformat(payload["created"])  # type: ignore[arg-type]
    return Finding(
        id=str(payload["id"]),
        created=created,
        run_id=str(payload["run_id"]),
        cycle=payload.get("cycle"),  # type: ignore[arg-type]
        axis=payload["axis"],  # type: ignore[arg-type]
        locus=payload["locus"],  # type: ignore[arg-type]
        severity=payload["severity"],  # type: ignore[arg-type]
        persona=str(payload["persona"]),
        capability_ref=str(payload["capability_ref"]),
        expected=str(payload["expected"]),
        observed=str(payload["observed"]),
        evidence_embedded=evidence,
        disambiguation=bool(payload.get("disambiguation", False)),
        low_confidence=bool(payload.get("low_confidence", False)),
        status=payload["status"],  # type: ignore[arg-type]
        route=payload["route"],  # type: ignore[arg-type]
        fix_commit=payload.get("fix_commit"),  # type: ignore[arg-type]
        alternative_fix=payload.get("alternative_fix"),  # type: ignore[arg-type]
    )
