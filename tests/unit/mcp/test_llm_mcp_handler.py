"""Unit tests for LLM MCP handler."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec
from dazzle.core.ir.llm import (
    LLMConfigSpec,
    LLMIntentSpec,
    LLMModelSpec,
    LLMProvider,
    PIIAction,
    PIIPolicySpec,
    RetryBackoff,
    RetryPolicySpec,
)
from dazzle.mcp.server.handlers.llm import (
    get_config_handler,
    inspect_intent_handler,
    list_intents_handler,
    list_models_handler,
)


def _make_appspec() -> AppSpec:
    model = LLMModelSpec(
        name="fast_model",
        title="Fast Model",
        provider=LLMProvider.ANTHROPIC,
        model_id="claude-3-haiku-20240307",
    )
    intent = LLMIntentSpec(
        name="classify",
        title="Classify Ticket",
        description="Classify a support ticket",
        model_ref="fast_model",
        prompt_template="Classify: {{ input.text }}",
        timeout_seconds=15,
        retry=RetryPolicySpec(max_attempts=2, backoff=RetryBackoff.LINEAR),
        pii=PIIPolicySpec(scan=True, action=PIIAction.REDACT),
    )
    config = LLMConfigSpec(
        default_model="fast_model",
        default_provider=LLMProvider.ANTHROPIC,
    )
    return AppSpec(
        module_name="test_llm",
        name="test_llm",
        domain=DomainSpec(),
        llm_models=[model],
        llm_intents=[intent],
        llm_config=config,
    )


@pytest.fixture()
def mock_appspec():
    appspec = _make_appspec()
    with patch(
        "dazzle.mcp.server.handlers.llm.load_project_appspec",
        return_value=appspec,
    ):
        yield appspec


class TestListIntents:
    def test_returns_intents(self, mock_appspec: AppSpec) -> None:
        result = json.loads(list_intents_handler(Path("/fake"), {}))
        assert result["count"] == 1
        assert result["intents"][0]["name"] == "classify"
        assert result["intents"][0]["has_retry"] is True
        assert result["intents"][0]["has_pii_policy"] is True


class TestListModels:
    def test_returns_models(self, mock_appspec: AppSpec) -> None:
        result = json.loads(list_models_handler(Path("/fake"), {}))
        assert result["count"] == 1
        assert result["models"][0]["name"] == "fast_model"
        assert result["models"][0]["provider"] == "anthropic"


class TestInspectIntent:
    def test_inspect_by_name(self, mock_appspec: AppSpec) -> None:
        result = json.loads(inspect_intent_handler(Path("/fake"), {"name": "classify"}))
        assert result["name"] == "classify"
        assert result["prompt_template"] == "Classify: {{ input.text }}"
        assert result["resolved_model"]["name"] == "fast_model"
        assert result["retry"]["max_attempts"] == 2
        assert result["pii"]["scan"] is True

    def test_missing_name(self, mock_appspec: AppSpec) -> None:
        result = json.loads(inspect_intent_handler(Path("/fake"), {}))
        assert "error" in result

    def test_unknown_intent(self, mock_appspec: AppSpec) -> None:
        result = json.loads(inspect_intent_handler(Path("/fake"), {"name": "nope"}))
        assert "error" in result
        assert "not found" in result["error"].lower()


class TestGetConfig:
    def test_returns_config(self, mock_appspec: AppSpec) -> None:
        result = json.loads(get_config_handler(Path("/fake"), {}))
        assert result["default_model"] == "fast_model"
        assert result["default_provider"] == "anthropic"

    def test_no_config(self) -> None:
        appspec = AppSpec(module_name="bare", name="bare", domain=DomainSpec())
        with patch(
            "dazzle.mcp.server.handlers.llm.load_project_appspec",
            return_value=appspec,
        ):
            result = json.loads(get_config_handler(Path("/fake"), {}))
        assert "error" in result
