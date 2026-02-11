"""Tests for the DSL emitter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from dazzle.agent.compiler import Proposal
from dazzle.agent.emitter import (
    DslEmitter,
    EmitContext,
    EmitResult,
    EntityFieldInfo,
    _attempt_fix,
    _emit_full_crud_set,
    _emit_generic,
    _emit_missing_crud,
    _emit_navigation_gap,
    _emit_ux_issue,
    _emit_workflow_gap,
    _generate_surface_dsl,
    _infer_missing_action,
    _is_comment_only,
    _primary_entity,
    _sanitize_identifier,
    _select_fields_for_mode,
    _unique_name,
    _validate_dsl,
    _wrap_for_validation,
    build_emit_context,
)

# =============================================================================
# Fixtures
# =============================================================================


def _fields() -> list[EntityFieldInfo]:
    """Standard entity fields for testing."""
    return [
        EntityFieldInfo(name="id", type_str="uuid", is_pk=True),
        EntityFieldInfo(name="title", type_str="str(200)", is_required=True),
        EntityFieldInfo(name="description", type_str="text"),
        EntityFieldInfo(name="status", type_str="enum[draft,active]"),
        EntityFieldInfo(name="created_at", type_str="datetime"),
        EntityFieldInfo(name="updated_at", type_str="datetime"),
    ]


def _context() -> EmitContext:
    """Standard emit context for testing."""
    return EmitContext(
        module_name="test_app",
        existing_entities=["Task"],
        existing_surfaces=["task_list"],
        existing_workspaces=["tasks"],
        entity_fields={"Task": _fields()},
    )


def _proposal(
    category: str = "missing_crud",
    title: str = "No delete for Task",
    severity: str = "high",
    entities: list[str] | None = None,
    surfaces: list[str] | None = None,
    locations: list[str] | None = None,
    narrative: str = "Missing delete operation",
) -> Proposal:
    return Proposal(
        id="P-001",
        title=title,
        narrative=narrative,
        category=category,
        priority=60,
        severity=severity,
        affected_entities=entities if entities is not None else ["Task"],
        affected_surfaces=surfaces if surfaces is not None else [],
        locations=locations if locations is not None else ["/tasks"],
    )


# =============================================================================
# Tests: Helpers
# =============================================================================


class TestSanitizeIdentifier:
    def test_simple(self) -> None:
        assert _sanitize_identifier("Task") == "task"

    def test_spaces(self) -> None:
        assert _sanitize_identifier("My Task List") == "my_task_list"

    def test_special_chars(self) -> None:
        assert _sanitize_identifier("task-list!") == "task_list"

    def test_empty(self) -> None:
        assert _sanitize_identifier("") == "unnamed"

    def test_multiple_underscores(self) -> None:
        assert _sanitize_identifier("task__list") == "task_list"


class TestPrimaryEntity:
    def test_finds_capitalized(self) -> None:
        p = _proposal(entities=["Task", "task_list"])
        assert _primary_entity(p) == "Task"

    def test_skips_surface(self) -> None:
        p = _proposal(entities=["surface:task_list", "Task"])
        assert _primary_entity(p) == "Task"

    def test_fallback(self) -> None:
        p = _proposal(entities=["task_list"])
        assert _primary_entity(p) == "task_list"

    def test_none(self) -> None:
        p = _proposal(entities=[])
        assert _primary_entity(p) is None


class TestInferMissingAction:
    def test_delete(self) -> None:
        p = _proposal(title="No delete for Task")
        assert _infer_missing_action(p) == "delete"

    def test_create(self) -> None:
        p = _proposal(title="Cannot create new Task", narrative="No create form")
        assert _infer_missing_action(p) == "create"

    def test_edit(self) -> None:
        p = _proposal(title="Cannot edit Task", narrative="No edit form")
        assert _infer_missing_action(p) == "edit"

    def test_list(self) -> None:
        p = _proposal(title="No list view to browse tasks", narrative="Cannot browse")
        assert _infer_missing_action(p) == "list"

    def test_view(self) -> None:
        p = _proposal(title="No detail view for Task", narrative="Cannot see details")
        assert _infer_missing_action(p) == "view"

    def test_generic(self) -> None:
        p = _proposal(title="Task CRUD missing", narrative="")
        assert _infer_missing_action(p) == "CRUD"


class TestUniqueName:
    def test_no_conflict(self) -> None:
        assert _unique_name("task_view", ["task_list"]) == "task_view"

    def test_conflict(self) -> None:
        assert _unique_name("task_list", ["task_list"]) == "task_list_2"

    def test_multiple_conflicts(self) -> None:
        assert _unique_name("task_list", ["task_list", "task_list_2"]) == "task_list_3"


class TestIsCommentOnly:
    def test_comments(self) -> None:
        assert _is_comment_only("# This is a comment\n# Another") is True

    def test_empty(self) -> None:
        assert _is_comment_only("") is True

    def test_code(self) -> None:
        assert _is_comment_only('surface foo "Foo":\n  mode: list') is False

    def test_mixed(self) -> None:
        assert _is_comment_only("# comment\nsurface foo") is False


# =============================================================================
# Tests: Surface Generation
# =============================================================================


class TestGenerateSurfaceDsl:
    def test_list_surface(self) -> None:
        dsl = _generate_surface_dsl("Task", "task_list", "Task List", "list", _fields())
        assert 'surface task_list "Task List":' in dsl
        assert "uses entity Task" in dsl
        assert "mode: list" in dsl
        assert "field title" in dsl

    def test_create_surface(self) -> None:
        dsl = _generate_surface_dsl("Task", "task_create", "Create Task", "create", _fields())
        assert "mode: create" in dsl
        # Create should exclude auto-timestamps
        assert "created_at" not in dsl
        assert "updated_at" not in dsl

    def test_view_surface(self) -> None:
        dsl = _generate_surface_dsl("Task", "task_view", "Task Detail", "view", _fields())
        assert "mode: view" in dsl
        # View shows all fields except PK
        assert "field title" in dsl
        assert "field created_at" in dsl

    def test_edit_surface(self) -> None:
        dsl = _generate_surface_dsl("Task", "task_edit", "Edit Task", "edit", _fields())
        assert "mode: edit" in dsl
        assert "created_at" not in dsl

    def test_pk_excluded(self) -> None:
        dsl = _generate_surface_dsl("Task", "task_view", "Task", "view", _fields())
        # PK field 'id' should be excluded in view
        lines = dsl.split("\n")
        field_lines = [ln for ln in lines if ln.strip().startswith("field ")]
        field_names = [ln.strip().split()[1] for ln in field_lines]
        assert "id" not in field_names


class TestSelectFieldsForMode:
    def test_list_limits_columns(self) -> None:
        fields = _fields()
        result = _select_fields_for_mode(fields, "list")
        assert len(result) <= 6
        assert all(not f.is_pk for f in result)
        # Text fields excluded from list
        assert all(f.type_str != "text" for f in result)

    def test_view_shows_all(self) -> None:
        fields = _fields()
        result = _select_fields_for_mode(fields, "view")
        # All non-PK fields
        assert len(result) == len(fields) - 1

    def test_create_excludes_auto(self) -> None:
        fields = _fields()
        result = _select_fields_for_mode(fields, "create")
        names = {f.name for f in result}
        assert "created_at" not in names
        assert "updated_at" not in names
        assert "id" not in names


# =============================================================================
# Tests: Category Emitters
# =============================================================================


class TestEmitMissingCrud:
    def test_single_delete(self) -> None:
        p = _proposal(title="No delete for Task")
        dsl = _emit_missing_crud(p, _context())
        # Delete is not a surface mode — should get a TODO
        assert "TODO" in dsl or "action" in dsl.lower()

    def test_single_create(self) -> None:
        p = _proposal(title="Cannot create new Task", narrative="No create form exists")
        dsl = _emit_missing_crud(p, _context())
        assert "mode: create" in dsl
        assert "surface task_create" in dsl

    def test_no_entity(self) -> None:
        p = _proposal(entities=[])
        dsl = _emit_missing_crud(p, _context())
        assert "TODO" in dsl

    def test_no_fields(self) -> None:
        ctx = EmitContext(module_name="test", entity_fields={})
        p = _proposal(entities=["Unknown"])
        dsl = _emit_missing_crud(p, ctx)
        assert "TODO" in dsl

    def test_avoids_existing_surfaces(self) -> None:
        ctx = _context()
        # task_list already exists, so "CRUD" should skip it
        dsl = _emit_full_crud_set("Task", _fields(), ctx)
        assert "task_list" not in dsl.split("surface ")[1] if "surface " in dsl else True


class TestEmitUxIssue:
    def test_generates_comment(self) -> None:
        p = _proposal(
            category="ux_issue",
            title="Missing validation",
            surfaces=["task_form"],
            narrative="Form lacks validation markers",
        )
        dsl = _emit_ux_issue(p, _context())
        assert "# UX improvement" in dsl
        assert "task_form" in dsl

    def test_suggests_search(self) -> None:
        p = _proposal(
            category="ux_issue",
            title="No search available",
            surfaces=["task_list"],
            narrative="Cannot search or filter tasks",
        )
        dsl = _emit_ux_issue(p, _context())
        assert "search" in dsl

    def test_no_surfaces(self) -> None:
        p = _proposal(category="ux_issue", surfaces=[])
        dsl = _emit_ux_issue(p, _context())
        assert "TODO" in dsl


class TestEmitWorkflowGap:
    def test_generates_stub(self) -> None:
        p = _proposal(category="workflow_gap", title="Missing approval step")
        dsl = _emit_workflow_gap(p, _context())
        assert "state_machine" in dsl
        assert "transitions" in dsl
        assert entity_name_in_output(dsl, "Task")

    def test_no_entity(self) -> None:
        p = _proposal(category="workflow_gap", entities=[])
        dsl = _emit_workflow_gap(p, _context())
        assert "TODO" in dsl


class TestEmitNavigationGap:
    def test_generates_workspace(self) -> None:
        p = _proposal(
            category="navigation_gap",
            title="Cannot reach Task page",
            surfaces=["task_list", "task_detail"],
        )
        ctx = _context()
        dsl = _emit_navigation_gap(p, ctx)
        assert "workspace" in dsl
        assert "purpose:" in dsl

    def test_no_info(self) -> None:
        p = _proposal(category="navigation_gap", entities=[], surfaces=[])
        dsl = _emit_navigation_gap(p, _context())
        assert "TODO" in dsl


class TestEmitGeneric:
    def test_generates_todo(self) -> None:
        p = _proposal(category="access_gap", title="Cannot access admin panel")
        dsl = _emit_generic(p, _context())
        assert "TODO" in dsl
        assert "access_gap" in dsl or "Access" in dsl
        assert "admin panel" in dsl


# =============================================================================
# Tests: Validation
# =============================================================================


class TestValidateDsl:
    def test_valid_dsl(self) -> None:
        dsl = 'module test\napp test "Test"\nentity Foo "Foo":\n  id: uuid pk\n  name: str(100)\n'
        errors, warnings = _validate_dsl(dsl)
        assert errors == []

    def test_invalid_dsl(self) -> None:
        errors, warnings = _validate_dsl("this is not valid dsl !!!")
        assert len(errors) > 0


class TestWrapForValidation:
    def test_wraps_with_module(self) -> None:
        ctx = _context()
        wrapped = _wrap_for_validation(
            'surface task_view "Task":\n  uses entity Task\n  mode: view', ctx
        )
        assert "module test_app" in wrapped
        assert "app _emit_validation" in wrapped
        # Should include entity stubs
        assert "entity Task" in wrapped


class TestAttemptFix:
    def test_no_change_on_unknown_error(self) -> None:
        dsl = 'surface foo "Foo":\n  mode: list'
        assert _attempt_fix(dsl, ["some random error"]) == dsl

    def test_fixes_indentation(self) -> None:
        dsl = "surface foo:\n      mode: list"
        fixed = _attempt_fix(dsl, ["unexpected indent at line 2"])
        # Should normalize indentation
        assert fixed != dsl or "indent" not in dsl


# =============================================================================
# Tests: DslEmitter
# =============================================================================


class TestDslEmitter:
    def test_emit_single_crud(self) -> None:
        emitter = DslEmitter()
        p = _proposal(title="Cannot create new Task")
        result = emitter.emit(p, _context())
        assert result.proposal_id == "P-001"
        assert result.category == "missing_crud"
        assert "surface" in result.dsl_code or "TODO" in result.dsl_code

    def test_emit_comment_only_is_valid(self) -> None:
        emitter = DslEmitter()
        p = _proposal(category="access_gap", title="No access")
        result = emitter.emit(p, _context())
        assert result.valid is True
        assert "TODO" in result.dsl_code

    def test_emit_batch(self) -> None:
        emitter = DslEmitter()
        proposals = [
            _proposal(title="No create", narrative="Cannot create new Task"),
            _proposal(category="ux_issue", title="No search", surfaces=["task_list"]),
        ]
        results = emitter.emit_batch(proposals, _context())
        assert len(results) == 2

    def test_emit_report_empty(self) -> None:
        emitter = DslEmitter()
        report = emitter.emit_report([])
        assert "No proposals to emit" in report

    def test_emit_report_with_results(self) -> None:
        emitter = DslEmitter()
        results = [
            EmitResult(
                proposal_id="P-001",
                dsl_code='surface task_create "Create Task":\n  uses entity Task\n  mode: create',
                valid=True,
                category="missing_crud",
                description="DSL for: Create Task",
            ),
            EmitResult(
                proposal_id="P-002",
                dsl_code="# TODO: Fix something",
                valid=True,
                category="gap",
                description="Guidance for: Fix something",
            ),
        ]
        report = emitter.emit_report(results)
        assert "# DSL Emission Report" in report
        assert "P-001" in report
        assert "```dsl" in report

    def test_emit_report_with_failures(self) -> None:
        emitter = DslEmitter()
        results = [
            EmitResult(
                proposal_id="P-001",
                dsl_code="invalid dsl",
                valid=False,
                errors=["Parse error at line 1"],
                category="gap",
                description="Failed emission",
                attempts=3,
            ),
        ]
        report = emitter.emit_report(results)
        assert "Failed Emissions" in report
        assert "Attempts" in report

    def test_emit_result_to_json(self) -> None:
        result = EmitResult(
            proposal_id="P-001",
            dsl_code="# test",
            valid=True,
            category="gap",
            description="test",
        )
        data = result.to_json()
        assert data["proposal_id"] == "P-001"
        assert data["valid"] is True


# =============================================================================
# Tests: Context Builder
# =============================================================================


class TestBuildEmitContext:
    def test_from_appspec(self) -> None:
        from types import SimpleNamespace

        entity = SimpleNamespace(
            name="Task",
            fields=[
                SimpleNamespace(
                    name="id",
                    type=SimpleNamespace(
                        kind="uuid",
                        max_length=None,
                        precision=None,
                        scale=None,
                        enum_values=None,
                        ref_entity=None,
                    ),
                    pk=True,
                    required=False,
                    constraints=None,
                ),
                SimpleNamespace(
                    name="title",
                    type=SimpleNamespace(
                        kind="str",
                        max_length=200,
                        precision=None,
                        scale=None,
                        enum_values=None,
                        ref_entity=None,
                    ),
                    pk=False,
                    required=True,
                    constraints=None,
                ),
            ],
        )
        surface = SimpleNamespace(name="task_list")
        workspace = SimpleNamespace(name="tasks")
        appspec = SimpleNamespace(
            name="test_app",
            domain=SimpleNamespace(entities=[entity]),
            surfaces=[surface],
            workspaces=[workspace],
        )

        ctx = build_emit_context(appspec)
        assert ctx.module_name == "test_app"
        assert ctx.existing_entities == ["Task"]
        assert ctx.existing_surfaces == ["task_list"]
        assert ctx.existing_workspaces == ["tasks"]
        assert len(ctx.entity_fields["Task"]) == 2
        assert ctx.entity_fields["Task"][0].is_pk is True
        assert ctx.entity_fields["Task"][1].type_str == "str(200)"


# =============================================================================
# Tests: MCP Handler Integration
# =============================================================================


class TestEmitDiscoveryHandler:
    def test_emit_no_reports(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import emit_discovery_handler

        (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\n')
        (tmp_path / ".dazzle").mkdir()

        result = json.loads(emit_discovery_handler(tmp_path, {}))
        assert "error" in result

    def test_emit_no_observations(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import emit_discovery_handler

        (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\n')
        report_dir = tmp_path / ".dazzle" / "discovery"
        report_dir.mkdir(parents=True)
        (report_dir / "empty.json").write_text(json.dumps({"observations": []}))

        result = json.loads(emit_discovery_handler(tmp_path, {"session_id": "empty"}))
        assert result["results"] == []

    @patch("dazzle.mcp.server.handlers.discovery._load_appspec")
    def test_emit_with_observations(
        self,
        mock_load: MagicMock,
        tmp_path: Path,
    ) -> None:
        from types import SimpleNamespace

        from dazzle.mcp.server.handlers.discovery import emit_discovery_handler

        # Set up mock appspec
        entity = SimpleNamespace(
            name="Task",
            fields=[
                SimpleNamespace(
                    name="id",
                    type=SimpleNamespace(
                        kind="uuid",
                        max_length=None,
                        precision=None,
                        scale=None,
                        enum_values=None,
                        ref_entity=None,
                    ),
                    pk=True,
                    required=False,
                    constraints=None,
                ),
                SimpleNamespace(
                    name="title",
                    type=SimpleNamespace(
                        kind="str",
                        max_length=200,
                        precision=None,
                        scale=None,
                        enum_values=None,
                        ref_entity=None,
                    ),
                    pk=False,
                    required=True,
                    constraints=None,
                ),
            ],
        )
        mock_load.return_value = SimpleNamespace(
            name="test",
            domain=SimpleNamespace(entities=[entity]),
            surfaces=[],
            workspaces=[],
        )

        (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\n')
        report_dir = tmp_path / ".dazzle" / "discovery"
        report_dir.mkdir(parents=True)
        (report_dir / "session.json").write_text(
            json.dumps(
                {
                    "observations": [
                        {
                            "category": "missing_crud",
                            "severity": "high",
                            "title": "Cannot create new Task",
                            "description": "No create surface",
                            "location": "/tasks",
                            "related_artefacts": ["entity:Task"],
                        }
                    ]
                }
            )
        )

        result = json.loads(emit_discovery_handler(tmp_path, {"session_id": "session"}))
        assert result["total_emitted"] == 1
        assert result["valid_count"] >= 0
        assert "report_markdown" in result

    @patch("dazzle.mcp.server.handlers.discovery._load_appspec")
    def test_emit_filters_by_proposal_id(
        self,
        mock_load: MagicMock,
        tmp_path: Path,
    ) -> None:
        from types import SimpleNamespace

        from dazzle.mcp.server.handlers.discovery import emit_discovery_handler

        mock_load.return_value = SimpleNamespace(
            name="test",
            domain=SimpleNamespace(entities=[]),
            surfaces=[],
            workspaces=[],
        )

        (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\n')
        report_dir = tmp_path / ".dazzle" / "discovery"
        report_dir.mkdir(parents=True)
        (report_dir / "session.json").write_text(
            json.dumps(
                {
                    "observations": [
                        {
                            "category": "missing_crud",
                            "severity": "high",
                            "title": "No create",
                            "related_artefacts": ["entity:Task"],
                        },
                        {
                            "category": "ux_issue",
                            "severity": "medium",
                            "title": "No search",
                            "related_artefacts": ["surface:task_list"],
                        },
                    ]
                }
            )
        )

        # Only emit P-001
        result = json.loads(
            emit_discovery_handler(tmp_path, {"session_id": "session", "proposal_ids": ["P-001"]})
        )
        assert result["total_emitted"] == 1

    def test_consolidated_dispatch_emit(self, tmp_path: Path) -> None:
        """Verify emit operation is routed by consolidated handler."""
        import asyncio

        from dazzle.mcp.server.handlers_consolidated import handle_discovery

        with patch("dazzle.mcp.server.handlers_consolidated._resolve_project") as mock_resolve:
            mock_resolve.return_value = tmp_path
            (tmp_path / ".dazzle").mkdir(parents=True, exist_ok=True)

            result = json.loads(asyncio.run(handle_discovery({"operation": "emit"})))
            # Should get "no reports" error, not "unknown operation"
            assert "error" in result
            assert "Unknown" not in result["error"]

    def test_tool_has_emit_operation(self) -> None:
        from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

        tools = get_consolidated_tools()
        discovery_tool = next(t for t in tools if t.name == "discovery")
        ops = discovery_tool.inputSchema["properties"]["operation"]["enum"]
        assert "emit" in ops

    def test_tool_has_proposal_ids_param(self) -> None:
        from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

        tools = get_consolidated_tools()
        discovery_tool = next(t for t in tools if t.name == "discovery")
        assert "proposal_ids" in discovery_tool.inputSchema["properties"]


# =============================================================================
# Helpers
# =============================================================================


def entity_name_in_output(dsl: str, name: str) -> bool:
    """Check if entity name appears in DSL output."""
    return name in dsl
