"""Unit tests for the Fragment coverage audit."""

from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.domain import DomainSpec, EntitySpec
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.surfaces import (
    RelatedDisplayMode,
    RelatedGroup,
    SurfaceElement,
    SurfaceMode,
    SurfaceSection,
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


def test_audit_marks_custom_mode_as_blocked() -> None:
    """Plan 9 added CREATE+EDIT; CUSTOM remains unsupported (Plan 9 closure)."""
    surface = SurfaceSpec(name="task_custom", mode=SurfaceMode.CUSTOM)
    report = audit_appspec(_make_appspec([surface]))
    assert report.ready_count == 0
    assert report.blocked_count == 1
    blockers = report.surfaces[0].blockers
    assert any(b.kind.value == "unsupported_mode" and b.detail == "CUSTOM" for b in blockers)


def test_audit_marks_view_mode_as_ready() -> None:
    """Plan 8 — VIEW mode is now supported, so a VIEW surface with no
    other blockers is ready to flip."""
    surface = SurfaceSpec(name="task_detail", mode=SurfaceMode.VIEW)
    report = audit_appspec(_make_appspec([surface]))
    assert report.ready_count == 1
    assert report.blocked_count == 0


def test_audit_treats_related_groups_as_supported() -> None:
    """Plan 10 — related_groups is now supported; surfaces with it
    are not blocked on this feature alone."""
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
    assert report.ready_count == 1
    assert report.blocked_count == 0


def test_audit_aggregates_across_surfaces() -> None:
    """Three surfaces, two blocked on CREATE mode — count is 2."""
    surfaces = [
        SurfaceSpec(name="a", mode=SurfaceMode.CUSTOM),
        SurfaceSpec(name="b", mode=SurfaceMode.CUSTOM),
        SurfaceSpec(name="c", mode=SurfaceMode.LIST),
    ]
    report = audit_appspec(_make_appspec(surfaces))
    assert report.ready_count == 1
    assert report.blocked_count == 2
    assert report.aggregated_blockers[("unsupported_mode", "CUSTOM")] == 2


def test_coverage_report_aggregates() -> None:
    a = SurfaceCoverage(name="task_list", mode="LIST", blockers=())
    b = SurfaceCoverage(
        name="task_detail",
        mode="VIEW",
        blockers=(Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail="VIEW"),),
    )
    c = SurfaceCoverage(
        name="task_custom",
        mode="CUSTOM",
        blockers=(Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail="CUSTOM"),),
    )
    report = CoverageReport(surfaces=(a, b, c))
    assert report.ready_count == 1
    assert report.blocked_count == 2
    assert report.aggregated_blockers == {
        ("unsupported_mode", "VIEW"): 1,
        ("unsupported_mode", "CUSTOM"): 1,
    }


def test_coverage_report_to_text_basic_shape() -> None:
    """Mix of LIST (ready) and CREATE (blocked) — text output covers both sections."""
    surfaces = [
        SurfaceSpec(name="task_list", mode=SurfaceMode.LIST),
        SurfaceSpec(name="task_custom", mode=SurfaceMode.CUSTOM),
    ]
    report = audit_appspec(_make_appspec(surfaces))
    text = report.to_text()
    assert "Coverage:" in text
    assert "1 / 2" in text
    assert "task_list" in text
    assert "task_custom" in text
    assert "✓" in text
    assert "✗" in text
    assert "unsupported_mode" in text


def test_coverage_report_to_json_shape() -> None:
    import json

    surfaces = [
        SurfaceSpec(name="task_list", mode=SurfaceMode.LIST),
        SurfaceSpec(name="task_custom", mode=SurfaceMode.CUSTOM),
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
    assert by_name["task_custom"]["is_ready"] is False
    assert by_name["task_custom"]["mode"] == "CUSTOM"
    assert {"kind": "unsupported_mode", "detail": "CUSTOM"} in by_name["task_custom"]["blockers"]
    assert payload["aggregated_blockers"][0] == {
        "kind": "unsupported_mode",
        "detail": "CUSTOM",
        "count": 1,
    }


# ─────────────────── Plan 13 — entity-ref field resolution ───────────────────


def test_audit_flags_ref_field_via_entity_resolution() -> None:
    """A surface with a SurfaceElement pointing at a REF-typed field on
    the bound entity must report unsupported_field_type=ref. Plan 13
    closed the audit's under-reporting gap by walking entity_ref →
    domain.entities → FieldSpec.type.kind."""
    user = EntitySpec(
        name="User",
        fields=[
            FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
        ],
    )
    task = EntitySpec(
        name="Task",
        fields=[
            FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
            FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR, max_length=200)),
            FieldSpec(
                name="assigned_to",
                type=FieldType(kind=FieldTypeKind.REF, ref_entity="User"),
            ),
        ],
    )
    surface = SurfaceSpec(
        name="task_create",
        mode=SurfaceMode.CREATE,
        entity_ref="Task",
        sections=[
            SurfaceSection(
                name="main",
                elements=[
                    SurfaceElement(field_name="title", label="Title"),
                    SurfaceElement(field_name="assigned_to", label="Assigned"),
                ],
            )
        ],
    )
    appspec = AppSpec(
        name="t",
        title="T",
        domain=DomainSpec(entities=[user, task]),
        surfaces=[surface],
    )
    report = audit_appspec(appspec)
    assert report.blocked_count == 1
    blockers = report.surfaces[0].blockers
    assert any(b.kind.value == "unsupported_field_type" and b.detail == "ref" for b in blockers), (
        f"Expected ref blocker, got {[(b.kind.value, b.detail) for b in blockers]!r}"
    )


def test_audit_skips_field_resolution_when_no_entity_ref() -> None:
    """A surface without entity_ref can't be checked against an entity.
    The audit must skip field-type resolution rather than raising."""
    surface = SurfaceSpec(
        name="dashboard",
        mode=SurfaceMode.LIST,
        entity_ref=None,
        sections=[],
    )
    appspec = _make_appspec([surface])
    report = audit_appspec(appspec)
    assert report.ready_count == 1


def test_audit_skips_field_resolution_when_entity_not_found() -> None:
    """Stale entity_ref pointing at a non-existent entity must not crash
    the audit. The linker would have flagged this earlier; the audit's
    job is to be robust to malformed input, not validate it."""
    surface = SurfaceSpec(
        name="x",
        mode=SurfaceMode.LIST,
        entity_ref="NoSuchEntity",
        sections=[
            SurfaceSection(
                name="main",
                elements=[SurfaceElement(field_name="any", label="Any")],
            ),
        ],
    )
    appspec = _make_appspec([surface])
    report = audit_appspec(appspec)
    assert report.ready_count == 1


def test_audit_dedupes_same_field_type_across_elements() -> None:
    """A surface with three REF fields produces one ref blocker, not
    three — what matters is that the type is unsupported, not the count
    per surface (cross-surface aggregation handles that)."""
    user = EntitySpec(
        name="User",
        fields=[
            FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
        ],
    )
    task = EntitySpec(
        name="Task",
        fields=[
            FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
            FieldSpec(name="a", type=FieldType(kind=FieldTypeKind.REF, ref_entity="User")),
            FieldSpec(name="b", type=FieldType(kind=FieldTypeKind.REF, ref_entity="User")),
            FieldSpec(name="c", type=FieldType(kind=FieldTypeKind.REF, ref_entity="User")),
        ],
    )
    surface = SurfaceSpec(
        name="t",
        mode=SurfaceMode.LIST,
        entity_ref="Task",
        sections=[
            SurfaceSection(
                name="main",
                elements=[
                    SurfaceElement(field_name="a", label="A"),
                    SurfaceElement(field_name="b", label="B"),
                    SurfaceElement(field_name="c", label="C"),
                ],
            )
        ],
    )
    appspec = AppSpec(
        name="t",
        title="T",
        domain=DomainSpec(entities=[user, task]),
        surfaces=[surface],
    )
    report = audit_appspec(appspec)
    ref_count = sum(
        1
        for b in report.surfaces[0].blockers
        if b.kind.value == "unsupported_field_type" and b.detail == "ref"
    )
    assert ref_count == 1
