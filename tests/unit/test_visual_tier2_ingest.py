"""Tests for visual_tier2_ingest — example-apps Tier 2 backlog ingestion."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from dazzle.cli.runtime_impl.ux_cycle_impl.visual_tier2_ingest import (
    ingest_visual_findings,
)


def _seed_backlog(path: Path) -> None:
    """Write a minimal backlog with an example-apps section closed by `---`."""
    path.write_text(
        textwrap.dedent(
            """\
            # Backlog (test fixture)

            ## Lane: example-apps

            | # | App | Gap Type | Description | Status | Attempts | Notes |
            |---|-----|----------|-------------|--------|----------|-------|
            | 1 | simple_task | lint | Existing row | DONE | 1 | seeded |

            ---

            ## Lane: trials

            (other lane)
            """
        )
    )


def _seed_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "timestamp": "2026-05-15T00:00:00+00:00",
                "apps": [
                    {
                        "app": "ops_dashboard",
                        "screens": [
                            {
                                "persona": "ops_engineer",
                                "workspace": "command_center",
                                "url": "/app/workspaces/command_center",
                                "screenshot": "/tmp/ops_cc.png",
                                "viewport": "desktop",
                            }
                        ],
                    },
                    {
                        "app": "simple_task",
                        "screens": [
                            {
                                "persona": "admin",
                                "workspace": "task_board",
                                "url": "/app/workspaces/task_board",
                                "screenshot": "/tmp/st_tb.png",
                            }
                        ],
                    },
                ],
            }
        )
    )


def _write_findings(path: Path, items: list[dict]) -> None:
    path.write_text(json.dumps(items))


def test_three_findings_become_three_rows_severity_sorted(tmp_path: Path) -> None:
    backlog = tmp_path / "improve-backlog.md"
    manifest = tmp_path / "manifest.json"
    findings = tmp_path / "findings.json"
    _seed_backlog(backlog)
    _seed_manifest(manifest)
    _write_findings(
        findings,
        [
            {
                "app": "simple_task",
                "screenshot": "/tmp/y/tb_admin.png",
                "category": "alignment",
                "severity": "low",
                "location": "task_board header",
                "description": "buttons drift",
                "suggestion": "snap to 4px",
            },
            {
                "app": "ops_dashboard",
                "screenshot": "/tmp/x/cc_ops_engineer.png",
                "category": "data_quality",
                "severity": "high",
                "location": "alerts_timeseries chart",
                "description": "no data shown",
                "suggestion": "seed alerts",
            },
            {
                "app": "ops_dashboard",
                "screenshot": "/tmp/x/cc_ops_engineer.png",
                "category": "empty_state",
                "severity": "medium",
                "location": "system_status panel",
                "description": "vague empty copy",
                "suggestion": "explain next step",
            },
        ],
    )

    result = ingest_visual_findings(findings, manifest, backlog)
    assert result.rows_added == 3
    assert result.rows_reinforced == 0
    assert result.starting_row_id == 2  # existing seed used id 1

    text = backlog.read_text()
    # New rows appear inside the lane, before the closing `---`.
    lane_section = text.split("## Lane: trials")[0]
    assert "| 2 | ops_dashboard | visual_quality" in lane_section
    assert "| 3 | ops_dashboard | visual_quality" in lane_section
    assert "| 4 | simple_task | visual_quality" in lane_section
    # The id-2 row should be the high-severity one (data_quality).
    row2 = [line for line in lane_section.splitlines() if line.startswith("| 2 |")][0]
    assert "data_quality" in row2
    # Row 4 should be the low-severity alignment row.
    row4 = [line for line in lane_section.splitlines() if line.startswith("| 4 |")][0]
    assert "alignment" in row4
    # Trailing `---` separator still present.
    assert "---\n\n## Lane: trials" in text


def test_dedup_on_rerun_reinforces_existing_row(tmp_path: Path) -> None:
    backlog = tmp_path / "improve-backlog.md"
    manifest = tmp_path / "manifest.json"
    findings = tmp_path / "findings.json"
    _seed_backlog(backlog)
    _seed_manifest(manifest)
    finding_set = [
        {
            "app": "ops_dashboard",
            "category": "data_quality",
            "severity": "high",
            "location": "alerts_timeseries chart",
            "description": "no data shown",
            "suggestion": "seed alerts",
        }
    ]
    _write_findings(findings, finding_set)

    first = ingest_visual_findings(findings, manifest, backlog)
    assert first.rows_added == 1
    assert first.rows_reinforced == 0

    second = ingest_visual_findings(findings, manifest, backlog)
    assert second.rows_added == 0
    assert second.rows_reinforced == 1

    text = backlog.read_text()
    assert "seen=2" in text
    # Only one row for this finding — not duplicated.
    assert text.count("data_quality") == 1


def test_screenshot_field_pins_row_to_source_screen(tmp_path: Path) -> None:
    """Regression test: each row's `screenshot=` should match the source screen,
    not just the first screenshot for the app (the cycle 141 smoke-test bug)."""
    backlog = tmp_path / "improve-backlog.md"
    manifest = tmp_path / "manifest.json"
    findings = tmp_path / "findings.json"
    _seed_backlog(backlog)
    # Manifest with two simple_task screens — the finding-specific
    # screenshot path is the second one, not the first.
    manifest.write_text(
        json.dumps(
            {
                "apps": [
                    {
                        "app": "simple_task",
                        "screens": [
                            {
                                "persona": "admin",
                                "workspace": "task_board",
                                "url": "/app/workspaces/task_board",
                                "screenshot": "/tmp/x/task_board_admin.png",
                            },
                            {
                                "persona": "member",
                                "workspace": "my_work",
                                "url": "/app/workspaces/my_work",
                                "screenshot": "/tmp/x/my_work_member.png",
                            },
                        ],
                    }
                ]
            }
        )
    )
    _write_findings(
        findings,
        [
            {
                "app": "simple_task",
                "screenshot": "/tmp/x/my_work_member.png",
                "category": "empty_state",
                "severity": "medium",
                "location": "my_work — My Completed section",
                "description": "blank region with no copy",
                "suggestion": "add empty-state icon + CTA",
            }
        ],
    )
    result = ingest_visual_findings(findings, manifest, backlog)
    assert result.rows_added == 1

    text = backlog.read_text()
    # The row's notes should reference the my_work screenshot, NOT the
    # first-in-manifest task_board one.
    row = next(line for line in text.splitlines() if line.startswith("| 2 |"))
    assert "screenshot=/tmp/x/my_work_member.png" in row
    assert "task_board_admin.png" not in row


def test_screenshot_fallback_to_manifest_when_finding_omits_it(tmp_path: Path) -> None:
    """If the finding lacks `screenshot` but provides persona+workspace,
    ingest should look up the screenshot from the manifest."""
    backlog = tmp_path / "improve-backlog.md"
    manifest = tmp_path / "manifest.json"
    findings = tmp_path / "findings.json"
    _seed_backlog(backlog)
    manifest.write_text(
        json.dumps(
            {
                "apps": [
                    {
                        "app": "simple_task",
                        "screens": [
                            {
                                "persona": "admin",
                                "workspace": "task_board",
                                "url": "/app/workspaces/task_board",
                                "screenshot": "/tmp/x/task_board_admin.png",
                            },
                            {
                                "persona": "member",
                                "workspace": "my_work",
                                "url": "/app/workspaces/my_work",
                                "screenshot": "/tmp/x/my_work_member.png",
                            },
                        ],
                    }
                ]
            }
        )
    )
    _write_findings(
        findings,
        [
            {
                "app": "simple_task",
                "persona": "member",
                "workspace": "my_work",
                "category": "empty_state",
                "severity": "medium",
                "location": "my_work — My Completed section",
                "description": "blank region",
                "suggestion": "add CTA",
            }
        ],
    )
    result = ingest_visual_findings(findings, manifest, backlog)
    assert result.rows_added == 1
    text = backlog.read_text()
    row = next(line for line in text.splitlines() if line.startswith("| 2 |"))
    assert "screenshot=/tmp/x/my_work_member.png" in row


def test_findings_with_missing_required_fields_skip(tmp_path: Path) -> None:
    backlog = tmp_path / "improve-backlog.md"
    manifest = tmp_path / "manifest.json"
    findings = tmp_path / "findings.json"
    _seed_backlog(backlog)
    _seed_manifest(manifest)
    _write_findings(
        findings,
        [
            {"app": "ops_dashboard", "category": "", "severity": "high", "location": "x"},
            {
                "app": "ops_dashboard",
                "category": "alignment",
                "severity": "medium",
                "location": "y",
                "description": "ok",
                "suggestion": "ok",
            },
        ],
    )
    result = ingest_visual_findings(findings, manifest, backlog)
    assert result.rows_added == 1
    assert any("missing" in w for w in result.warnings)
