"""Tests for the top-level ``guide`` block parser (v0.71.0)."""

from pathlib import Path

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import Parser
from dazzle.core.lexer import tokenize


def _parse(source: str) -> ir.ModuleFragment:
    tokens = tokenize(source, Path("/tmp/test.dsl"))
    return Parser(tokens, Path("/tmp/test.dsl")).parse()


def test_parser_recognises_top_level_guide_block() -> None:
    fragment = _parse(
        """\
module my_app

guide workspace_setup "First-run setup":
  audience: persona = admin

  step create_task:
    kind: popover
    target: surface.task_list.action.create
    title: "Create your first task"
    body: "Click here to start."
    complete_on: click

  step_order: [create_task]
"""
    )
    assert len(fragment.guides) == 1
    guide = fragment.guides[0]
    assert guide.name == "workspace_setup"
    assert guide.title == "First-run setup"
    assert guide.audience == "persona = admin"
    assert guide.step_order == ["create_task"]


def test_parser_captures_step_fields() -> None:
    fragment = _parse(
        """\
module my_app

guide g1 "T":
  audience: persona = admin
  step s1:
    kind: spotlight
    target: surface.task_list
    title: "Welcome"
    body: "Take a look around."
    placement: top
    cta_label: "Got it"
    cta_target: surface.task_list
    complete_on: dismiss
  step_order: [s1]
"""
    )
    step = fragment.guides[0].steps[0]
    assert step.name == "s1"
    assert step.kind == ir.GuideStepKind.SPOTLIGHT
    assert step.target == "surface.task_list"
    assert step.title == "Welcome"
    assert step.body == "Take a look around."
    assert step.placement == "top"
    assert step.cta_label == "Got it"
    assert step.cta_target == "surface.task_list"
    assert step.complete_on.kind == ir.GuideCompleteOnKind.DISMISS


def test_parser_event_completion() -> None:
    fragment = _parse(
        """\
module my_app

guide g1 "T":
  audience: persona = admin
  step s1:
    kind: popover
    target: surface.task_list
    title: "x"
    body: "y"
    complete_on: event entity.Task.created
  step_order: [s1]
"""
    )
    co = fragment.guides[0].steps[0].complete_on
    assert co.kind == ir.GuideCompleteOnKind.EVENT
    assert co.event_ref == "entity.Task.created"


def test_parser_field_filled_completion() -> None:
    fragment = _parse(
        """\
module my_app

guide g1 "T":
  audience: persona = admin
  step s1:
    kind: popover
    target: surface.task_list
    title: "x"
    body: "y"
    complete_on: field_filled surface.task_create.field.title
  step_order: [s1]
"""
    )
    co = fragment.guides[0].steps[0].complete_on
    assert co.kind == ir.GuideCompleteOnKind.FIELD_FILLED
    assert co.field_filled == "surface.task_create.field.title"


def test_parser_on_complete_block() -> None:
    fragment = _parse(
        """\
module my_app

guide g1 "T":
  audience: persona = admin
  step s1:
    kind: popover
    target: surface.task_list
    title: "x"
    body: "y"
    complete_on: click
  step_order: [s1]
  on_complete:
    emit: event entity.Onboarding.completed
    redirect: surface.task_list
"""
    )
    oc = fragment.guides[0].on_complete
    assert oc is not None
    assert oc.emit == "entity.Onboarding.completed"
    assert oc.redirect == "surface.task_list"


def test_parser_audience_when_per_step() -> None:
    fragment = _parse(
        """\
module my_app

guide g1 "T":
  audience: persona = admin
  step s1:
    kind: popover
    target: surface.task_list
    title: "x"
    body: "y"
    complete_on: click
    audience_when: entity.Task.count = 0
  step_order: [s1]
"""
    )
    step = fragment.guides[0].steps[0]
    assert step.audience_when == "entity.Task.count = 0"


def test_parser_step_order_dash_list_form() -> None:
    fragment = _parse(
        """\
module my_app

guide g1 "T":
  audience: persona = admin
  step s1:
    kind: popover
    target: surface.task_list
    title: "x"
    body: "y"
    complete_on: click
  step s2:
    kind: popover
    target: surface.task_list
    title: "x"
    body: "y"
    complete_on: click
  step_order:
    - s1
    - s2
"""
    )
    assert fragment.guides[0].step_order == ["s1", "s2"]


def test_multiple_guides_per_module() -> None:
    fragment = _parse(
        """\
module my_app

guide g1 "T1":
  audience: persona = admin
  step s1:
    kind: popover
    target: surface.task_list
    title: "x"
    body: "y"
    complete_on: click
  step_order: [s1]

guide g2 "T2":
  audience: persona = member
  step s1:
    kind: popover
    target: surface.task_list
    title: "x"
    body: "y"
    complete_on: click
  step_order: [s1]
"""
    )
    assert [g.name for g in fragment.guides] == ["g1", "g2"]
