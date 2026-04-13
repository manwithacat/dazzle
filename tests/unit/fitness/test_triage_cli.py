"""Smoke tests for `dazzle fitness triage` and `dazzle fitness queue`."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dazzle.cli.fitness import fitness_app

runner = CliRunner()


def _write_backlog(path: Path, rows_table: str) -> None:
    """Write a minimal fitness-backlog.md with the given rows block."""
    header = (
        "# Fitness Backlog\n\n"
        "Structured findings.\n\n"
        "| id | created | locus | axis | severity | persona | status | route | summary |\n"
        "|----|---------|-------|------|----------|---------|--------|-------|---------|\n"
    )
    path.write_text(header + rows_table)


def test_triage_writes_queue_file(tmp_path: Path) -> None:
    backlog = tmp_path / "dev_docs" / "fitness-backlog.md"
    backlog.parent.mkdir(parents=True)
    rows = (
        "| FIND-1 | 2026-04-13T19:00:00+00:00 | story_drift | coverage | medium | Admin | PROPOSED | soft | No matching story found |\n"
        "| FIND-2 | 2026-04-13T19:00:01+00:00 | story_drift | coverage | medium | Admin | PROPOSED | soft | No matching story found |\n"
        "| FIND-3 | 2026-04-13T19:00:02+00:00 | story_drift | coverage | high | User | PROPOSED | soft | Route mismatch |\n"
    )
    _write_backlog(backlog, rows)

    result = runner.invoke(fitness_app, ["triage", "--project", str(tmp_path)])
    assert result.exit_code == 0, result.stdout

    queue_file = tmp_path / "dev_docs" / "fitness-queue.md"
    assert queue_file.exists()
    content = queue_file.read_text()
    assert "# Fitness Queue" in content
    assert "CL-" in content


def test_queue_json_output(tmp_path: Path) -> None:
    backlog = tmp_path / "dev_docs" / "fitness-backlog.md"
    backlog.parent.mkdir(parents=True)
    rows = "| FIND-1 | 2026-04-13T19:00:00+00:00 | story_drift | coverage | high | Admin | PROPOSED | soft | Example finding |\n"
    _write_backlog(backlog, rows)

    # Regenerate first.
    runner.invoke(fitness_app, ["triage", "--project", str(tmp_path)])

    # Now read as JSON.
    result = runner.invoke(fitness_app, ["queue", "--project", str(tmp_path), "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["clusters_total"] == 1
    assert payload["raw_findings"] == 1
    assert len(payload["clusters"]) == 1
    assert payload["clusters"][0]["severity"] == "high"


def test_queue_missing_file_exits_1(tmp_path: Path) -> None:
    result = runner.invoke(fitness_app, ["queue", "--project", str(tmp_path)])
    assert result.exit_code == 1
    assert "fitness triage" in (result.stdout + (result.stderr or "")).lower()
