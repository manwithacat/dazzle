"""Tests for investigator tools (6 AgentTools + shared ToolState).

This file grows across Tasks 9-14 as each tool is added.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dazzle.fitness.backlog import upsert_findings
from dazzle.fitness.investigator.case_file import CaseFile, build_case_file
from dazzle.fitness.investigator.tools import ToolState, build_investigator_tools
from dazzle.fitness.models import EvidenceEmbedded, Finding
from dazzle.fitness.triage import Cluster

# ------------ shared fixtures ----------------------------------------------


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
        capability_ref="Ticket.create",
        expected="foo",
        observed="bar at line 47",
        evidence_embedded=EvidenceEmbedded(
            expected_ledger_step={"step": 1},
            diff_summary=[],
            transcript_excerpt=[{"text": "src/ui/form.html:47 problem"}],
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
        canonical_summary="bar at line 47",
        persona="admin",
        severity="high",
        cluster_size=1,
        first_seen=datetime(2026, 4, 14, tzinfo=UTC),
        last_seen=datetime(2026, 4, 14, tzinfo=UTC),
        sample_id="f_001",
    )


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    """A tmp_path seeded with a backlog and a small locus file."""
    (tmp_path / "dev_docs").mkdir()
    upsert_findings(tmp_path / "dev_docs" / "fitness-backlog.md", [_finding("f_001")])
    locus = tmp_path / "src" / "ui" / "form.html"
    locus.parent.mkdir(parents=True)
    locus.write_text("\n".join(f"<div>line {i}</div>" for i in range(1, 21)))
    return tmp_path


@pytest.fixture
def case_file(fake_root: Path) -> CaseFile:
    return build_case_file(_cluster(), fake_root)


@pytest.fixture
def state() -> ToolState:
    return ToolState()


def _tools_by_name(case_file: CaseFile, fake_root: Path, state: ToolState) -> dict[str, object]:
    tools = build_investigator_tools(
        case_file=case_file,
        dazzle_root=fake_root,
        llm_run_id="run-xyz",
        state=state,
    )
    return {t.name: t for t in tools}


# ------------ tool: read_file ----------------------------------------------


def test_read_file_happy_path(case_file, fake_root, state) -> None:
    tools = _tools_by_name(case_file, fake_root, state)
    result = tools["read_file"].handler(path="src/ui/form.html")
    assert "content" in result
    assert "  1: <div>line 1</div>" in result["content"]
    assert "src/ui/form.html" in state.evidence_paths
    assert any("read_file" in entry for entry in state.tool_calls_summary)


def test_read_file_rejects_absolute_path(case_file, fake_root, state) -> None:
    tools = _tools_by_name(case_file, fake_root, state)
    result = tools["read_file"].handler(path="/etc/passwd")
    assert "error" in result
    assert "repo-relative" in result["error"]


def test_read_file_missing_with_similar_suggestions(case_file, fake_root, state) -> None:
    (fake_root / "src" / "ui" / "other_form.html").write_text("x")
    tools = _tools_by_name(case_file, fake_root, state)
    result = tools["read_file"].handler(path="src/ui/notreal.html")
    assert "error" in result
    assert "not found" in result["error"]
    assert "similar" in result


def test_read_file_traversal_guard(case_file, fake_root, state) -> None:
    tools = _tools_by_name(case_file, fake_root, state)
    result = tools["read_file"].handler(path="../../etc/passwd")
    assert "error" in result
    assert "escape" in result["error"] or "traversal" in result["error"]


def test_read_file_line_range(case_file, fake_root, state) -> None:
    tools = _tools_by_name(case_file, fake_root, state)
    result = tools["read_file"].handler(path="src/ui/form.html", line_range=[5, 7])
    assert "content" in result
    # Right-aligned 3-char minimum width (20-line file → max(3,2)=3)
    assert "5: " in result["content"]
    assert "7: " in result["content"]
    assert "3: " not in result["content"]
