"""Rebuildable idempotence cache for the investigator.

.dazzle/fitness-proposals/_attempted.json tracks which clusters have been
investigated. It is a write-through cache, not an authoritative store — if
deleted or corrupt, load_attempted rebuilds from the proposal files on disk.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from dazzle.fitness.investigator.proposal import (
    ProposalParseError,
    ProposalStatus,
    load_proposal,
)

AttemptStatus = ProposalStatus | Literal["blocked"]


@dataclass
class AttemptedEntry:
    proposal_ids: list[str] = field(default_factory=list)
    last_attempt: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: AttemptStatus = "proposed"


@dataclass
class AttemptedIndex:
    clusters: dict[str, AttemptedEntry] = field(default_factory=dict)


def _index_path(dazzle_root: Path) -> Path:
    return dazzle_root / ".dazzle" / "fitness-proposals" / "_attempted.json"


def load_attempted(dazzle_root: Path) -> AttemptedIndex:
    """Load the index; rebuild from disk if missing or corrupt."""
    path = _index_path(dazzle_root)
    if not path.exists():
        return rebuild_attempted(dazzle_root)
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return rebuild_attempted(dazzle_root)
    if not isinstance(raw, dict):
        return rebuild_attempted(dazzle_root)
    return _deserialise(raw)


def save_attempted(index: AttemptedIndex, dazzle_root: Path) -> None:
    """Atomic write via tempfile + rename."""
    path = _index_path(dazzle_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _serialise(index)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False, suffix=".tmp") as tf:
        json.dump(data, tf, indent=2, sort_keys=True)
        tmp_name = tf.name
    Path(tmp_name).replace(path)


def rebuild_attempted(dazzle_root: Path) -> AttemptedIndex:
    """Scan .dazzle/fitness-proposals/ and _blocked/ to reconstruct the index."""
    index = AttemptedIndex(clusters={})
    proposals_dir = dazzle_root / ".dazzle" / "fitness-proposals"
    if not proposals_dir.exists():
        return index

    # Top-level proposal files
    for path in sorted(proposals_dir.glob("CL-*.md")):
        try:
            proposal = load_proposal(path)
        except ProposalParseError:
            continue
        entry = index.clusters.setdefault(
            proposal.cluster_id,
            AttemptedEntry(last_attempt=proposal.created),
        )
        entry.proposal_ids.append(proposal.proposal_id)
        if proposal.created > entry.last_attempt:
            entry.last_attempt = proposal.created
        entry.status = proposal.status

    # Blocked artefacts — only mark blocked if no successful proposal exists
    blocked_dir = proposals_dir / "_blocked"
    if blocked_dir.exists():
        for path in sorted(blocked_dir.glob("CL-*.md")):
            cluster_id = path.stem
            entry = index.clusters.setdefault(cluster_id, AttemptedEntry())
            if not entry.proposal_ids:
                entry.status = "blocked"
                entry.last_attempt = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)

    return index


def mark_attempted(
    index: AttemptedIndex,
    cluster_id: str,
    *,
    proposal_id: str | None,
    status: AttemptStatus,
) -> None:
    """Update an entry in-place. Caller is responsible for calling save_attempted."""
    entry = index.clusters.setdefault(cluster_id, AttemptedEntry())
    if proposal_id is not None and proposal_id not in entry.proposal_ids:
        entry.proposal_ids.append(proposal_id)
    entry.last_attempt = datetime.now(UTC)
    entry.status = status


def _serialise(index: AttemptedIndex) -> dict[str, dict[str, object]]:
    return {
        cluster_id: {
            "proposal_ids": entry.proposal_ids,
            "last_attempt": entry.last_attempt.isoformat(),
            "status": entry.status,
        }
        for cluster_id, entry in index.clusters.items()
    }


def _deserialise(raw: dict[str, object]) -> AttemptedIndex:
    index = AttemptedIndex(clusters={})
    for cluster_id, data in raw.items():
        if not isinstance(data, dict):
            continue
        try:
            index.clusters[cluster_id] = AttemptedEntry(
                proposal_ids=list(data.get("proposal_ids") or []),
                last_attempt=datetime.fromisoformat(str(data["last_attempt"])),
                status=data["status"],
            )
        except (KeyError, ValueError, TypeError):
            continue
    return index
