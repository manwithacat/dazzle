"""Tests for dazzle.qa.evaluate — pluggable LLM evaluator."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from dazzle.qa.evaluate import ClaudeEvaluator, build_evaluation_prompt, parse_findings
from dazzle.qa.models import CapturedScreen, Finding

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_screen(tmp_path: Path) -> CapturedScreen:
    screenshot = tmp_path / "screen.png"
    screenshot.write_bytes(b"\x89PNG\r\n")
    return CapturedScreen(
        persona="teacher",
        workspace="teacher_workspace",
        url="/app/workspaces/teacher_workspace",
        screenshot=screenshot,
    )


# ---------------------------------------------------------------------------
# build_evaluation_prompt
# ---------------------------------------------------------------------------


class TestBuildEvaluationPrompt:
    def test_contains_all_eight_category_names(self) -> None:
        screen = CapturedScreen(
            persona="teacher",
            workspace="teacher_workspace",
            url="/app",
            screenshot=Path("x.png"),
        )
        prompt = build_evaluation_prompt(screen)
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

    def test_contains_workspace_context(self) -> None:
        screen = CapturedScreen(
            persona="admin",
            workspace="admin_workspace",
            url="/app/workspaces/admin_workspace",
            screenshot=Path("x.png"),
        )
        prompt = build_evaluation_prompt(screen)
        assert "admin_workspace" in prompt
        assert "admin" in prompt

    def test_requests_json_array_output(self) -> None:
        screen = CapturedScreen(
            persona="teacher",
            workspace="teacher_workspace",
            url="/app",
            screenshot=Path("x.png"),
        )
        prompt = build_evaluation_prompt(screen)
        assert "JSON" in prompt or "json" in prompt
        assert "[]" in prompt or "empty array" in prompt.lower() or "array" in prompt.lower()


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


# ---------------------------------------------------------------------------
# ClaudeEvaluator
# ---------------------------------------------------------------------------


class TestClaudeEvaluator:
    def test_evaluate_calls_anthropic_client(self, tmp_path: Path) -> None:
        screen = _make_screen(tmp_path)

        # Build a mock Anthropic client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="[]")]
        mock_client.messages.create.return_value = mock_response

        evaluator = ClaudeEvaluator(client=mock_client)

        with patch("dazzle.qa.evaluate._read_screenshot_b64", return_value="AAAA"):
            findings = evaluator.evaluate(screen)

        assert mock_client.messages.create.called
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs is not None
        assert findings == []
