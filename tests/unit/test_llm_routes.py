"""Unit tests for LLM routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec
from dazzle.core.ir.llm import LLMConfigSpec, LLMIntentSpec, LLMModelSpec, LLMProvider
from dazzle_back.runtime.llm_executor import ExecutionResult, LLMIntentExecutor
from dazzle_back.runtime.llm_routes import create_llm_routes


def _make_app() -> tuple[FastAPI, LLMIntentExecutor]:
    model = LLMModelSpec(name="m1", provider=LLMProvider.ANTHROPIC, model_id="claude-3")
    intent = LLMIntentSpec(
        name="summarize",
        model_ref="m1",
        prompt_template="Summarise: {{ input.text }}",
        description="Summarise text",
    )
    appspec = AppSpec(
        module_name="test",
        name="test",
        domain=DomainSpec(),
        llm_models=[model],
        llm_intents=[intent],
        llm_config=LLMConfigSpec(default_model="m1"),
    )
    executor = LLMIntentExecutor(appspec)
    app = FastAPI()
    app.include_router(create_llm_routes(executor))
    return app, executor


class TestLLMRoutes:
    def test_get_intents(self) -> None:
        app, _ = _make_app()
        client = TestClient(app)
        resp = client.get("/_dazzle/llm/intents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "summarize"

    def test_get_models(self) -> None:
        app, _ = _make_app()
        client = TestClient(app)
        resp = client.get("/_dazzle/llm/models")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "m1"

    def test_execute_success(self) -> None:
        app, executor = _make_app()
        client = TestClient(app)

        mock_result = ExecutionResult(success=True, output="Summary here", duration_ms=42)

        with patch.object(executor, "execute", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post(
                "/_dazzle/llm/execute/summarize",
                json={"input_data": {"text": "hello"}},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["output"] == "Summary here"

    def test_execute_unknown_intent(self) -> None:
        app, executor = _make_app()
        client = TestClient(app)

        mock_result = ExecutionResult(success=False, error="Unknown intent: nonexistent")

        with patch.object(executor, "execute", new_callable=AsyncMock, return_value=mock_result):
            resp = client.post(
                "/_dazzle/llm/execute/nonexistent",
                json={"input_data": {}},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "Unknown intent" in data["error"]

    def test_execute_with_user_id(self) -> None:
        app, executor = _make_app()
        client = TestClient(app)

        mock_result = ExecutionResult(success=True, output="ok")

        with patch.object(
            executor, "execute", new_callable=AsyncMock, return_value=mock_result
        ) as mock_exec:
            resp = client.post(
                "/_dazzle/llm/execute/summarize",
                json={"input_data": {"text": "x"}, "user_id": "user-1"},
            )

        assert resp.status_code == 200
        mock_exec.assert_called_once_with("summarize", {"text": "x"}, user_id="user-1")
