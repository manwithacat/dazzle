"""Tests for permit-based UI button suppression (#550, #552)."""

from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.core import ir


@pytest.fixture(autouse=True)
def _skip_if_no_fastapi() -> None:
    pytest.importorskip("fastapi")


def _make_appspec(
    *,
    workspaces: list[ir.WorkspaceSpec] | None = None,
    entities: list[ir.EntitySpec] | None = None,
) -> ir.AppSpec:
    return ir.AppSpec(
        name="test_app",
        title="Test App",
        module="test",
        workspaces=workspaces or [],
        domain=ir.DomainSpec(entities=entities or []),
        surfaces=[],
    )


def _make_deps(
    appspec: ir.AppSpec,
    surface_workspace: dict[str, str] | None = None,
    entity_cedar_specs: dict[str, Any] | None = None,
    surface_entity: dict[str, str] | None = None,
) -> Any:
    from dazzle_back.runtime.access_evaluator import evaluate_permission
    from dazzle_ui.runtime.page_routes import _PageDeps

    return _PageDeps(
        appspec=appspec,
        backend_url="http://localhost:8000",
        theme_css="",
        get_auth_context=None,
        app_prefix="",
        surface_workspace=surface_workspace or {},
        entity_cedar_specs=entity_cedar_specs or {},
        surface_entity=surface_entity or {},
        evaluate_permission=evaluate_permission,
    )


class TestShouldSuppressMutations:
    """Workspace read_only persona variant suppresses all mutation buttons."""

    def test_no_workspace_no_suppression(self) -> None:
        from dazzle_ui.runtime.page_routes import _should_suppress_mutations

        deps = _make_deps(_make_appspec())
        assert not _should_suppress_mutations(deps, "task_list", None, ["role_teacher"])

    def test_read_only_persona_suppresses(self) -> None:
        from dazzle_ui.runtime.page_routes import _should_suppress_mutations

        ws = ir.WorkspaceSpec(
            name="student_portal",
            title="Student Portal",
            ux=ir.UXSpec(
                persona_variants=[
                    ir.PersonaVariant(persona="student", read_only=True),
                ]
            ),
        )
        appspec = _make_appspec(workspaces=[ws])
        deps = _make_deps(appspec, surface_workspace={"feedback_list": "student_portal"})
        assert _should_suppress_mutations(deps, "feedback_list", None, ["role_student"])

    def test_non_read_only_persona_allows(self) -> None:
        from dazzle_ui.runtime.page_routes import _should_suppress_mutations

        ws = ir.WorkspaceSpec(
            name="teacher_ws",
            title="Teacher Workspace",
            ux=ir.UXSpec(
                persona_variants=[
                    ir.PersonaVariant(persona="student", read_only=True),
                    ir.PersonaVariant(persona="teacher", read_only=False),
                ]
            ),
        )
        appspec = _make_appspec(workspaces=[ws])
        deps = _make_deps(appspec, surface_workspace={"feedback_list": "teacher_ws"})
        assert not _should_suppress_mutations(deps, "feedback_list", None, ["role_teacher"])

    def test_role_prefix_stripped(self) -> None:
        """User roles have 'role_' prefix; persona IDs don't."""
        from dazzle_ui.runtime.page_routes import _should_suppress_mutations

        ws = ir.WorkspaceSpec(
            name="student_portal",
            title="Student Portal",
            ux=ir.UXSpec(
                persona_variants=[
                    ir.PersonaVariant(persona="student", read_only=True),
                ]
            ),
        )
        appspec = _make_appspec(workspaces=[ws])
        deps = _make_deps(appspec, surface_workspace={"feedback_list": "student_portal"})
        # Role is "role_student" but persona variant uses "student"
        assert _should_suppress_mutations(deps, "feedback_list", None, ["role_student"])


class TestUserCanMutate:
    """Entity permit rules control per-operation button visibility."""

    def test_no_cedar_spec_allows(self) -> None:
        from dazzle_ui.runtime.page_routes import _user_can_mutate

        deps = _make_deps(_make_appspec())
        assert _user_can_mutate(deps, "task_view", "update", None)

    def test_no_surface_name_allows(self) -> None:
        from dazzle_ui.runtime.page_routes import _user_can_mutate

        deps = _make_deps(_make_appspec())
        assert _user_can_mutate(deps, None, "delete", None)

    def test_permitted_role_allows(self) -> None:
        """Teacher with update permission can see Edit button."""
        from dazzle_ui.runtime.page_routes import _user_can_mutate

        pytest.importorskip("dazzle_back.runtime.access_evaluator")
        from dazzle_back.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.UPDATE,
                    personas=["teacher"],
                ),
            ],
        )
        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Task": cedar},
            surface_entity={"task_view": "Task"},
        )
        auth_ctx = SimpleNamespace(
            is_authenticated=True,
            user=SimpleNamespace(id="user1", roles=["role_teacher"], is_superuser=False),
        )
        assert _user_can_mutate(deps, "task_view", "update", auth_ctx)

    def test_denied_role_blocks(self) -> None:
        """Student without update permission cannot see Edit button."""
        from dazzle_ui.runtime.page_routes import _user_can_mutate

        pytest.importorskip("dazzle_back.runtime.access_evaluator")
        from dazzle_back.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.UPDATE,
                    personas=["teacher"],
                ),
            ],
        )
        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Task": cedar},
            surface_entity={"task_view": "Task"},
        )
        auth_ctx = SimpleNamespace(
            is_authenticated=True,
            user=SimpleNamespace(id="user2", roles=["role_student"], is_superuser=False),
        )
        assert not _user_can_mutate(deps, "task_view", "update", auth_ctx)

    def test_delete_denied_separately(self) -> None:
        """Update allowed but delete denied — only delete is blocked."""
        from dazzle_ui.runtime.page_routes import _user_can_mutate

        pytest.importorskip("dazzle_back.runtime.access_evaluator")
        from dazzle_back.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.UPDATE,
                    personas=["teacher"],
                ),
                PermissionRuleSpec(
                    operation=AccessOperationKind.DELETE,
                    personas=["school_admin"],
                ),
            ],
        )
        deps = _make_deps(
            _make_appspec(),
            entity_cedar_specs={"Task": cedar},
            surface_entity={"task_view": "Task"},
        )
        auth_ctx = SimpleNamespace(
            is_authenticated=True,
            user=SimpleNamespace(id="user1", roles=["role_teacher"], is_superuser=False),
        )
        assert _user_can_mutate(deps, "task_view", "update", auth_ctx)
        assert not _user_can_mutate(deps, "task_view", "delete", auth_ctx)
