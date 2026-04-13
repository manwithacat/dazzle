"""Unit tests for the mcp__dazzle__fitness handler."""

from __future__ import annotations

import json
from pathlib import Path

from dazzle.mcp.server.handlers.fitness import fitness_queue_handler


def _write_queue(
    path: Path,
    *,
    project: str = "demo",
    raw: int = 5,
    clusters: int = 1,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Fitness Queue\n\n"
        "Ranked, deduped view.\n\n"
        f"**Project:** {project}\n"
        "**Generated:** 2026-04-14T00:00:00Z\n"
        f"**Raw findings:** {raw}\n"
        f"**Clusters:** {clusters}\n"
        f"**Dedup ratio:** {raw / clusters:.1f}×\n\n"
        "| rank | cluster_id | severity | locus | axis | persona | size | summary | first_seen | last_seen | sample_id |\n"
        "|------|-----------|----------|-------|------|---------|------|---------|------------|-----------|-----------|\n"
        "| 1 | CL-abc12345 | high | story_drift | coverage | Admin | 5 | example summary | 2026-04-13T19:00:00+00:00 | 2026-04-13T20:00:00+00:00 | FIND-xyz |\n"
    )


def test_queue_operation_returns_json(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    _write_queue(project_root / "dev_docs" / "fitness-queue.md")

    result = fitness_queue_handler(
        tmp_path,
        {"project_root": str(project_root), "top": 10},
    )
    payload = json.loads(result)
    assert payload["project"] == "project"
    assert payload["raw_findings"] == 5
    assert payload["clusters_total"] == 1
    assert len(payload["clusters"]) == 1
    assert payload["clusters"][0]["cluster_id"] == "CL-abc12345"
    assert payload["clusters"][0]["severity"] == "high"


def test_queue_missing_file_returns_error(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()

    result = fitness_queue_handler(
        tmp_path,
        {"project_root": str(project_root), "top": 10},
    )
    payload = json.loads(result)
    assert "error" in payload
    assert "fitness triage" in payload["error"]


def test_queue_respects_top_parameter(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    queue_file = project_root / "dev_docs" / "fitness-queue.md"
    queue_file.parent.mkdir(parents=True)
    queue_file.write_text(
        "# Fitness Queue\n\n"
        "**Project:** project\n"
        "**Generated:** 2026-04-14T00:00:00Z\n"
        "**Raw findings:** 3\n"
        "**Clusters:** 3\n"
        "**Dedup ratio:** 1.0×\n\n"
        "| rank | cluster_id | severity | locus | axis | persona | size | summary | first_seen | last_seen | sample_id |\n"
        "|------|-----------|----------|-------|------|---------|------|---------|------------|-----------|-----------|\n"
        "| 1 | CL-000aaa11 | high | story_drift | coverage | A | 1 | first | 2026-04-13T19:00:00+00:00 | 2026-04-13T19:00:00+00:00 | FIND-1 |\n"
        "| 2 | CL-000bbb22 | medium | story_drift | coverage | B | 1 | second | 2026-04-13T19:00:00+00:00 | 2026-04-13T19:00:00+00:00 | FIND-2 |\n"
        "| 3 | CL-000ccc33 | low | story_drift | coverage | C | 1 | third | 2026-04-13T19:00:00+00:00 | 2026-04-13T19:00:00+00:00 | FIND-3 |\n"
    )

    result = fitness_queue_handler(
        tmp_path,
        {"project_root": str(project_root), "top": 2},
    )
    payload = json.loads(result)
    assert len(payload["clusters"]) == 2
    assert payload["clusters_total"] == 3  # total preserved
