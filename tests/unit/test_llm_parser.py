"""Tests for LLM trigger and concurrency parser extensions."""

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.llm import LLMTriggerEvent
from dazzle.core.ir.process import StepKind

# ---------------------------------------------------------------------------
# Trigger Parsing
# ---------------------------------------------------------------------------

TRIGGER_DSL = """\
module test_triggers
app test "Test"

llm_model claude "Claude":
  provider: anthropic
  model_id: claude-3-sonnet

llm_config:
  default_model: claude

llm_intent classify_ticket "Classify Ticket":
  model: claude
  prompt: "Classify: {{ input.title }}"
  trigger:
    on_entity: Ticket
    on_event: created
    input_map:
      title: entity.title
      body: entity.description
    write_back:
      Ticket.category: output
    when: "entity.category == null"
"""


class TestTriggerParsing:
    def test_parses_trigger_on_intent(self):
        _, _, _, _, _, fragment = parse_dsl(TRIGGER_DSL, Path("test.dsl"))
        assert len(fragment.llm_intents) == 1
        intent = fragment.llm_intents[0]
        assert intent.name == "classify_ticket"
        assert len(intent.triggers) == 1

    def test_trigger_fields(self):
        _, _, _, _, _, fragment = parse_dsl(TRIGGER_DSL, Path("test.dsl"))
        trigger = fragment.llm_intents[0].triggers[0]
        assert trigger.on_entity == "Ticket"
        assert trigger.on_event == LLMTriggerEvent.CREATED

    def test_trigger_input_map(self):
        _, _, _, _, _, fragment = parse_dsl(TRIGGER_DSL, Path("test.dsl"))
        trigger = fragment.llm_intents[0].triggers[0]
        assert trigger.input_map == {
            "title": "entity.title",
            "body": "entity.description",
        }

    def test_trigger_write_back(self):
        _, _, _, _, _, fragment = parse_dsl(TRIGGER_DSL, Path("test.dsl"))
        trigger = fragment.llm_intents[0].triggers[0]
        assert trigger.write_back == {"Ticket.category": "output"}

    def test_trigger_when_condition(self):
        _, _, _, _, _, fragment = parse_dsl(TRIGGER_DSL, Path("test.dsl"))
        trigger = fragment.llm_intents[0].triggers[0]
        assert trigger.when == "entity.category == null"


MULTI_TRIGGER_DSL = """\
module test_multi
app test "Test"

llm_model claude "Claude":
  provider: anthropic
  model_id: claude-3-sonnet

llm_config:
  default_model: claude

llm_intent classify_item "Classify":
  model: claude
  prompt: "Classify: {{ input.title }}"
  trigger:
    on_entity: Ticket
    on_event: created
    input_map:
      title: entity.title
  trigger:
    on_entity: Ticket
    on_event: updated
    input_map:
      title: entity.title
    when: "entity.category == null"
"""


class TestMultipleTriggers:
    def test_parses_multiple_triggers(self):
        _, _, _, _, _, fragment = parse_dsl(MULTI_TRIGGER_DSL, Path("test.dsl"))
        intent = fragment.llm_intents[0]
        assert len(intent.triggers) == 2
        assert intent.triggers[0].on_event == LLMTriggerEvent.CREATED
        assert intent.triggers[1].on_event == LLMTriggerEvent.UPDATED


# ---------------------------------------------------------------------------
# Concurrency Parsing
# ---------------------------------------------------------------------------

CONCURRENCY_DSL = """\
module test_conc
app test "Test"

llm_model claude "Claude":
  provider: anthropic
  model_id: claude-3-sonnet

llm_config:
  default_model: claude
  rate_limits:
    claude: 60
  concurrency:
    claude: 5
"""


class TestConcurrencyParsing:
    def test_parses_concurrency(self):
        _, _, _, _, _, fragment = parse_dsl(CONCURRENCY_DSL, Path("test.dsl"))
        assert fragment.llm_config is not None
        assert fragment.llm_config.concurrency == {"claude": 5}

    def test_rate_limits_still_parsed(self):
        _, _, _, _, _, fragment = parse_dsl(CONCURRENCY_DSL, Path("test.dsl"))
        assert fragment.llm_config.rate_limits == {"claude": 60}


# ---------------------------------------------------------------------------
# Process llm_intent Step
# ---------------------------------------------------------------------------

PROCESS_LLM_STEP_DSL = """\
module test_proc
app test "Test"

llm_model claude "Claude":
  provider: anthropic
  model_id: claude-3-sonnet

llm_config:
  default_model: claude

llm_intent classify_ticket "Classify":
  model: claude
  prompt: "Classify: {{ input.title }}"

entity Ticket "Ticket":
  id: uuid pk
  title: str(200) required
  category: str(100)

process ticket_classify_flow "Classify Flow":
  trigger:
    when: entity Ticket created

  steps:
    - step run_classify:
        llm_intent: classify_ticket
        input_map:
          title: trigger.entity.title
        timeout: 30s
"""


class TestProcessLLMStep:
    def test_parses_llm_intent_step(self):
        _, _, _, _, _, fragment = parse_dsl(PROCESS_LLM_STEP_DSL, Path("test.dsl"))
        assert len(fragment.processes) == 1
        process = fragment.processes[0]
        assert len(process.steps) == 1

    def test_step_kind_is_llm_intent(self):
        _, _, _, _, _, fragment = parse_dsl(PROCESS_LLM_STEP_DSL, Path("test.dsl"))
        step = fragment.processes[0].steps[0]
        assert step.kind == StepKind.LLM_INTENT

    def test_step_llm_intent_name(self):
        _, _, _, _, _, fragment = parse_dsl(PROCESS_LLM_STEP_DSL, Path("test.dsl"))
        step = fragment.processes[0].steps[0]
        assert step.llm_intent == "classify_ticket"

    def test_step_input_map(self):
        _, _, _, _, _, fragment = parse_dsl(PROCESS_LLM_STEP_DSL, Path("test.dsl"))
        step = fragment.processes[0].steps[0]
        assert step.llm_input_map == {"title": "trigger.entity.title"}
