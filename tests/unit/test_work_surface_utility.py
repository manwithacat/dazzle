"""Gate: work-surface utility ontology is loadable and covers core stems."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.qa.work_surface_utility import (
    load_ontology,
    ontology_path,
    residual,
    scan_project,
    summary,
    surfaces_from_ontology,
)

pytestmark = pytest.mark.gate

_REQUIRED_IDS = frozenset(
    {
        "kanban",
        "timeline",
        "day_timeline",
        "task_inbox",
        "queue",
        "list",
        "activity_feed",
        "status_list",
    }
)


def test_ontology_file_exists() -> None:
    assert ontology_path().is_file()


def test_ontology_loads_required_surfaces() -> None:
    data = load_ontology()
    assert int(data.get("version") or 0) >= 1
    surfaces = surfaces_from_ontology(data)
    ids = {s.id for s in surfaces}
    missing = _REQUIRED_IDS - ids
    assert not missing, f"ontology missing surfaces: {sorted(missing)}"
    for s in surfaces:
        assert s.job.strip(), f"{s.id} needs job"
        assert s.use_when, f"{s.id} needs use_when"
        assert s.utility_axes, f"{s.id} needs utility_axes"
        assert s.measure_proxy.strip(), f"{s.id} needs measure_proxy"


def test_measurement_block_present() -> None:
    data = load_ontology()
    m = data.get("measurement") or {}
    assert "method" in m
    assert m.get("success_criteria")


def test_scan_simple_task_runs() -> None:
    project = Path("examples/simple_task")
    if not project.is_dir():
        pytest.skip("simple_task example missing")
    findings = scan_project(project, app_name="simple_task")
    sm = summary(findings)
    assert sm["count"] >= 0
    # residual is non-negative; unknown displays are ok to report
    assert residual(findings) >= 0
