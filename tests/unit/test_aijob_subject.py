"""Tests for AIJob.subject required poly_ref over derived cognition surface (#1454).

Task 2: AIJob.entity_type/entity_id are removed; a required poly_ref `subject`
is derived from llm_intent triggers + process llm_intent steps (ProcessRun).
E_AIJOB_NO_SUBJECT_SURFACE fires when llm_config is present but no surface is declared.
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


# DSL with BOTH an llm_intent trigger on Doc AND a process llm_intent step.
# Targets should be {"Doc", "ProcessRun"}.
_DSL_WITH_TRIGGER_AND_PROCESS = """\
module m
app a "A"

llm_config:
  default_model: m1

llm_model m1 "M1":
  provider: anthropic
  model_id: claude-3-5-haiku-20241022

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
  trigger:
    on_entity: Doc
    on_event: created
    input_map:
      text: entity.body
"""

# DSL with only a trigger (no process llm_intent step).
# Targets should be {"Doc"} — no ProcessRun.
_DSL_TRIGGER_ONLY = """\
module m
app a "A"

llm_config:
  default_model: m1

llm_model m1 "M1":
  provider: anthropic
  model_id: claude-3-5-haiku-20241022

entity Doc "Doc":
  id: uuid pk
  body: text

llm_intent summarize "Summarize":
  model: m1
  prompt: "{{ input.text }}"
  trigger:
    on_entity: Doc
    on_event: created
    input_map:
      text: entity.body
"""

# DSL with only a process llm_intent step (no trigger).
# Targets should be {"ProcessRun"}.
_DSL_PROCESS_ONLY = """\
module m
app a "A"

llm_config:
  default_model: m1

llm_model m1 "M1":
  provider: anthropic
  model_id: claude-3-5-haiku-20241022

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

# DSL with llm_config but no trigger and no process llm_intent step.
# Should produce E_AIJOB_NO_SUBJECT_SURFACE at lint time.
_DSL_NO_SURFACE = """\
module m
app a "A"

llm_config:
  default_model: m1

llm_model m1 "M1":
  provider: anthropic
  model_id: claude-3-5-haiku-20241022

entity Doc "Doc":
  id: uuid pk
  body: text

llm_intent summarize "Summarize":
  model: m1
  prompt: "{{ input.text }}"
"""


def test_aijob_subject_is_required_polyref_over_derived_targets():
    """AIJob.subject is a required poly_ref when both trigger and process step exist."""
    appspec = _build_appspec(_DSL_WITH_TRIGGER_AND_PROCESS)
    aijob = next(e for e in appspec.domain.entities if e.name == "AIJob")
    names = {f.name for f in aijob.fields}

    assert "entity_type" not in names, "entity_type must be removed from AIJob (#1454)"
    assert "entity_id" not in names, "entity_id must be removed from AIJob (#1454)"

    subj = next(f for f in aijob.fields if f.name == "subject")
    assert subj.type.kind.value == "poly_ref", (
        f"subject must be poly_ref, got kind={subj.type.kind.value!r}"
    )
    assert "Doc" in subj.type.poly_targets, (
        f"Doc (from trigger) must be in poly_targets; got {subj.type.poly_targets}"
    )
    assert "ProcessRun" in subj.type.poly_targets, (
        f"ProcessRun (from process step) must be in poly_targets; got {subj.type.poly_targets}"
    )
    assert subj.is_required, "subject must be required (no-NULL invariant)"


def test_aijob_subject_trigger_only():
    """With trigger only (no process llm_intent step), targets = {Doc} only."""
    appspec = _build_appspec(_DSL_TRIGGER_ONLY)
    aijob = next(e for e in appspec.domain.entities if e.name == "AIJob")
    subj = next(f for f in aijob.fields if f.name == "subject")
    assert subj.type.kind.value == "poly_ref"
    assert "Doc" in subj.type.poly_targets
    assert "ProcessRun" not in subj.type.poly_targets, (
        "ProcessRun must NOT be in targets when there is no process llm_intent step"
    )
    assert subj.is_required


def test_aijob_subject_process_step_only():
    """With process llm_intent step only (no trigger), targets = {ProcessRun}."""
    appspec = _build_appspec(_DSL_PROCESS_ONLY)
    aijob = next(e for e in appspec.domain.entities if e.name == "AIJob")
    subj = next(f for f in aijob.fields if f.name == "subject")
    assert subj.type.kind.value == "poly_ref"
    assert "ProcessRun" in subj.type.poly_targets
    assert subj.is_required


def test_aijob_subject_targets_are_sorted():
    """poly_targets must be sorted (stable, deterministic schema)."""
    appspec = _build_appspec(_DSL_WITH_TRIGGER_AND_PROCESS)
    aijob = next(e for e in appspec.domain.entities if e.name == "AIJob")
    subj = next(f for f in aijob.fields if f.name == "subject")
    assert subj.type.poly_targets == sorted(subj.type.poly_targets), (
        f"poly_targets must be sorted; got {subj.type.poly_targets}"
    )


def test_e_aijob_no_subject_surface_fires_when_no_surface_declared():
    """E_AIJOB_NO_SUBJECT_SURFACE fires when llm_config is present but no subject surface exists."""
    from dazzle.core.lint import lint_appspec

    appspec = _build_appspec(_DSL_NO_SURFACE)
    errors, _warnings, _relevance = lint_appspec(appspec)
    matching = [e for e in errors if "E_AIJOB_NO_SUBJECT_SURFACE" in e]
    assert matching, f"Expected E_AIJOB_NO_SUBJECT_SURFACE error; errors were: {errors}"
