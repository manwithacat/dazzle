"""CSV export must not dump generic Export CSV (oral #236)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_region_render import _stamp_list_entity_catalog
from dazzle.render.breadcrumbs import (
    clerk_csv_export_label,
    clerk_entity_download_stem,
    clerk_entity_noun,
    clerk_pagination_rows_label,
    clerk_related_create_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.fragment import URL, CsvExportButton, FragmentRenderer, ListColumn, ListRegion

SIMPLE = Path("examples/simple_task")
FIELDTEST = Path("examples/fieldtest_hub")
SIMPLE_DSL = SIMPLE / "dsl" / "app.dsl"


def _list(**overrides: object) -> ListRegion:
    base: dict[str, object] = {
        "columns": (ListColumn(key="title", label="Title"),),
        "rows": (("Buy ingredients",),),
        "csv_endpoint": "/api/tasks?format=csv",
        "csv_filename": "tasks.csv",
        "entity_name": "Task",
        "entity_title": "Task",
        "total": 1,
    }
    base.update(overrides)
    return ListRegion(**base)  # type: ignore[arg-type]


def _button(**overrides: object) -> CsvExportButton:
    base: dict[str, object] = {
        "endpoint": URL("/api/tasks?format=csv"),
        "filename": "tasks.csv",
        "entity_name": "Task",
        "entity_title": "Task",
    }
    base.update(overrides)
    return CsvExportButton(**base)  # type: ignore[arg-type]


def test_simple_task_task_list_is_live() -> None:
    block = SIMPLE_DSL.read_text()
    listing = block.split('surface task_list "Tasks":', 1)[1].split("surface ", 1)[0]
    assert "uses entity Task" in listing
    assert "mode: list" in listing
    spec = load_project(SIMPLE)
    task = next(e for e in spec.domain.entities if e.name == "Task")
    assert task.title == "Task"


def test_clerk_csv_export_label_uses_entity_noun() -> None:
    assert clerk_csv_export_label("Task") == "Export Task CSV"
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("IssueReport", labels) == "Issue Report"
    assert clerk_related_create_noun("IssueReport", labels) == "Issue Report"
    assert clerk_csv_export_label("IssueReport", labels) == "Export Issue Report CSV"
    assert clerk_csv_export_label("IssueReport") == "Export Issue Report CSV"
    assert clerk_entity_download_stem("IssueReport", labels) == "issue-report"
    assert clerk_pagination_rows_label("IssueReport", labels, total=42) == "issue reports"


def test_clerk_csv_export_label_leftover_invents_no_entity() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_csv_export_label(junk) == "Export CSV"
        assert clerk_csv_export_label(junk, {"zzz": "Issue Report"}) == "Export CSV"
    assert clerk_csv_export_label("") == "Export CSV"
    assert clerk_csv_export_label("record") == "Export CSV"
    assert clerk_csv_export_label("item") == "Export CSV"


def test_list_region_csv_is_export_task_not_export_csv() -> None:
    html = FragmentRenderer().render(_list())
    assert 'title="Export Task CSV"' in html
    assert 'aria-label="Export Task CSV"' in html
    leftover = FragmentRenderer().render(
        _list(entity_name="zzz", entity_title="zzz", csv_filename="zzz.csv")
    )
    assert 'title="Export CSV"' in leftover
    assert "Export zzz" not in leftover


def test_list_region_csv_issue_report_is_not_schema_dump() -> None:
    html = FragmentRenderer().render(
        _list(
            entity_name="IssueReport",
            entity_title="Issue Report",
            csv_filename="issue-report.csv",
        )
    )
    assert 'title="Export Issue Report CSV"' in html
    assert 'title="Export CSV"' not in html
    assert "Export IssueReport" not in html
    assert "Export issuereport" not in html


def test_stamp_list_entity_catalog_threads_source() -> None:
    out: dict[str, object] = {}
    _stamp_list_entity_catalog(
        out, SimpleNamespace(source="Task", entity_spec=SimpleNamespace(title="Task"))
    )
    assert out["entity_name"] == "Task"
    assert out["source_entity"] == "Task"
    assert out["entity_title"] == "Task"
    leftover: dict[str, object] = {}
    _stamp_list_entity_catalog(leftover, SimpleNamespace(source="zzz", entity_spec=None))
    assert leftover["entity_name"] == "zzz"
    assert "entity_title" not in leftover


def test_csv_export_button_is_export_task_not_export_csv() -> None:
    html = FragmentRenderer().render(_button())
    assert 'title="Export Task CSV"' in html
    assert 'aria-label="Export Task CSV"' in html
    leftover = FragmentRenderer().render(_button(entity_name="zzz", entity_title="zzz"))
    assert 'title="Export CSV"' in leftover
    assert "Export zzz" not in leftover
