"""Queue empty must not dump generic 'Queue is empty.' (oral #225)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.breadcrumbs import (
    clerk_empty_queue_title,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_tables import _BuildersTablesMixin

TRACKER = Path("examples/project_tracker")
OPS = Path("examples/ops_dashboard")
TRACKER_DSL = TRACKER / "dsl" / "app.dsl"


class _A(_BuildersTablesMixin):
    pass


def _region(**overrides: object) -> object:
    base: dict[str, object] = {
        "name": "project_overview",
        "title": "Project overview",
        "empty_message": None,
        "source": "Project",
    }
    base.update(overrides)
    return type("R", (), base)()


def _render_queue(region: object, ctx: dict[str, object] | None = None) -> str:
    return FragmentRenderer().render(_A()._build_queue(region, ctx or {}))


def test_project_overview_queue_is_live() -> None:
    block = TRACKER_DSL.read_text()
    region = block.split("  project_overview:", 1)[1].split("  task_flow:", 1)[0]
    assert "display: queue" in region
    assert "source: Project" in region
    assert "empty:" not in region


def test_clerk_empty_queue_title_splits_pascal_and_catalog() -> None:
    spec = load_project(TRACKER)
    project = next(e for e in spec.domain.entities if e.name == "Project")
    assert project.title == "Project"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("Project", labels) == "Project"
    assert clerk_entity_confirm_noun("Project", labels) == "project"
    assert clerk_empty_queue_title("Project", labels) == "No projects in this queue."
    assert clerk_empty_queue_title("Project") == "No projects in this queue."


def test_clerk_empty_queue_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_queue_title(junk) == "Queue is empty."


def test_ops_alert_queue_is_alerts() -> None:
    spec = load_project(OPS)
    alert = next(e for e in spec.domain.entities if e.name == "Alert")
    assert alert.title == "Alert"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_empty_queue_title("Alert", labels) == "No alerts in this queue."


def test_queue_empty_is_projects_not_queue_is_empty() -> None:
    html = _render_queue(_region())
    assert "dz-queue-empty" in html
    assert "No projects in this queue." in html
    assert "Queue is empty." not in html
    assert "No projectss" not in html


def test_queue_empty_ctx_source_entity_still_splits() -> None:
    html = _render_queue(_region(source=""), {"source_entity": "Project"})
    assert "No projects in this queue." in html
    assert "Queue is empty." not in html


def test_queue_empty_missing_entity_stays_queue_is_empty() -> None:
    html = _render_queue(_region(source=""))
    assert "Queue is empty." in html
    assert "No projects" not in html


def test_queue_empty_leftover_invents_no_collection() -> None:
    html = _render_queue(_region(source="zzz"))
    assert "Queue is empty." in html
    assert "No zzz" not in html


def test_queue_empty_card_title_item_fallback_does_not_invent() -> None:
    html = _render_queue(_region(source="Project"), {"entity_name": "Item"})
    assert "No projects in this queue." in html
    assert "Queue is empty." not in html


def test_queue_authored_empty_still_wins() -> None:
    html = _render_queue(_region(empty_message="No open projects"))
    assert "No open projects" in html
    assert "Queue is empty." not in html
    assert "No projects in this queue." not in html


def test_queue_populated_still_renders_rows() -> None:
    html = _render_queue(
        _region(),
        {
            "items": [{"id": "p1", "name": "Website relaunch"}],
            "display_key": "name",
            "columns": [{"key": "name", "label": "Name"}],
        },
    )
    assert "Website relaunch" in html
    assert "Queue is empty." not in html
    assert "No projects in this queue." not in html
