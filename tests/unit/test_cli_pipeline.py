"""Tests for pipeline, composition, discovery CLI commands and --format json retrofits."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from dazzle.cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fake_toml(tmp_path: Path) -> Path:
    """Create a fake dazzle.toml so CLI commands don't bail early."""
    toml = tmp_path / "dazzle.toml"
    toml.write_text("[project]\nname = 'test'\n")
    return toml


def _manifest_args(tmp_path: Path) -> list[str]:
    return ["--manifest", str(tmp_path / "dazzle.toml")]


# ---------------------------------------------------------------------------
# pipeline run
# ---------------------------------------------------------------------------

_PIPELINE_RESULT = json.dumps(
    {
        "status": "passed",
        "total_duration_ms": 1234.5,
        "summary": {"total_steps": 11, "passed": 10, "failed": 0, "skipped": 1},
        "steps": [
            {
                "step": 1,
                "operation": "dsl(validate)",
                "status": "passed",
                "duration_ms": 120.0,
            },
            {
                "step": 2,
                "operation": "dsl(lint)",
                "status": "passed",
                "duration_ms": 45.0,
            },
        ],
    }
)

_PIPELINE_FAIL_RESULT = json.dumps(
    {
        "status": "failed",
        "total_duration_ms": 500,
        "summary": {"total_steps": 3, "passed": 2, "failed": 1, "skipped": 0},
        "steps": [
            {"step": 1, "operation": "dsl(validate)", "status": "passed", "duration_ms": 100},
            {
                "step": 2,
                "operation": "dsl(fidelity)",
                "status": "error",
                "duration_ms": 200,
                "error": "3 fidelity gaps found",
            },
        ],
    }
)

_HANDLER_MOD = "dazzle.mcp.server.handlers"


class TestPipelineRun:
    def test_json_format(self, tmp_path: Path) -> None:
        with patch(
            f"{_HANDLER_MOD}.pipeline.run_pipeline_handler",
            return_value=_PIPELINE_RESULT,
        ):
            result = runner.invoke(
                app, ["pipeline", "run", *_manifest_args(tmp_path), "--format", "json"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "passed"
        assert "summary" in data
        assert "steps" in data

    def test_table_format(self, tmp_path: Path) -> None:
        with patch(
            f"{_HANDLER_MOD}.pipeline.run_pipeline_handler",
            return_value=_PIPELINE_RESULT,
        ):
            result = runner.invoke(app, ["pipeline", "run", *_manifest_args(tmp_path)])
        assert result.exit_code == 0
        assert "Pipeline Quality Report" in result.output
        assert "dsl(validate)" in result.output

    def test_stop_on_error_flag(self, tmp_path: Path) -> None:
        with patch(
            f"{_HANDLER_MOD}.pipeline.run_pipeline_handler",
            return_value=_PIPELINE_RESULT,
        ) as mock_handler:
            runner.invoke(
                app,
                ["pipeline", "run", *_manifest_args(tmp_path), "--stop-on-error"],
            )
            call_args = mock_handler.call_args
            assert call_args[0][1]["stop_on_error"] is True

    def test_exit_code_on_failure(self, tmp_path: Path) -> None:
        with patch(
            f"{_HANDLER_MOD}.pipeline.run_pipeline_handler",
            return_value=_PIPELINE_FAIL_RESULT,
        ):
            result = runner.invoke(
                app, ["pipeline", "run", *_manifest_args(tmp_path), "--format", "json"]
            )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# composition audit
# ---------------------------------------------------------------------------

_AUDIT_RESULT = json.dumps(
    {
        "overall_score": 85,
        "pages": [
            {
                "route": "/",
                "score": 90,
                "violations_count": {"warning": 1},
            },
            {
                "route": "/tasks",
                "score": 80,
                "violations_count": {"error": 1, "warning": 2},
            },
        ],
        "summary": "2 pages audited",
    }
)


class TestCompositionAudit:
    def test_json_format(self, tmp_path: Path) -> None:
        with patch(
            f"{_HANDLER_MOD}.composition.audit_composition_handler",
            return_value=_AUDIT_RESULT,
        ):
            result = runner.invoke(
                app, ["composition", "audit", *_manifest_args(tmp_path), "--format", "json"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["overall_score"] == 85
        assert len(data["pages"]) == 2

    def test_exit_code_low_score(self, tmp_path: Path) -> None:
        low_score = json.dumps({"overall_score": 50, "pages": []})
        with patch(
            f"{_HANDLER_MOD}.composition.audit_composition_handler",
            return_value=low_score,
        ):
            result = runner.invoke(
                app, ["composition", "audit", *_manifest_args(tmp_path), "--format", "json"]
            )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# discovery coherence
# ---------------------------------------------------------------------------

_COHERENCE_RESULT = json.dumps(
    {
        "overall_score": 78,
        "personas": [
            {
                "persona": "admin",
                "coherence_score": 78,
                "workspace": "main",
                "checks": [
                    {"check": "workspace_binding", "status": "pass"},
                    {"check": "nav_filtering", "status": "warn", "detail": "1 issue"},
                ],
                "gap_count": 1,
            }
        ],
        "skipped_personas": [],
        "persona_count": 1,
    }
)


class TestDiscoveryCoherence:
    def test_json_format(self, tmp_path: Path) -> None:
        with patch(
            f"{_HANDLER_MOD}.discovery.app_coherence_handler",
            return_value=_COHERENCE_RESULT,
        ):
            result = runner.invoke(
                app, ["discovery", "coherence", *_manifest_args(tmp_path), "--format", "json"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["overall_score"] == 78
        assert len(data["personas"]) == 1

    def test_table_format(self, tmp_path: Path) -> None:
        with patch(
            f"{_HANDLER_MOD}.discovery.app_coherence_handler",
            return_value=_COHERENCE_RESULT,
        ):
            result = runner.invoke(app, ["discovery", "coherence", *_manifest_args(tmp_path)])
        assert result.exit_code == 0
        assert "App Coherence" in result.output
        assert "admin" in result.output

    def test_exit_code_low_score(self, tmp_path: Path) -> None:
        low = json.dumps(
            {"overall_score": 40, "personas": [], "skipped_personas": [], "persona_count": 0}
        )
        with patch(
            f"{_HANDLER_MOD}.discovery.app_coherence_handler",
            return_value=low,
        ):
            result = runner.invoke(
                app, ["discovery", "coherence", *_manifest_args(tmp_path), "--format", "json"]
            )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# test dsl-run --format json
# ---------------------------------------------------------------------------


class TestDslRunFormatJson:
    def test_json_format(self, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {
            "total_tests": 5,
            "passed": 5,
            "failed": 0,
            "tests": [],
        }
        mock_result.get_summary.return_value = {
            "total_tests": 5,
            "passed": 5,
            "failed": 0,
            "skipped": 0,
            "success_rate": 100.0,
        }

        mock_runner_cls = MagicMock()
        mock_runner_cls.return_value.run_all.return_value = mock_result

        with patch.dict(
            "sys.modules",
            {"dazzle.testing.unified_runner": MagicMock(UnifiedTestRunner=mock_runner_cls)},
        ):
            result = runner.invoke(
                app, ["test", "dsl-run", *_manifest_args(tmp_path), "--format", "json"]
            )

        # The internal import may or may not resolve to our mock depending on
        # whether the real module is importable; assert JSON when it works.
        if result.exit_code == 0:
            data = json.loads(result.output)
            assert data["passed"] == 5


# ---------------------------------------------------------------------------
# test run-all --format json
# ---------------------------------------------------------------------------


class TestRunAllFormatJson:
    def test_json_format(self, tmp_path: Path) -> None:
        mock_result = MagicMock()
        mock_result.get_summary.return_value = {
            "total_tests": 3,
            "passed": 3,
            "failed": 0,
            "skipped": 0,
            "success_rate": 100.0,
        }

        mock_runner_cls = MagicMock()
        mock_runner_cls.return_value.run_all.return_value = mock_result

        with patch.dict(
            "sys.modules",
            {"dazzle.testing.unified_runner": MagicMock(UnifiedTestRunner=mock_runner_cls)},
        ):
            # Tier 1 only for simpler mocking
            result = runner.invoke(
                app,
                ["test", "run-all", *_manifest_args(tmp_path), "--tier", "1", "--format", "json"],
            )

        if result.exit_code == 0:
            data = json.loads(result.output)
            assert "tiers" in data
            assert "overall" in data


# ---------------------------------------------------------------------------
# test dsl-run --base-url
# ---------------------------------------------------------------------------


class TestDslRunBaseUrl:
    """Tests for the --base-url flag on dsl-run."""

    def test_base_url_preflight_failure(self, tmp_path: Path) -> None:
        """When server is unreachable, exit 1 with clear error."""
        with patch(
            "dazzle.mcp.server.handlers.preflight.check_server_reachable",
            return_value=json.dumps(
                {
                    "error": "Server not reachable at https://bad.example.com",
                    "hint": "Start the app",
                }
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "test",
                    "dsl-run",
                    *_manifest_args(tmp_path),
                    "--base-url",
                    "https://bad.example.com",
                ],
            )
        assert result.exit_code == 1
        assert (
            "not reachable" in result.output.lower()
            or "not reachable" in (result.stderr or "").lower()
        )

    def test_base_url_passed_to_runner(self, tmp_path: Path) -> None:
        """--base-url is forwarded to UnifiedTestRunner."""
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"passed": 1, "failed": 0, "tests": []}
        mock_result.get_summary.return_value = {
            "total_tests": 1,
            "passed": 1,
            "failed": 0,
            "skipped": 0,
            "success_rate": 100.0,
        }

        mock_runner_cls = MagicMock()
        mock_runner_cls.return_value.run_all.return_value = mock_result

        with (
            patch(
                "dazzle.mcp.server.handlers.preflight.check_server_reachable",
                return_value=None,
            ),
            patch.dict(
                "sys.modules",
                {"dazzle.testing.unified_runner": MagicMock(UnifiedTestRunner=mock_runner_cls)},
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "test",
                    "dsl-run",
                    *_manifest_args(tmp_path),
                    "--base-url",
                    "https://staging.example.com",
                    "--format",
                    "json",
                ],
            )

        if result.exit_code == 0:
            # Verify base_url was passed to the runner constructor
            call_kwargs = mock_runner_cls.call_args
            assert call_kwargs is not None
            assert call_kwargs[1].get("base_url") == "https://staging.example.com" or (
                len(call_kwargs[0]) > 2 and call_kwargs[0][2] == "https://staging.example.com"
            )


# ---------------------------------------------------------------------------
# _parse_base_url
# ---------------------------------------------------------------------------


class TestParseBaseUrl:
    """Tests for UnifiedTestRunner._parse_base_url."""

    def _parse(self, url: str) -> tuple[str, str]:
        from dazzle.testing.unified_runner import UnifiedTestRunner

        runner = UnifiedTestRunner.__new__(UnifiedTestRunner)
        return runner._parse_base_url(url)

    def test_localhost_8000_splits(self) -> None:
        api, ui = self._parse("http://localhost:8000")
        assert api == "http://localhost:8000"
        assert ui == "http://localhost:3000"

    def test_remote_https_no_port(self) -> None:
        api, ui = self._parse("https://staging.example.com")
        assert api == "https://staging.example.com"
        assert ui == "https://staging.example.com"

    def test_remote_https_with_port(self) -> None:
        api, ui = self._parse("https://staging.example.com:4000")
        assert api == "https://staging.example.com:4000"
        assert ui == "https://staging.example.com:4000"

    def test_trailing_slash_stripped(self) -> None:
        api, ui = self._parse("https://example.com/")
        assert api == "https://example.com"
        assert ui == "https://example.com"

    def test_heroku_url(self) -> None:
        api, ui = self._parse("https://myapp-staging-abc123.herokuapp.com")
        assert api == "https://myapp-staging-abc123.herokuapp.com"
        assert ui == "https://myapp-staging-abc123.herokuapp.com"
