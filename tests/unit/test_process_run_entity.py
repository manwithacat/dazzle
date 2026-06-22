"""Tests for the auto-injected ProcessRun system entity (#1454).

ProcessRun is injected by the linker when any declared process has at least
one ``llm_intent`` step.  It provides the uuid-pk, user-anchored audit row
that a process-step AIJob will reference as its subject.
"""

import os
import tempfile
from pathlib import Path


def _build_appspec(dsl: str):
    """Parse DSL text and link into an AppSpec via build_appspec."""
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsl", delete=False) as f:
        f.write(dsl)
        f.flush()
        fpath = Path(f.name)
    try:
        modules = parse_modules([fpath])
        return build_appspec(modules, modules[0].name)
    finally:
        os.unlink(fpath)


# Minimal single-module DSL with one process that has an llm_intent step.
# Grammar notes (confirmed against parser):
#   - step kind is inferred from the keyword used, NOT via "kind: llm_intent"
#   - the input mapping sub-block is "input_map:", NOT "llm_input_map:"
#   - "classify" is a reserved keyword; step names must avoid it
_DSL = """\
module m
app a "A"

llm_config:
  default_model: m1

llm_model m1 "M1":
  provider: anthropic
  model_id: x

entity Doc "Doc":
  id: uuid pk
  body: text

process review "Review":
  steps:
    - step run_summarize:
        llm_intent: summarize
        input_map:
          text: context.body

llm_intent summarize "Summarize":
  model: m1
  prompt: "{{ input.text }}"
"""

# DSL with a process that has NO llm_intent step — ProcessRun must NOT be injected.
_DSL_NO_LLM = """\
module m
app a "A"

entity Doc "Doc":
  id: uuid pk
  body: text

process plain "Plain":
  steps:
    - step do_work:
        service: some_service
"""


def test_process_run_injected_when_process_has_llm_step():
    """ProcessRun is auto-injected when any process has an llm_intent step."""
    appspec = _build_appspec(_DSL)
    pr = next((e for e in appspec.domain.entities if e.name == "ProcessRun"), None)
    assert pr is not None, "ProcessRun must be injected when a process has an llm_intent step"

    names = {f.name for f in pr.fields}
    assert {"id", "process_name", "status", "started_by", "started_at"} <= names, (
        f"Expected core fields in ProcessRun; got: {names}"
    )

    idf = next(f for f in pr.fields if f.name == "id")
    assert idf.type.kind.value == "uuid", (
        f"id field must be uuid pk; got kind={idf.type.kind.value!r}"
    )


def test_process_run_not_injected_without_llm_step():
    """ProcessRun must NOT be injected when no process has an llm_intent step."""
    appspec = _build_appspec(_DSL_NO_LLM)
    pr = next((e for e in appspec.domain.entities if e.name == "ProcessRun"), None)
    assert pr is None, "ProcessRun must NOT be injected when no process has an llm_intent step"


def test_process_run_fields_complete():
    """ProcessRun carries all declared fields from PROCESS_RUN_FIELDS."""
    appspec = _build_appspec(_DSL)
    pr = next(e for e in appspec.domain.entities if e.name == "ProcessRun")

    names = {f.name for f in pr.fields}
    expected = {
        "id",
        "process_name",
        "status",
        "started_by",
        "current_step",
        "started_at",
        "finished_at",
        "error_message",
        "created_at",
    }
    assert names == expected, f"Field mismatch — got: {names}, expected: {expected}"

    status_field = next(f for f in pr.fields if f.name == "status")
    assert status_field.type.kind.value == "enum", "status must be an enum type"
    assert set(status_field.type.enum_values) == {
        "pending",
        "running",
        "completed",
        "failed",
    }
    assert status_field.default == "pending", "status default must be 'pending'"
