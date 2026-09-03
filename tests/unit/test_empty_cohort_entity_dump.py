"""Cohort-strip empty must not dump generic 'No members in this view.' (oral #226)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.ir.workspaces import CohortStripConfig, CohortStripLens
from dazzle.core.project import load_project
from dazzle.render.breadcrumbs import (
    clerk_empty_cohort_title,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_cards import _BuildersCardsMixin

OPS = Path("examples/ops_dashboard")
HR = Path("examples/hr_records")
OPS_DSL = OPS / "dsl" / "app.dsl"


class _A(_BuildersCardsMixin):
    pass


def _cfg() -> CohortStripConfig:
    return CohortStripConfig(
        member_via="id",
        default_lens="status",
        lenses=[CohortStripLens(id="status", label="Status", primary="status")],
    )


def _region(**overrides: object) -> object:
    base: dict[str, object] = {
        "name": "systems_strip",
        "title": "Systems strip",
        "empty_message": None,
        "source": "System",
        "cohort_strip_config": _cfg(),
    }
    base.update(overrides)
    return type("R", (), base)()


def _render_cohort(region: object, ctx: dict[str, object] | None = None) -> str:
    payload = {"cohort_cells": [], "cohort_endpoint": "/r/systems_strip"}
    payload.update(ctx or {})
    return FragmentRenderer().render(_A()._build_cohort_strip(region, payload))


def test_ops_systems_strip_is_live() -> None:
    block = OPS_DSL.read_text()
    region = block.split("  systems_strip:", 1)[1].split("  ops_today:", 1)[0]
    assert "display: cohort_strip" in region
    assert "source: System" in region
    assert "empty:" not in region


def test_clerk_empty_cohort_title_splits_pascal_and_catalog() -> None:
    spec = load_project(OPS)
    system = next(e for e in spec.domain.entities if e.name == "System")
    assert system.title == "System"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("System", labels) == "System"
    assert clerk_entity_confirm_noun("System", labels) == "system"
    assert clerk_empty_cohort_title("System", labels) == "No systems in this view."
    assert clerk_empty_cohort_title("System") == "No systems in this view."


def test_clerk_empty_cohort_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_cohort_title(junk) == "No members in this view."


def test_hr_department_cohort_is_departments() -> None:
    spec = load_project(HR)
    dept = next(e for e in spec.domain.entities if e.name == "Department")
    assert dept.title == "Department"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_empty_cohort_title("Department", labels) == "No departments in this view."


def test_cohort_empty_is_systems_not_no_members() -> None:
    html = _render_cohort(_region())
    assert "dz-cohort-strip-empty" in html
    assert "No systems in this view." in html
    assert "No members in this view." not in html
    assert "No systemss" not in html


def test_cohort_empty_ctx_source_entity_still_splits() -> None:
    html = _render_cohort(_region(source=""), {"source_entity": "System"})
    assert "No systems in this view." in html
    assert "No members in this view." not in html


def test_cohort_empty_missing_entity_stays_no_members() -> None:
    html = _render_cohort(_region(source=""))
    assert "No members in this view." in html
    assert "No systems" not in html


def test_cohort_empty_leftover_invents_no_collection() -> None:
    html = _render_cohort(_region(source="zzz"))
    assert "No members in this view." in html
    assert "No zzz" not in html


def test_cohort_empty_card_title_item_fallback_does_not_invent() -> None:
    html = _render_cohort(_region(source="System"), {"entity_name": "Item"})
    assert "No systems in this view." in html
    assert "No members in this view." not in html


def test_cohort_authored_empty_still_wins() -> None:
    html = _render_cohort(_region(empty_message="No systems on this lens"))
    assert "No systems on this lens" in html
    assert "No members in this view." not in html
    assert "No systems in this view." not in html


def test_cohort_populated_still_renders_members() -> None:
    html = _render_cohort(
        _region(),
        {
            "cohort_cells": [
                {
                    "member_id": "s1",
                    "member_name": "api-gateway",
                    "primary_value": "healthy",
                }
            ],
        },
    )
    assert "api-gateway" in html
    assert "No members in this view." not in html
    assert "No systems in this view." not in html
