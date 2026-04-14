"""Append-only JSONL metrics sink for investigator runs.

One line per investigation attempt (proposed, blocked, or infrastructure
failure). Lives at .dazzle/fitness-proposals/_metrics.jsonl. Append-only
JSONL means downstream analysis can use `jq` or similar line-oriented
tools without parsing the whole file.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def append_metric(
    dazzle_root: Path,
    *,
    cluster_id: str,
    proposal_id: str | None,
    status: str,
    tokens_in: int,
    tokens_out: int,
    tool_calls: int,
    duration_ms: int,
    model: str,
) -> None:
    """Append one JSONL line to .dazzle/fitness-proposals/_metrics.jsonl.

    Creates the parent directory if missing. One line per investigation
    attempt — success, blocked, or infrastructure failure.
    """
    target = dazzle_root / ".dazzle" / "fitness-proposals" / "_metrics.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "cluster_id": cluster_id,
        "proposal_id": proposal_id,
        "status": status,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tool_calls": tool_calls,
        "duration_ms": duration_ms,
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
    }
    with target.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
