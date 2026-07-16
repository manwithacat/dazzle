"""#1605 journey prove — surface hub / open-via graph (no browser)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from dazzle.agent_loop.journey_prove import journey_prove_one
from dazzle.core import ir

pytestmark = pytest.mark.gate


def _appspec_with_hub() -> ir.AppSpec:
    company = ir.EntitySpec(
        name="Company",
        title="Company",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ir.FieldSpec(name="name", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
        ],
    )
    task = ir.EntitySpec(
        name="Task",
        title="Task",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ir.FieldSpec(
                name="company",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Company"),
            ),
        ],
    )
    company_detail = ir.SurfaceSpec(
        name="company_detail",
        title="Company hub",
        entity_ref="Company",
        mode=ir.SurfaceMode.VIEW,
        sections=[
            ir.SurfaceSection(
                name="header",
                elements=[ir.SurfaceElement(field_name="name")],
            ),
            ir.SurfaceSection(
                name="compliance",
                layout="strip",
                elements=[ir.SurfaceElement(field_name="name")],
            ),
        ],
        related_groups=[
            ir.RelatedGroup(
                name="work",
                display=ir.RelatedDisplayMode.TABLE,
                show=["Task"],
            )
        ],
    )
    task_list = ir.SurfaceSpec(
        name="task_list",
        title="Tasks",
        entity_ref="Task",
        mode=ir.SurfaceMode.LIST,
        open_via="company",
        open_entity="Company",
        open_via_targets=[ir.OpenViaTarget(via="company", entity="Company")],
        sections=[
            ir.SurfaceSection(
                name="main",
                elements=[ir.SurfaceElement(field_name="company")],
            )
        ],
    )
    return ir.AppSpec(
        name="t",
        domain=ir.DomainSpec(entities=[company, task]),
        surfaces=[company_detail, task_list],
    )


def _story(story_id: str, executed_by: str) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(story_id=story_id, executed_by=executed_by, narrative_only=False)


def test_journey_view_hub_pass() -> None:
    appspec = _appspec_with_hub()
    story = _story("ST-HUB", "surface.company_detail")
    static = {
        "story_id": "ST-HUB",
        "executed_by": "surface.company_detail",
        "result": "pass_static",
        "reason": "surface_exists",
        "evidence": ["surface:company_detail"],
    }
    res = journey_prove_one(Path("."), appspec, story, static_result=static)
    assert res["result"] == "pass_journey"
    assert any("view_multi_section_hub" in e for e in res["evidence"])
    assert any("view_has_layout_strip" in e for e in res["evidence"])


def test_journey_list_open_via_pass() -> None:
    appspec = _appspec_with_hub()
    story = _story("ST-LIST", "surface.task_list")
    static = {
        "story_id": "ST-LIST",
        "executed_by": "surface.task_list",
        "result": "pass_static",
        "reason": "surface_exists",
        "evidence": ["surface:task_list"],
    }
    res = journey_prove_one(Path("."), appspec, story, static_result=static)
    assert res["result"] == "pass_journey"
    assert any("open_hop:" in e for e in res["evidence"])


def test_journey_empty_view_fails() -> None:
    appspec = _appspec_with_hub()
    empty = ir.SurfaceSpec(
        name="company_detail",
        title="Empty",
        entity_ref="Company",
        mode=ir.SurfaceMode.VIEW,
        sections=[],
    )
    appspec = appspec.model_copy(
        update={"surfaces": [empty] + [s for s in appspec.surfaces if s.name != "company_detail"]}
    )
    story = _story("ST-HUB", "surface.company_detail")
    static = {
        "story_id": "ST-HUB",
        "executed_by": "surface.company_detail",
        "result": "pass_static",
        "reason": "surface_exists",
        "evidence": [],
    }
    res = journey_prove_one(Path("."), appspec, story, static_result=static)
    assert res["result"] == "fail_journey"
    assert "view_hub_empty" in res["reason"]


def test_journey_open_via_missing_view_fails() -> None:
    appspec = _appspec_with_hub()
    appspec = appspec.model_copy(
        update={"surfaces": [s for s in appspec.surfaces if s.name != "company_detail"]}
    )
    story = _story("ST-LIST", "surface.task_list")
    static = {
        "story_id": "ST-LIST",
        "executed_by": "surface.task_list",
        "result": "pass_static",
        "reason": "surface_exists",
        "evidence": [],
    }
    res = journey_prove_one(Path("."), appspec, story, static_result=static)
    assert res["result"] == "fail_journey"
    assert "open_via_no_view_surface" in res["reason"]
