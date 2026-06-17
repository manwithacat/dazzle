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
        "unsupported_display",
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


def test_audit_marks_file_fields_as_supported() -> None:
    """Issue #1033 (v0.66.140): the `file` field type is now
    supported via the FileUpload primitive. A surface with a file
    field should be in `ready_count`, not `blocked_count`. Pre-fix
    this test asserted the opposite — `file` was in
    `_UNSUPPORTED_FIELD_TYPES` and produced a blocker; that constant
    is now empty so this test inverts to confirm the closure."""
    task = EntitySpec(
        name="Task",
        fields=[
            FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
            FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR, max_length=200)),
            FieldSpec(
                name="attachment",
                type=FieldType(kind=FieldTypeKind.FILE),
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
                    SurfaceElement(field_name="attachment", label="Attachment"),
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
    report = audit_appspec(appspec)
    assert report.ready_count == 1
    assert report.blocked_count == 0
    assert report.surfaces[0].blockers == ()


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


def test_audit_marks_admin_surface_as_framework_injected() -> None:
    """Cyfuture pilot ask: distinguish declared surfaces from framework-
    injected ones. Names starting with `_admin_` or `_platform_` are
    auto-injected by the framework (see admin_builder.py:744)."""
    declared = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST)
    injected = SurfaceSpec(name="_admin_health", mode=SurfaceMode.LIST)
    appspec = _make_appspec([declared, injected])
    report = audit_appspec(appspec)
    by_name = {s.name: s for s in report.surfaces}
    assert by_name["task_list"].source == "declared"
    assert by_name["_admin_health"].source == "framework_injected"


def test_coverage_report_to_json_includes_source_field() -> None:
    """JSON shape carries `source` per surface so consumers can filter
    framework noise out of their own coverage stats."""
    import json

    declared = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST)
    injected = SurfaceSpec(name="_admin_health", mode=SurfaceMode.LIST)
    appspec = _make_appspec([declared, injected])
    report = audit_appspec(appspec)
    payload = json.loads(report.to_json())
    by_name = {s["name"]: s for s in payload["surfaces"]}
    assert by_name["task_list"]["source"] == "declared"
    assert by_name["_admin_health"]["source"] == "framework_injected"


def test_audit_flags_unsupported_display_mode() -> None:
    """Phase 4A: surfaces with `display:` set to a value the adapter
    doesn't dispatch on are flagged. `display: kanban` on a list-mode
    surface previously rendered as a Table silently — exactly the
    Plan-13-class silent under-reporting."""
    surface = SurfaceSpec(
        name="metrics_chart",
        mode=SurfaceMode.LIST,
        display="map",
    )
    appspec = _make_appspec([surface])
    report = audit_appspec(appspec)
    assert report.blocked_count == 1
    blockers = report.surfaces[0].blockers
    assert any(b.kind.value == "unsupported_display" and b.detail == "map" for b in blockers), (
        f"Expected map blocker, got {[(b.kind.value, b.detail) for b in blockers]!r}"
    )


def test_audit_does_not_flag_empty_display() -> None:
    """The default — no `display:` set — uses the surface mode's
    natural rendering (LIST → Table). No blocker."""
    surface = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST)
    appspec = _make_appspec([surface])
    report = audit_appspec(appspec)
    assert report.ready_count == 1


def test_audit_does_not_flag_explicit_list_display() -> None:
    """`display: list` is the explicit form of the default — also
    supported."""
    surface = SurfaceSpec(name="task_list", mode=SurfaceMode.LIST, display="list")
    appspec = _make_appspec([surface])
    report = audit_appspec(appspec)
    assert report.ready_count == 1


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
        display=DisplayMode.MAP,
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
    # map is unsupported; flagged
    bar_entry = by_name["my_workspace.metrics_chart"]
    assert not bar_entry.is_ready
    assert bar_entry.mode == "REGION"
    assert any(
        b.kind.value == "unsupported_display" and b.detail == "map" for b in bar_entry.blockers
    )
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

    adapter_displays = (
        set(WorkspaceRegionAdapter._BUILDERS.keys())
        | set(WorkspaceRegionAdapter._ALIASES.keys())
        | set(WorkspaceRegionAdapter._TIMESERIES_VIEWS.keys())
    )
    audit_displays = set(_SUPPORTED_DISPLAYS)

    only_in_audit = audit_displays - adapter_displays
    only_in_adapter = adapter_displays - audit_displays
    assert not only_in_audit and not only_in_adapter, (
        "Drift between coverage._SUPPORTED_DISPLAYS and adapter dispatch: "
        f"only_in_audit={sorted(only_in_audit)}, "
        f"only_in_adapter={sorted(only_in_adapter)}"
    )
