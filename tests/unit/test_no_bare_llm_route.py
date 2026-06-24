"""Guard test: the bare POST /execute/{intent_name} route must not exist.

#1454 invariant: AI runs ONLY via (a) an entity ``llm_intent`` trigger or
(b) a process ``llm_intent`` step.  The ungoverned bare-execute endpoint is
permanently removed; this test ensures it is never re-added.
"""

import pytest

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec
from dazzle.core.ir.llm import LLMConfigSpec, LLMIntentSpec, LLMModelSpec, LLMProvider
from dazzle.http.runtime.llm_executor import LLMIntentExecutor
from dazzle.http.runtime.llm_routes import create_llm_routes

pytestmark = pytest.mark.gate


def _make_router():
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
    return create_llm_routes(executor)


def test_no_generic_intent_execute_route():
    """The bare POST /execute/{intent} path must stay removed.

    AI runs only via an entity trigger or a process step (#1454).
    """
    router = _make_router()
    paths = {r.path for r in router.routes}
    assert not any("/execute/" in p for p in paths), (
        "#1454: the bare POST /execute/{intent} path must stay removed — AI runs only "
        "via an entity trigger or a process step."
    )
