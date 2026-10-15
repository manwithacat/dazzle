"""Unit tests for the Fragment coverage audit."""

import json

import pytest

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


def _make_appspec(surfaces: list[SurfaceSpec], entities: list[EntitySpec] | None = None) -> AppSpec:
    """Build a minimal AppSpec — the audit only consults surfaces (+ entities
    for field-type resolution)."""
    return AppSpec(
        name="test",
        title="Test App",
        domain=DomainSpec(entities=entities or []),
        surfaces=surfaces,
    )


def test_blocker_kind_enum_values() -> None:
    """Each blocker kind names a structural reason an adapter can't render
    a surface. Adding a new failure mode means adding to the enum."""
    expected = {
        "unsupported_mode",
        "unsupported_field_type",
        "unsupported_feature",
        "unsupported_display",
    }
    assert {k.value for k in BlockerKind} == expected


@pytest.mark.parametrize(
    ("blockers", "ready"),
    [
        pytest.param((), True, id="no-blockers-ready"),
        pytest.param(
            (Blocker(kind=BlockerKind.UNSUPPORTED_MODE, detail="VIEW"),),
            False,
            id="blockers-present-not-ready",
        ),
    ],
)
def test_surface_coverage_is_ready(blockers: tuple[Blocker, ...], ready: bool) -> None:
    assert SurfaceCoverage(name="s", mode="LIST", blockers=blockers).is_ready is ready


def _task_with_file_field() -> EntitySpec:
    return EntitySpec(
        name="Task",
        fields=[
            FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
            FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR, max_length=200)),
            FieldSpec(name="attachment", type=FieldType(kind=FieldTypeKind.FILE)),
        ],
    )


@pytest.mark.parametrize(
    ("surface", "entities", "expected_blocker"),
    [
        # A LIST surface with no display / related_groups / companions renders;
        # an unset `display:` uses the mode's natural rendering (LIST → Table).
        pytest.param(SurfaceSpec(name="task_list", mode=SurfaceMode.LIST), [], None, id="list"),
        # `display: list` is the explicit form of the default.
        pytest.param(
            SurfaceSpec(name="task_list", mode=SurfaceMode.LIST, display="list"),
            [],
            None,
            id="explicit-list-display",
        ),
        # Plan 8: VIEW mode is supported.
        pytest.param(
            SurfaceSpec(name="task_detail", mode=SurfaceMode.VIEW), [], None, id="view-mode"
        ),
        # Plan 10: related_groups are supported.
        pytest.param(
            SurfaceSpec(
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
            ),
            [],
            None,
            id="related-groups",
        ),
        # No entity_ref → field-type resolution is skipped, not raised.
        pytest.param(
            SurfaceSpec(name="dashboard", mode=SurfaceMode.LIST, entity_ref=None, sections=[]),
            [],
            None,
            id="no-entity-ref-skips-field-resolution",
        ),
        # A stale entity_ref must not crash the audit (the linker flags it).
        pytest.param(
            SurfaceSpec(
                name="x",
                mode=SurfaceMode.LIST,
                entity_ref="NoSuchEntity",
                sections=[
                    SurfaceSection(
                        name="main", elements=[SurfaceElement(field_name="any", label="Any")]
                    ),
                ],
            ),
            [],
            None,
            id="unknown-entity-ref-skips-field-resolution",
        ),
        # #1033 (v0.66.140): the `file` field type renders via FileUpload.
        pytest.param(
            SurfaceSpec(
                name="task_create",
                mode=SurfaceMode.CREATE,
                entity_ref="Task",
                sections=[
                    SurfaceSection(
                        name="main",
                        elements=[
                            SurfaceElement(field_name="title", label="Title"),
                            SurfaceElement(field_name="attachment", label="Attachment"),
                        ],
                    )
                ],
            ),
            [_task_with_file_field()],
            None,
            id="file-field-supported-1033",
        ),
        # Plan 9 added CREATE+EDIT; CUSTOM remains unsupported.
        pytest.param(
            SurfaceSpec(name="task_custom", mode=SurfaceMode.CUSTOM),
            [],
            ("unsupported_mode", "CUSTOM"),
            id="custom-mode-blocked",
        ),
        # Phase 4A: an undispatched `display:` is flagged instead of silently
        # rendering as a Table (Plan-13-class under-reporting).
        pytest.param(
            SurfaceSpec(name="metrics_chart", mode=SurfaceMode.LIST, display="not_a_real_mode"),
            [],
            ("unsupported_display", "not_a_real_mode"),
            id="unknown-display-blocked",
        ),
    ],
)
def test_audit_single_surface(
    surface: SurfaceSpec,
    entities: list[EntitySpec],
    expected_blocker: tuple[str, str] | None,
) -> None:
    report = audit_appspec(_make_appspec([surface], entities))
    blockers = [(b.kind.value, b.detail) for b in report.surfaces[0].blockers]
    if expected_blocker is None:
        assert (report.ready_count, report.blocked_count, blockers) == (1, 0, [])
    else:
        assert (report.ready_count, report.blocked_count) == (0, 1)
        assert expected_blocker in blockers


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


def test_audit_classifies_framework_injected_surfaces() -> None:
    """Cyfuture pilot ask: distinguish declared surfaces from framework-
    injected ones (`_admin_` / `_platform_` names, see admin_builder.py).
    The JSON carries `source` so consumers can filter framework noise."""
    declared = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST)
    injected = SurfaceSpec(name="_admin_health", mode=SurfaceMode.LIST)
    report = audit_appspec(_make_appspec([declared, injected]))
    expected = {"task_list": "declared", "_admin_health": "framework_injected"}
    assert {s.name: s.source for s in report.surfaces} == expected
    payload = json.loads(report.to_json())
    assert {s["name"]: s["source"] for s in payload["surfaces"]} == expected


# ─────── Workspace-region walking (Phase 4A) ─────────────────────


def test_audit_walks_workspace_regions_and_flags_unsupported_display() -> None:
    """v0.66.59: the audit walks `appspec.workspaces[*].regions[*]` and
    emits a coverage entry per region (named `<workspace>.<region>`,
    mode='REGION'). Regions with non-default display are flagged."""
    from dazzle.core.ir.workspaces import (
        DisplayMode,
        WorkspaceRegion,
        WorkspaceSpec,
    )

    region_bar = WorkspaceRegion(
        name="metrics_chart",
        source="Metric",
        display=DisplayMode.BAR_CHART,
    )
    region_list = WorkspaceRegion(
        name="task_list",
        source="Task",
        display=DisplayMode.LIST,
    )
    workspace = WorkspaceSpec(
        name="my_workspace",
        title="My Workspace",
        regions=[region_bar, region_list],
    )
    appspec = AppSpec(
        name="t",
        title="T",
        domain=DomainSpec(entities=[]),
        surfaces=[],
        workspaces=[workspace],
    )
    report = audit_appspec(appspec)
    by_name = {s.name: s for s in report.surfaces}
    assert "my_workspace.metrics_chart" in by_name
    assert "my_workspace.task_list" in by_name
    # bar_chart is supported
    bar_entry = by_name["my_workspace.metrics_chart"]
    assert bar_entry.is_ready
    assert bar_entry.mode == "REGION"
    # List is supported; ready
    list_entry = by_name["my_workspace.task_list"]
    assert list_entry.is_ready


def test_audit_workspace_region_source_classification() -> None:
    """Framework workspaces (_admin_* / _platform_*) flag regions as
    framework_injected for the consumer-noise filter."""
    from dazzle.core.ir.workspaces import (
        DisplayMode,
        WorkspaceRegion,
        WorkspaceSpec,
    )

    framework_ws = WorkspaceSpec(
        name="_platform_admin",
        title="Platform Admin",
        regions=[
            WorkspaceRegion(name="r", source="X", display=DisplayMode.LIST),
        ],
    )
    user_ws = WorkspaceSpec(
        name="my_dashboard",
        title="My Dashboard",
        regions=[
            WorkspaceRegion(name="r", source="X", display=DisplayMode.LIST),
        ],
    )
    appspec = AppSpec(
        name="t",
        title="T",
        domain=DomainSpec(entities=[]),
        surfaces=[],
        workspaces=[framework_ws, user_ws],
    )
    report = audit_appspec(appspec)
    by_name = {s.name: s for s in report.surfaces}
    assert by_name["_platform_admin.r"].source == "framework_injected"
    assert by_name["my_dashboard.r"].source == "declared"


def test_audit_dedupes_same_field_type_across_elements() -> None:
    """The dedup mechanism: when N elements reference the same
    unsupported field type, the audit produces ONE blocker per type,
    not N (cross-surface aggregation handles count rollups).

    Issue #1033 closure emptied `_UNSUPPORTED_FIELD_TYPES`, so this
    test exercises the seam by monkeypatching a sentinel into the
    set. The dedup logic itself is unchanged and worth pinning for
    when future field-type restrictions land."""
    import dazzle.render.fragment.coverage as _cov

    task = EntitySpec(
        name="Task",
        fields=[
            FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
            # Three fields with the sentinel type — the audit normalises
            # FieldType.kind via str(...).lower() so we can pass an
            # untyped string sentinel through `extra` to fake an
            # unsupported type without polluting the real type system.
            FieldSpec(name="a", type=FieldType(kind=FieldTypeKind.STR)),
            FieldSpec(name="b", type=FieldType(kind=FieldTypeKind.STR)),
            FieldSpec(name="c", type=FieldType(kind=FieldTypeKind.STR)),
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
        domain=DomainSpec(entities=[task]),
        surfaces=[surface],
    )
    # Patch in `str` as the sentinel-unsupported type for the duration
    # of the test, then restore.
    original = _cov._UNSUPPORTED_FIELD_TYPES
    _cov._UNSUPPORTED_FIELD_TYPES = frozenset({"str"})
    try:
        report = audit_appspec(appspec)
        str_count = sum(
            1
            for b in report.surfaces[0].blockers
            if b.kind.value == "unsupported_field_type" and b.detail == "str"
        )
        # Three str fields → one blocker (dedupe).
        assert str_count == 1
    finally:
        _cov._UNSUPPORTED_FIELD_TYPES = original


# ─────── Adapter ↔ coverage drift gate ─────────────────────


def test_supported_displays_match_adapter() -> None:
    """coverage._SUPPORTED_DISPLAYS must equal the union of every
    display value the adapter dispatches on. Drift between the two
    files is the recurring class of bug the dispatch refactor fixed.

    Adding a display in either file without the other gets caught here.
    """
    from dazzle.render.fragment.coverage import _SUPPORTED_DISPLAYS
    from dazzle.render.fragment.region import WorkspaceRegionAdapter

    adapter_displays = set(WorkspaceRegionAdapter._BUILDERS.keys()) | set(
        WorkspaceRegionAdapter._ALIASES.keys()
    )
    audit_displays = set(_SUPPORTED_DISPLAYS)

    only_in_audit = audit_displays - adapter_displays
    only_in_adapter = adapter_displays - audit_displays
    assert not only_in_audit and not only_in_adapter, (
        "Drift between coverage._SUPPORTED_DISPLAYS and adapter dispatch: "
        f"only_in_audit={sorted(only_in_audit)}, "
        f"only_in_adapter={sorted(only_in_adapter)}"
    )
