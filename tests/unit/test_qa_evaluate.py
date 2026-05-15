"""Tests for dazzle.qa.evaluate — subagent prompt builder + findings parser."""

import json
from pathlib import Path

from dazzle.qa.evaluate import build_subagent_prompt, parse_findings
from dazzle.qa.models import Finding


def _make_manifest() -> dict:
    return {
        "timestamp": "2026-05-15T00:00:00+00:00",
        "apps": [
            {
                "app": "ops_dashboard",
                "screens": [
                    {
                        "persona": "ops_engineer",
                        "workspace": "command_center",
                        "url": "/app/workspaces/command_center",
                        "screenshot": "/tmp/x/cc_ops_engineer.png",
                        "viewport": "desktop",
                    },
                ],
            },
        ],
    }


# ---------------------------------------------------------------------------
# build_subagent_prompt
# ---------------------------------------------------------------------------


class TestBuildSubagentPrompt:
    def test_contains_all_eight_category_names(self) -> None:
        prompt = build_subagent_prompt(_make_manifest(), "/tmp/findings.json")
        expected_ids = [
            "text_wrapping",
            "truncation",
            "title_formatting",
            "column_layout",
            "empty_state",
            "alignment",
            "readability",
            "data_quality",
        ]
        for cat_id in expected_ids:
            assert cat_id in prompt, f"Category '{cat_id}' missing from prompt"

    def test_contains_per_screen_context(self) -> None:
        prompt = build_subagent_prompt(_make_manifest(), "/tmp/findings.json")
        assert "ops_dashboard" in prompt
        assert "command_center" in prompt
        assert "ops_engineer" in prompt
        assert "/tmp/x/cc_ops_engineer.png" in prompt

    def test_includes_findings_path_for_write(self) -> None:
        prompt = build_subagent_prompt(_make_manifest(), "/tmp/findings.json")
        assert "/tmp/findings.json" in prompt
        # Must instruct the subagent to Write the JSON output.
        assert "Write" in prompt

    def test_output_schema_requires_screenshot_field(self) -> None:
        """Subagent must echo the screenshot path that triggered each finding —
        the ingest step pairs the row back to its source image. Forgetting this
        was the cycle 141 smoke-test bug."""
        prompt = build_subagent_prompt(_make_manifest(), "/tmp/findings.json")
        assert "`screenshot`" in prompt

    def test_requests_json_array_output(self) -> None:
        prompt = build_subagent_prompt(_make_manifest(), "/tmp/findings.json")
        assert "JSON" in prompt or "json" in prompt
        assert "[]" in prompt or "empty array" in prompt.lower() or "array" in prompt.lower()

    def test_filters_categories_when_specified(self) -> None:
        prompt = build_subagent_prompt(
            _make_manifest(),
            "/tmp/findings.json",
            categories=["data_quality"],
        )
        assert "data_quality" in prompt
        assert "text_wrapping" not in prompt

    def test_handles_multi_app_manifest(self) -> None:
        manifest = _make_manifest()
        manifest["apps"].append(
            {
                "app": "simple_task",
                "screens": [
                    {
                        "persona": "admin",
                        "workspace": "task_board",
                        "url": "/app/workspaces/task_board",
                        "screenshot": "/tmp/y/tb_admin.png",
                    }
                ],
            }
        )
        prompt = build_subagent_prompt(manifest, "/tmp/findings.json")
        assert "ops_dashboard" in prompt
        assert "simple_task" in prompt
        assert "2 apps" in prompt


# ---------------------------------------------------------------------------
# parse_findings
# ---------------------------------------------------------------------------


class TestParseFindings:
    def _make_raw(self, findings: list[dict]) -> str:
        return json.dumps(findings)

    def test_valid_json_array(self) -> None:
        raw = self._make_raw(
            [
                {
                    "category": "data_quality",
                    "severity": "high",
                    "location": "Student column",
                    "description": "UUID visible",
                    "suggestion": "Display student name",
                }
            ]
        )
        results = parse_findings(raw)
        assert len(results) == 1
        assert isinstance(results[0], Finding)
        assert results[0].category == "data_quality"
        assert results[0].severity == "high"

    def test_empty_array_returns_empty_list(self) -> None:
        results = parse_findings("[]")
        assert results == []

    def test_markdown_fences_stripped(self) -> None:
        raw = (
            "```json\n"
            + json.dumps(
                [
                    {
                        "category": "alignment",
                        "severity": "low",
                        "location": "Header",
                        "description": "Misaligned buttons",
                        "suggestion": "Fix spacing",
                    }
                ]
            )
            + "\n```"
        )
        results = parse_findings(raw)
        assert len(results) == 1
        assert results[0].category == "alignment"

    def test_invalid_json_returns_empty_list(self) -> None:
        results = parse_findings("this is not JSON at all {{{")
        assert results == []

    def test_skips_entries_missing_required_keys(self, tmp_path: Path) -> None:
        raw = json.dumps(
            [
                {"category": "data_quality", "severity": "high"},  # missing fields
                {
                    "category": "alignment",
                    "severity": "low",
                    "location": "Header",
                    "description": "Misaligned",
                    "suggestion": "Fix",
                },
            ]
        )
        results = parse_findings(raw)
        assert len(results) == 1
        assert results[0].category == "alignment"
