"""Unit tests for the Fragment coverage audit."""

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec
from dazzle.core.ir.surfaces import (
    RelatedDisplayMode,
    RelatedGroup,
    SurfaceMode,
    SurfaceSpec,
)
from dazzle.render.fragment.coverage import (
    Blocker,
    BlockerKind,
    CoverageReport,
    SurfaceCoverage,
    audit_appspec,
)


def _make_appspec(surfaces: list[SurfaceSpec]) -> AppSpec:
    """Build a minimal AppSpec — the audit only consults surfaces."""
    return AppSpec(
        name="test",
        title="Test App",
        domain=DomainSpec(entities=[]),
        surfaces=surfaces,
    )


def test_blocker_kind_enum_values() -> None:
    """Each blocker kind names a structural reason an adapter can't render
    a surface. Adding a new failure mode means adding to the enum."""
    expected = {
        "unsupported_mode",
        "unsupported_field_type",
        "unsupported_feature",
    }
    assert {k.value for k in BlockerKind} == expected


def test_blocker_dataclass() -> None:
    b = Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail="VIEW")
    assert b.kind == BlockerKind.UNSUPPORTED_MODE
    assert b.detail == "VIEW"


def test_surface_coverage_ready_when_no_blockers() -> None:
    sc = SurfaceCoverage(name="task_list", mode="LIST", blockers=())
    assert sc.is_ready


def test_surface_coverage_blocked_when_blockers_present() -> None:
    sc = SurfaceCoverage(
        name="task_detail",
        mode="VIEW",
        blockers=(Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail="VIEW"),),
    )
    assert not sc.is_ready


def test_audit_marks_simple_list_as_ready() -> None:
    """A LIST-mode surface with no related_groups, no companions is renderable."""
    surface = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST)
    report = audit_appspec(_make_appspec([surface]))
    assert report.ready_count == 1
    assert report.blocked_count == 0
    assert report.surfaces[0].is_ready


def test_audit_marks_view_mode_as_blocked() -> None:
    """VIEW mode is not yet supported by the adapter."""
    surface = SurfaceSpec(name="task_detail", mode=SurfaceMode.VIEW)
    report = audit_appspec(_make_appspec([surface]))
    assert report.ready_count == 0
    assert report.blocked_count == 1
    blockers = report.surfaces[0].blockers
    assert any(b.kind.value == "unsupported_mode" and b.detail == "VIEW" for b in blockers)


def test_audit_marks_related_groups_as_blocked() -> None:
    """A LIST surface with related_groups uses an unsupported feature."""
    surface = SurfaceSpec(
        name="x",
        mode=SurfaceMode.LIST,
        related_groups=[
            RelatedGroup(
                name="comments",
                entity_ref="Comment",
                display=RelatedDisplayMode.TABLE,
                show=[],
            ),
        ],
    )
    report = audit_appspec(_make_appspec([surface]))
    assert report.blocked_count == 1
    blockers = report.surfaces[0].blockers
    assert any(
        b.kind.value == "unsupported_feature" and b.detail == "related_groups" for b in blockers
    )


def test_audit_aggregates_across_surfaces() -> None:
    """Three surfaces, two blocked on VIEW mode — count is 2."""
    surfaces = [
        SurfaceSpec(name="a", mode=SurfaceMode.VIEW),
        SurfaceSpec(name="b", mode=SurfaceMode.VIEW),
        SurfaceSpec(name="c", mode=SurfaceMode.LIST),
    ]
    report = audit_appspec(_make_appspec(surfaces))
    assert report.ready_count == 1
    assert report.blocked_count == 2
    assert report.aggregated_blockers[("unsupported_mode", "VIEW")] == 2


def test_coverage_report_aggregates() -> None:
    a = SurfaceCoverage(name="task_list", mode="LIST", blockers=())
    b = SurfaceCoverage(
        name="task_detail",
        mode="VIEW",
        blockers=(Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail="VIEW"),),
    )
    c = SurfaceCoverage(
        name="task_create",
        mode="CREATE",
        blockers=(Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail="CREATE"),),
    )
    report = CoverageReport(surfaces=(a, b, c))
    assert report.ready_count == 1
    assert report.blocked_count == 2
    assert report.aggregated_blockers == {
        ("unsupported_mode", "VIEW"): 1,
        ("unsupported_mode", "CREATE"): 1,
    }


def test_coverage_report_to_text_basic_shape() -> None:
    surfaces = [
        SurfaceSpec(name="task_list", mode=SurfaceMode.LIST),
        SurfaceSpec(name="task_detail", mode=SurfaceMode.VIEW),
    ]
    report = audit_appspec(_make_appspec(surfaces))
    text = report.to_text()
    assert "Coverage:" in text
    assert "1 / 2" in text
    assert "task_list" in text
    assert "task_detail" in text
    assert "✓" in text
    assert "✗" in text
    assert "unsupported_mode" in text


def test_coverage_report_to_json_shape() -> None:
    import json

    surfaces = [
        SurfaceSpec(name="task_list", mode=SurfaceMode.LIST),
        SurfaceSpec(name="task_detail", mode=SurfaceMode.VIEW),
    ]
    report = audit_appspec(_make_appspec(surfaces))
    payload = json.loads(report.to_json())
    assert payload["ready_count"] == 1
    assert payload["blocked_count"] == 1
    assert payload["total"] == 2
    by_name = {s["name"]: s for s in payload["surfaces"]}
    assert by_name["task_list"]["is_ready"] is True
    assert by_name["task_list"]["mode"] == "LIST"
    assert by_name["task_list"]["blockers"] == []
    assert by_name["task_detail"]["is_ready"] is False
    assert by_name["task_detail"]["mode"] == "VIEW"
    assert {"kind": "unsupported_mode", "detail": "VIEW"} in by_name["task_detail"]["blockers"]
    assert payload["aggregated_blockers"][0] == {
        "kind": "unsupported_mode",
        "detail": "VIEW",
        "count": 1,
    }
