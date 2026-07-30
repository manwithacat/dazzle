"""PersonaVariant ``action_primary`` wiring — compile + request resolve.

DSL authors declare ``for <persona>: action_primary: <surface>``.

* LIST + CREATE target → list-header Create CTA route/label.
* LIST + EDIT target → recorded only (no record id at list header).
* VIEW + CREATE target → detail primary CTA (e.g. tester device_detail →
  issue_report_create) even when Device UPDATE is denied (EX-048 VIEW).
* VIEW + EDIT target → edit route + surface title label when UPDATE ok.
"""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.ir.surfaces import SurfaceSection
from dazzle.page.app_paths import create_path, edit_path, entity_slug
from dazzle.page.converters.template_compiler import (
    _compile_list_surface,
    _compile_view_surface,
    compile_appspec_to_templates,
)


def _task_entity() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Task",
        label="Task",
        title="Task",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID), pk=True),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                required=True,
            ),
        ],
    )


def test_compile_list_resolves_create_action_primary() -> None:
    entity = _task_entity()
    list_s = ir.SurfaceSpec(
        name="task_list",
        title="Tasks",
        mode=ir.SurfaceMode.LIST,
        entity_ref="Task",
        sections=[SurfaceSection(name="main", elements=[])],
        ux=ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(persona="manager", action_primary="task_create"),
                ir.PersonaVariant(persona="member"),  # no override
            ]
        ),
    )
    create_s = ir.SurfaceSpec(
        name="task_create",
        title="Create Task",
        mode=ir.SurfaceMode.CREATE,
        entity_ref="Task",
        sections=[SurfaceSection(name="main", elements=[])],
    )
    by_name = {"task_list": list_s, "task_create": create_s}
    ctx = _compile_list_surface(
        list_s,
        entity,
        "Task",
        "/tasks",
        "task",
        "/app",
        surfaces_by_name=by_name,
    )
    assert ctx.table is not None
    assert ctx.table.persona_action_primary == {"manager": "task_create"}
    assert ctx.table.persona_create_urls == {
        "manager": create_path("/app", entity_slug("Task")),
    }
    assert ctx.table.persona_create_labels == {"manager": "Create Task"}


def test_compile_skips_edit_mode_action_primary_for_create_url() -> None:
    entity = _task_entity()
    list_s = ir.SurfaceSpec(
        name="task_list",
        title="Tasks",
        mode=ir.SurfaceMode.LIST,
        entity_ref="Task",
        sections=[SurfaceSection(name="main", elements=[])],
        ux=ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(persona="engineer", action_primary="task_edit"),
            ]
        ),
    )
    edit_s = ir.SurfaceSpec(
        name="task_edit",
        title="Edit Task",
        mode=ir.SurfaceMode.EDIT,
        entity_ref="Task",
        sections=[SurfaceSection(name="main", elements=[])],
    )
    ctx = _compile_list_surface(
        list_s,
        entity,
        "Task",
        "/tasks",
        "task",
        "/app",
        surfaces_by_name={"task_list": list_s, "task_edit": edit_s},
    )
    assert ctx.table is not None
    assert ctx.table.persona_action_primary == {"engineer": "task_edit"}
    assert ctx.table.persona_create_urls == {}
    assert ctx.table.persona_create_labels == {}


def test_apply_persona_overrides_swaps_create_url_and_label() -> None:
    from dazzle.http.runtime.page_routes import _apply_persona_overrides
    from dazzle.render.context import ColumnContext, TableContext

    table = TableContext(
        entity_name="Task",
        title="Tasks",
        api_endpoint="/tasks",
        columns=[ColumnContext(key="title", label="Title", type="text")],
        create_url="/app/task/create",
        create_label="",
        persona_create_urls={"manager": "/app/task/create"},
        persona_create_labels={"manager": "Create Task"},
    )
    _apply_persona_overrides(table, ["role_manager"])
    assert table.create_url == "/app/task/create"
    assert table.create_label == "Create Task"


def test_apply_persona_overrides_create_before_read_only_order() -> None:
    """read_only still wins when both apply (same persona)."""
    from dazzle.http.runtime.page_routes import _apply_persona_overrides
    from dazzle.render.context import ColumnContext, TableContext

    table = TableContext(
        entity_name="Task",
        title="Tasks",
        api_endpoint="/tasks",
        columns=[ColumnContext(key="title", label="Title", type="text")],
        create_url="/app/task/create",
        persona_read_only={"viewer"},
        persona_create_urls={"viewer": "/app/task/create"},
        persona_create_labels={"viewer": "Create Task"},
    )
    _apply_persona_overrides(table, ["viewer"])
    # read_only clears create_url after create override in same pass —
    # both set matched; order in helper: read_only then create. Ensure
    # read_only leaves create suppressed (read_only block sets None after
    # create would set URL if create runs last). Check actual helper order:
    # we apply create after read_only so create could re-enable — fix if so.
    # Policy: read_only must suppress create. Verify:
    assert table.create_url is None
    assert table.bulk_actions is False


def test_appspec_compile_threads_surfaces_by_name() -> None:
    appspec = ir.AppSpec(
        name="demo",
        title="Demo",
        domain=ir.DomainSpec(name="d", entities=[_task_entity()]),
        surfaces=[
            ir.SurfaceSpec(
                name="task_list",
                title="Tasks",
                mode=ir.SurfaceMode.LIST,
                entity_ref="Task",
                sections=[SurfaceSection(name="main", elements=[])],
                ux=ir.UXSpec(
                    persona_variants=[
                        ir.PersonaVariant(persona="admin", action_primary="task_create"),
                    ]
                ),
            ),
            ir.SurfaceSpec(
                name="task_create",
                title="Add Task",
                mode=ir.SurfaceMode.CREATE,
                entity_ref="Task",
                sections=[SurfaceSection(name="main", elements=[])],
            ),
        ],
    )
    contexts = compile_appspec_to_templates(appspec, app_prefix="/app")
    # Find list context by table presence
    list_ctx = next(c for c in contexts.values() if c.table is not None)
    assert list_ctx.table.persona_create_labels.get("admin") == "Add Task"
    assert list_ctx.table.persona_create_urls["admin"] == "/app/task/create"


def test_compile_view_resolves_create_action_primary() -> None:
    """device_detail as tester → issue_report_create primary CTA."""
    device = ir.EntitySpec(
        name="Device",
        label="Device",
        title="Device",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID), pk=True),
            ir.FieldSpec(
                name="name",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=100),
            ),
        ],
    )
    view_s = ir.SurfaceSpec(
        name="device_detail",
        title="Device Detail",
        mode=ir.SurfaceMode.VIEW,
        entity_ref="Device",
        sections=[SurfaceSection(name="main", elements=[])],
        ux=ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(persona="engineer", action_primary="device_edit"),
                ir.PersonaVariant(persona="tester", action_primary="issue_report_create"),
            ]
        ),
    )
    edit_s = ir.SurfaceSpec(
        name="device_edit",
        title="Edit Device",
        mode=ir.SurfaceMode.EDIT,
        entity_ref="Device",
        sections=[SurfaceSection(name="main", elements=[])],
    )
    create_s = ir.SurfaceSpec(
        name="issue_report_create",
        title="Report Issue",
        mode=ir.SurfaceMode.CREATE,
        entity_ref="IssueReport",
        sections=[SurfaceSection(name="main", elements=[])],
    )
    by_name = {
        "device_detail": view_s,
        "device_edit": edit_s,
        "issue_report_create": create_s,
    }
    ctx = _compile_view_surface(
        view_s,
        device,
        "Device",
        "/devices",
        "device",
        "/app",
        surfaces_by_name=by_name,
    )
    assert ctx.detail is not None
    d = ctx.detail
    assert d.persona_primary_urls["tester"] == create_path("/app", entity_slug("IssueReport"))
    assert d.persona_primary_labels["tester"] == "Report Issue"
    assert d.persona_primary_kinds["tester"] == "create"
    assert d.persona_primary_urls["engineer"] == edit_path("/app", entity_slug("Device"))
    assert d.persona_primary_labels["engineer"] == "Edit Device"
    assert d.persona_primary_kinds["engineer"] == "edit"


def test_apply_persona_detail_primary_create_when_update_denied() -> None:
    from dazzle.http.runtime.page_routes import _apply_persona_detail_primary
    from dazzle.render.context import DetailContext, FieldContext

    detail = DetailContext(
        entity_name="Device",
        title="Device Detail",
        fields=[FieldContext(name="name", label="Name", type="text")],
        edit_url=None,  # UPDATE denied cleared default edit
        persona_primary_urls={"tester": "/app/issuereport/create"},
        persona_primary_labels={"tester": "Report Issue"},
        persona_primary_kinds={"tester": "create"},
    )
    _apply_persona_detail_primary(detail, ["role_tester"], can_update=False)
    assert detail.edit_url == "/app/issuereport/create"
    assert detail.edit_label == "Report Issue"
    assert detail.primary_action_kind == "create"


def test_apply_persona_detail_primary_edit_respects_update_deny() -> None:
    from dazzle.http.runtime.page_routes import _apply_persona_detail_primary
    from dazzle.render.context import DetailContext, FieldContext

    detail = DetailContext(
        entity_name="Device",
        title="Device Detail",
        fields=[FieldContext(name="name", label="Name", type="text")],
        edit_url=None,
        persona_primary_urls={"engineer": "/app/device/{id}/edit"},
        persona_primary_labels={"engineer": "Edit Device"},
        persona_primary_kinds={"engineer": "edit"},
    )
    _apply_persona_detail_primary(detail, ["engineer"], can_update=False)
    assert detail.edit_url is None
    assert detail.edit_label == "Edit"


def test_apply_persona_detail_primary_edit_when_update_ok() -> None:
    from dazzle.http.runtime.page_routes import _apply_persona_detail_primary
    from dazzle.render.context import DetailContext, FieldContext

    detail = DetailContext(
        entity_name="Device",
        title="Device Detail",
        fields=[FieldContext(name="name", label="Name", type="text")],
        edit_url="/app/device/{id}/edit",
        persona_primary_urls={"engineer": "/app/device/{id}/edit"},
        persona_primary_labels={"engineer": "Edit Device"},
        persona_primary_kinds={"engineer": "edit"},
    )
    _apply_persona_detail_primary(detail, ["engineer"], can_update=True)
    assert detail.edit_url == "/app/device/{id}/edit"
    assert detail.edit_label == "Edit Device"
    assert detail.primary_action_kind == "edit"


def test_detail_actions_use_edit_label_for_create_primary() -> None:
    from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter

    adapter = FragmentSurfaceAdapter()
    actions = adapter._build_detail_actions(
        {
            "edit_url": "/app/issuereport/create",
            "edit_label": "Report Issue",
            "primary_action_kind": "create",
            "entity_name": "Device",
            "delete_url": "",
            "transitions": [],
            "integration_actions": [],
            "external_link_actions": [],
        }
    )
    assert len(actions) == 1
    assert getattr(actions[0], "label", None) == "Report Issue"


def test_appspec_compile_view_threads_action_primary() -> None:
    appspec = ir.AppSpec(
        name="demo",
        title="Demo",
        domain=ir.DomainSpec(
            name="d",
            entities=[
                _task_entity(),
                ir.EntitySpec(
                    name="IssueReport",
                    label="Issue",
                    title="Issue Report",
                    fields=[
                        ir.FieldSpec(
                            name="id",
                            type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                            pk=True,
                        ),
                    ],
                ),
            ],
        ),
        surfaces=[
            ir.SurfaceSpec(
                name="task_detail",
                title="Task Detail",
                mode=ir.SurfaceMode.VIEW,
                entity_ref="Task",
                sections=[SurfaceSection(name="main", elements=[])],
                ux=ir.UXSpec(
                    persona_variants=[
                        ir.PersonaVariant(persona="tester", action_primary="issue_report_create"),
                    ]
                ),
            ),
            ir.SurfaceSpec(
                name="issue_report_create",
                title="Report Issue",
                mode=ir.SurfaceMode.CREATE,
                entity_ref="IssueReport",
                sections=[SurfaceSection(name="main", elements=[])],
            ),
        ],
    )
    contexts = compile_appspec_to_templates(appspec, app_prefix="/app")
    view_ctx = next(c for c in contexts.values() if c.detail is not None)
    assert view_ctx.detail.persona_primary_labels["tester"] == "Report Issue"
    assert view_ctx.detail.persona_primary_kinds["tester"] == "create"
    assert "create" in view_ctx.detail.persona_primary_urls["tester"]
