"""Tests for the investigator metrics sink."""

import json
from pathlib import Path

from dazzle.fitness.investigator.metrics import append_metric


def test_append_metric_creates_file(tmp_path: Path) -> None:
    append_metric(
        tmp_path,
        cluster_id="CL-deadbeef",
        proposal_id="abc12345",
        status="proposed",
        tokens_in=100,
        tokens_out=50,
        tool_calls=3,
        duration_ms=1234,
        model="claude-sonnet-4-6",
    )
    metrics = tmp_path / ".dazzle" / "fitness-proposals" / "_metrics.jsonl"
    assert metrics.exists()
    line = metrics.read_text().strip()
    data = json.loads(line)
    assert data["cluster_id"] == "CL-deadbeef"
    assert data["status"] == "proposed"
    assert data["tokens_in"] == 100
    assert data["tool_calls"] == 3
    assert data["model"] == "claude-sonnet-4-6"
    assert data["proposal_id"] == "abc12345"
    assert "created" in data
    assert data["created"].endswith("Z")
    assert "." not in data["created"]  # no microseconds


def test_append_metric_is_append_only(tmp_path: Path) -> None:
    for i in range(3):
        append_metric(
            tmp_path,
            cluster_id=f"CL-{i:08x}",
            proposal_id=None,
            status="blocked_step_cap",
            tokens_in=0,
            tokens_out=0,
            tool_calls=0,
            duration_ms=0,
            model="x",
        )
    metrics = tmp_path / ".dazzle" / "fitness-proposals" / "_metrics.jsonl"
    lines = metrics.read_text().strip().split("\n")
    assert len(lines) == 3
    ids = [json.loads(line)["cluster_id"] for line in lines]
    assert ids == ["CL-00000000", "CL-00000001", "CL-00000002"]
    # Verify each line has all expected fields
    for line in lines:
        data = json.loads(line)
        assert data["proposal_id"] is None
        assert data["status"] == "blocked_step_cap"


def test_append_metric_creates_parent_dir(tmp_path: Path) -> None:
    """The .dazzle/fitness-proposals/ directory should be created if missing."""
    # tmp_path has no .dazzle yet
    append_metric(
        tmp_path,
        cluster_id="CL-11112222",
        proposal_id="id-1",
        status="proposed",
        tokens_in=1,
        tokens_out=1,
        tool_calls=1,
        duration_ms=1,
        model="claude-sonnet-4-6",
    )
    assert (tmp_path / ".dazzle" / "fitness-proposals" / "_metrics.jsonl").exists()
