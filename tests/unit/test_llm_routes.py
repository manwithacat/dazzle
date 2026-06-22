"""Unit tests for LLM routes."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec
from dazzle.core.ir.llm import LLMConfigSpec, LLMIntentSpec, LLMModelSpec, LLMProvider
from dazzle.http.runtime.llm_executor import LLMIntentExecutor
from dazzle.http.runtime.llm_routes import create_llm_routes


def _make_app() -> tuple[FastAPI, LLMIntentExecutor]:
    model = LLMModelSpec(name="m1", provider=LLMProvider.ANTHROPIC, model_id="claude-3")
    intent = LLMIntentSpec(
        name="summarize",
        model_ref="m1",
        prompt_template="Summarise: $text",
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
