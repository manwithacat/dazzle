"""Tests for runtime parameter MCP handlers and CLI commands."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from dazzle.core.ir.params import ParamConstraints, ParamSpec

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_appspec_with_params(params: list[ParamSpec]) -> MagicMock:
    appspec = MagicMock()
    appspec.params = params
    return appspec


SAMPLE_PARAMS = [
    ParamSpec(
        key="heatmap.rag.thresholds",
        param_type="list[float]",
        default=[0.3, 0.6, 0.9],
        scope="tenant",
        constraints=ParamConstraints(
            min_length=1,
            max_length=10,
            ordered="ascending",
            range=[0.0, 1.0],
        ),
        description="RAG heatmap thresholds",
        category="heatmap",
    ),
    ParamSpec(
        key="max_retries",
        param_type="int",
        default=3,
        scope="system",
        constraints=ParamConstraints(min_value=1, max_value=10),
    ),
]


# ---------------------------------------------------------------------------
# MCP handler tests
# ---------------------------------------------------------------------------


class TestParamListHandler:
    """Tests for param_list_handler."""

    def test_empty_params(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.handlers.param import param_list_handler

        appspec = _make_appspec_with_params([])
        with patch(
            "dazzle.mcp.server.handlers.param.load_project_appspec",
            return_value=appspec,
        ):
            raw = param_list_handler(tmp_path, {})
        result = json.loads(raw)
        assert result["total"] == 0
        assert result["params"] == []

    def test_returns_all_params(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.handlers.param import param_list_handler

        appspec = _make_appspec_with_params(SAMPLE_PARAMS)
        with patch(
            "dazzle.mcp.server.handlers.param.load_project_appspec",
            return_value=appspec,
        ):
            raw = param_list_handler(tmp_path, {})
        result = json.loads(raw)
        assert result["total"] == 2
        assert len(result["params"]) == 2
        keys = [p["key"] for p in result["params"]]
        assert "heatmap.rag.thresholds" in keys
        assert "max_retries" in keys


class TestParamGetHandler:
    """Tests for param_get_handler."""

    def test_missing_key_arg(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.handlers.param import param_get_handler

        appspec = _make_appspec_with_params(SAMPLE_PARAMS)
        with patch(
            "dazzle.mcp.server.handlers.param.load_project_appspec",
            return_value=appspec,
        ):
            raw = param_get_handler(tmp_path, {})
        result = json.loads(raw)
        assert "error" in result

    def test_unknown_key(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.handlers.param import param_get_handler

        appspec = _make_appspec_with_params(SAMPLE_PARAMS)
        with patch(
            "dazzle.mcp.server.handlers.param.load_project_appspec",
            return_value=appspec,
        ):
            raw = param_get_handler(tmp_path, {"key": "nonexistent"})
        result = json.loads(raw)
        assert "error" in result
        assert "nonexistent" in result["error"]

    def test_known_key_returns_spec(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.handlers.param import param_get_handler

        appspec = _make_appspec_with_params(SAMPLE_PARAMS)
        with patch(
            "dazzle.mcp.server.handlers.param.load_project_appspec",
            return_value=appspec,
        ):
            raw = param_get_handler(tmp_path, {"key": "max_retries"})
        result = json.loads(raw)
        assert result["key"] == "max_retries"
        assert result["param_type"] == "int"
        assert result["default"] == 3
        assert result["scope"] == "system"

    def test_known_key_with_constraints(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.handlers.param import param_get_handler

        appspec = _make_appspec_with_params(SAMPLE_PARAMS)
        with patch(
            "dazzle.mcp.server.handlers.param.load_project_appspec",
            return_value=appspec,
        ):
            raw = param_get_handler(tmp_path, {"key": "heatmap.rag.thresholds"})
        result = json.loads(raw)
        assert result["key"] == "heatmap.rag.thresholds"
        assert result["param_type"] == "list[float]"
        assert result["default"] == [0.3, 0.6, 0.9]
        assert result["constraints"]["ordered"] == "ascending"
        assert result["description"] == "RAG heatmap thresholds"
