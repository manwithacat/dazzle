"""Tests for `dazzle fitness investigate` CLI subcommand."""

from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from dazzle.cli.fitness import fitness_app
from dazzle.fitness.backlog import upsert_findings
from dazzle.fitness.models import EvidenceEmbedded, Finding
from dazzle.fitness.triage import Cluster, write_queue_file


def _finding() -> Finding:
    return Finding(
        id="f_001",
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


def _seed_project(root: Path) -> None:
    (root / "dev_docs").mkdir(parents=True, exist_ok=True)
    upsert_findings(root / "dev_docs" / "fitness-backlog.md", [_finding()])
    write_queue_file(
        root / "dev_docs" / "fitness-queue.md",
        [_cluster()],
        project_name="fixture",
        raw_findings_count=1,
    )
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "foo.html").write_text("<div>line 1</div>\n")


def test_investigate_dry_run_prints_case_file(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        fitness_app,
        [
            "investigate",
            "--cluster",
            "CL-deadbeef",
            "--dry-run",
            "--project",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "# Case File" in result.output
    assert "CL-deadbeef" in result.output


def test_investigate_cluster_not_in_queue_exits_2(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        fitness_app,
        [
            "investigate",
            "--cluster",
            "CL-nosuch",
            "--dry-run",
            "--project",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 2
    assert "not in queue" in result.output.lower()


def test_investigate_top_empty_queue_exits_1(tmp_path: Path) -> None:
    (tmp_path / "dev_docs").mkdir()
    (tmp_path / "dev_docs" / "fitness-queue.md").write_text("# empty\n")
    runner = CliRunner()
    result = runner.invoke(
        fitness_app,
        ["investigate", "--top", "1", "--project", str(tmp_path)],
    )
    assert result.exit_code == 1


def test_investigate_top_zero_exits_2(tmp_path: Path) -> None:
    _seed_project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        fitness_app,
        ["investigate", "--top", "0", "--project", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert "must be >= 1" in result.output
