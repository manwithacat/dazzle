"""Tests for build_server_config() — unified ServerConfig construction."""

from pathlib import Path
from typing import Any
from unittest.mock import patch

from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    SurfaceElement,
    SurfaceMode,
    SurfaceSection,
    SurfaceSpec,
    WorkspaceSpec,
)
from dazzle.core.ir.process import ProcessSpec, ScheduleSpec
from dazzle.core.ir.state_machine import StateMachineSpec
from dazzle_back.runtime.app_factory import build_server_config

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _entity(name: str = "Task", extra_fields: list[FieldSpec] | None = None) -> EntitySpec:
    fields = [
        FieldSpec(
            name="id",
            type=FieldType(kind=FieldTypeKind.UUID),
            modifiers=[FieldModifier.PK],
        ),
        FieldSpec(
            name="title",
            type=FieldType(kind=FieldTypeKind.STR, max_length=200),
            modifiers=[FieldModifier.REQUIRED],
        ),
    ]
    if extra_fields:
        fields.extend(extra_fields)
    return EntitySpec(name=name, title=name, fields=fields)


def _surface(
    name: str = "task_list",
    entity_ref: str = "Task",
    mode: SurfaceMode = SurfaceMode.LIST,
    search_fields: list[str] | None = None,
) -> SurfaceSpec:
    kwargs: dict[str, Any] = {
        "name": name,
        "title": name,
        "entity_ref": entity_ref,
        "mode": mode,
        "sections": [
            SurfaceSection(
                name="main",
                title="Main",
                elements=[SurfaceElement(field_name="title", label="Title")],
            )
        ],
    }
    if search_fields is not None:
        kwargs["search_fields"] = search_fields
    return SurfaceSpec(**kwargs)


def _appspec(
    entities: list[EntitySpec] | None = None,
    surfaces: list[SurfaceSpec] | None = None,
    processes: list[Any] | None = None,
    schedules: list[Any] | None = None,
) -> AppSpec:
    return AppSpec(
        name="test_app",
        title="Test App",
        domain=DomainSpec(entities=entities or [_entity()]),
        surfaces=surfaces or [_surface()],
        workspaces=[WorkspaceSpec(name="main", title="Main")],
        processes=processes or [],
        schedules=schedules or [],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildServerConfig:
    def test_computes_entity_list_projections(self) -> None:
        config = build_server_config(_appspec())
        assert "Task" in config.entity_list_projections
        proj = config.entity_list_projections["Task"]
        assert "title" in proj
        assert "id" in proj

    def test_computes_entity_search_fields(self) -> None:
        appspec = _appspec(surfaces=[_surface(search_fields=["title"])])
        config = build_server_config(appspec)
        assert config.entity_search_fields == {"Task": ["title"]}

    def test_computes_entity_auto_includes_from_ref_fields(self) -> None:
        ref_field = FieldSpec(
            name="assignee",
            type=FieldType(kind=FieldTypeKind.REF, ref_entity="User"),
        )
        appspec = _appspec(entities=[_entity(extra_fields=[ref_field])])
        config = build_server_config(appspec)
        assert config.entity_auto_includes == {"Task": ["assignee"]}

    def test_computes_entity_status_fields_from_state_machine(self) -> None:
        sm = StateMachineSpec(status_field="state", states=["open", "closed"])
        entity = EntitySpec(
            name="Task",
            title="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                FieldSpec(
                    name="title",
                    type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                    modifiers=[FieldModifier.REQUIRED],
                ),
            ],
            state_machine=sm,
        )
        appspec = _appspec(entities=[entity])
        config = build_server_config(appspec)
        assert config.entity_status_fields == {"Task": "state"}

    def test_sets_schedule_specs_from_appspec(self) -> None:
        schedule = ScheduleSpec(name="daily_sync", cron="0 8 * * *")
        appspec = _appspec(schedules=[schedule])
        config = build_server_config(appspec)
        assert len(config.schedule_specs) == 1
        assert config.schedule_specs[0].name == "daily_sync"

    @patch("dazzle_back.runtime.app_factory.build_fragment_sources", return_value={"stripe": {}})
    def test_computes_fragment_sources_when_not_provided(self, mock_bfs: Any) -> None:
        config = build_server_config(_appspec())
        assert config.fragment_sources == {"stripe": {}}
        mock_bfs.assert_called_once()

    def test_uses_provided_fragment_sources(self) -> None:
        frag = {"custom_pack": {"op": "data"}}
        config = build_server_config(_appspec(), fragment_sources=frag)
        assert config.fragment_sources == frag

    @patch("dazzle.core.process_persistence.load_processes")
    def test_merges_persisted_processes_dsl_wins(self, mock_load: Any, tmp_path: Path) -> None:
        dsl_proc = ProcessSpec(name="approval")
        persisted_proc = ProcessSpec(name="approval", title="Persisted Approval")
        extra_proc = ProcessSpec(name="onboarding")
        mock_load.return_value = [persisted_proc, extra_proc]

        appspec = _appspec(processes=[dsl_proc])
        config = build_server_config(appspec, project_root=tmp_path)
        names = [p.name for p in config.process_specs]
        assert names == ["approval", "onboarding"]
        # DSL version should win (first in list, no title)
        assert config.process_specs[0].title is None

    def test_works_without_project_root_skips_process_merge(self) -> None:
        config = build_server_config(_appspec(), project_root=None)
        assert config.process_specs == []

    def test_passes_through_caller_options(self) -> None:
        config = build_server_config(
            _appspec(),
            database_url="postgresql://localhost/test",
            enable_auth=True,
            enable_files=True,
            enable_dev_mode=True,
            enable_test_mode=True,
        )
        assert config.database_url == "postgresql://localhost/test"
        assert config.enable_auth is True
        assert config.enable_files is True
        assert config.enable_dev_mode is True
        assert config.enable_test_mode is True
