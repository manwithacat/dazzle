"""Tests for the investigator runner.

Uses a stub LLM client (_StubLlmClient) with scripted tool calls —
no real LLM is invoked.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from dazzle.fitness.backlog import upsert_findings
from dazzle.fitness.investigator.runner import (
    run_investigation,
    walk_queue,
)
from dazzle.fitness.models import EvidenceEmbedded, Finding
from dazzle.fitness.triage import Cluster, write_queue_file


def _finding(fid: str = "f_001") -> Finding:
    return Finding(
        id=fid,
        created=datetime(2026, 4, 14, tzinfo=UTC),
        run_id="run-1",
        cycle=None,
        axis="coverage",
        locus="implementation",
        severity="high",
        persona="admin",
        capability_ref="x",
        expected="y",
        observed="z",
        evidence_embedded=EvidenceEmbedded(
            expected_ledger_step={},
            diff_summary=[],
            transcript_excerpt=[{"text": "src/foo.html:1 problem"}],
        ),
        disambiguation=False,
        low_confidence=False,
        status="PROPOSED",
        route="soft",
        fix_commit=None,
        alternative_fix=None,
    )


def _cluster() -> Cluster:
    return Cluster(
        cluster_id="CL-deadbeef",
        locus="implementation",
        axis="coverage",
        canonical_summary="z",
        persona="admin",
        severity="high",
        cluster_size=1,
        first_seen=datetime(2026, 4, 14, tzinfo=UTC),
        last_seen=datetime(2026, 4, 14, tzinfo=UTC),
        sample_id="f_001",
    )


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(tmp_path / "dev_docs" / "fitness-backlog.md", [_finding("f_001")])
    write_queue_file(
        tmp_path / "dev_docs" / "fitness-queue.md",
        [_cluster()],
        project_name="fixture",
        raw_findings_count=1,
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.html").write_text("<div>line 1</div>\n")
    return tmp_path


class _StubLlmClient:
    """Test double for the LLM client.

    The runner discriminates on `hasattr(llm_client, "script")`, so this
    class has a `script` attribute and gets dispatched to the stub driver.
    The driver walks the script, calls each tool's handler directly, and
    increments `calls`.
    """

    def __init__(self, script: list[dict[str, Any]]):
        self.script = script
        self.calls = 0
        self.run_id = "stub-run-id"
        self.model = "stub-model"


def _minimal_propose_payload() -> dict[str, Any]:
    return {
        "fixes": [
            {
                "file_path": "src/foo.html",
                "line_range": [1, 1],
                "diff": (
                    "--- a/src/foo.html\n"
                    "+++ b/src/foo.html\n"
                    "@@ -1,1 +1,1 @@\n"
                    "-<div>line 1</div>\n"
                    "+<div>line 1 fixed</div>\n"
                ),
                "rationale": "fix the div",
                "confidence": 0.85,
            }
        ],
        "rationale": "Standard rationale that meets the 20-char minimum easily.",
        "overall_confidence": 0.85,
        "verification_plan": "Re-run Phase B; expect cluster CL-deadbeef to vanish from queue.",
        "alternatives_considered": ["do nothing — rejected"],
        "investigation_log": "looked at foo.html",
    }


@pytest.mark.asyncio
async def test_run_investigation_happy_path(fake_root: Path) -> None:
    """A scripted investigation that calls read_file then propose_fix returns a Proposal."""
    script = [
        {"tool": "read_file", "args": {"path": "src/foo.html"}},
        {"tool": "propose_fix", "args": _minimal_propose_payload()},
    ]

    result = await run_investigation(
        cluster=_cluster(),
        dazzle_root=fake_root,
        llm_client=_StubLlmClient(script),
        force=False,
        dry_run=False,
    )

    assert result is not None
    assert result.cluster_id == "CL-deadbeef"
    assert result.status == "proposed"

    proposals = list((fake_root / ".dazzle" / "fitness-proposals").glob("CL-deadbeef-*.md"))
    assert len(proposals) == 1


@pytest.mark.asyncio
async def test_run_investigation_idempotent_skip(fake_root: Path) -> None:
    """Second call with force=False returns the existing Proposal without running the LLM."""
    script = [
        {"tool": "read_file", "args": {"path": "src/foo.html"}},
        {"tool": "propose_fix", "args": _minimal_propose_payload()},
    ]

    first = await run_investigation(
        cluster=_cluster(),
        dazzle_root=fake_root,
        llm_client=_StubLlmClient(script),
        force=False,
        dry_run=False,
    )
    second_client = _StubLlmClient([])  # empty script — would fail if driver invoked
    second = await run_investigation(
        cluster=_cluster(),
        dazzle_root=fake_root,
        llm_client=second_client,
        force=False,
        dry_run=False,
    )
    assert first is not None and second is not None
    assert first.proposal_id == second.proposal_id
    assert second_client.calls == 0  # stub driver never invoked


@pytest.mark.asyncio
async def test_run_investigation_dry_run(fake_root: Path, capsys) -> None:
    """--dry-run prints the case file and returns None without invoking the LLM."""
    result = await run_investigation(
        cluster=_cluster(),
        dazzle_root=fake_root,
        llm_client=_StubLlmClient([]),
        force=False,
        dry_run=True,
    )
    assert result is None
    captured = capsys.readouterr()
    assert "# Case File" in captured.out
    # No proposal file should exist
    proposals_dir = fake_root / ".dazzle" / "fitness-proposals"
    if proposals_dir.exists():
        assert not list(proposals_dir.glob("CL-*.md"))


@pytest.mark.asyncio
async def test_walk_queue_top_n(fake_root: Path) -> None:
    """walk_queue iterates the top N clusters from fitness-queue.md."""
    script = [
        {"tool": "read_file", "args": {"path": "src/foo.html"}},
        {"tool": "propose_fix", "args": _minimal_propose_payload()},
    ]
    results = await walk_queue(
        dazzle_root=fake_root,
        llm_client=_StubLlmClient(script),
        top=1,
        force=False,
        dry_run=False,
    )
    assert len(results) == 1
    assert results[0] is not None
