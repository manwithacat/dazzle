"""Tests for Phase 1 workspace explorer — navigation plan + deterministic exploration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.agent.journey_models import NavigationTarget, Verdict

# ---------------------------------------------------------------------------
# build_navigation_plan tests
# ---------------------------------------------------------------------------


def _make_appspec(
    *,
    personas: list[dict] | None = None,
    workspaces: list[dict] | None = None,
    surfaces: list[dict] | None = None,
) -> MagicMock:
    """Build a minimal mock AppSpec for navigation plan tests."""
    spec = MagicMock()

    # Personas
    persona_mocks = []
    for p in personas or []:
        pm = MagicMock()
        pm.id = p["id"]
        pm.default_workspace = p.get("default_workspace")
        persona_mocks.append(pm)
    spec.personas = persona_mocks

    # Surfaces
    surface_mocks = []
    for s in surfaces or []:
        sm = MagicMock()
        sm.name = s["name"]
        sm.entity_ref = s.get("entity_ref")
        sm.mode = MagicMock()
        sm.mode.value = s.get("mode", "list")
        sm.mode.__str__ = lambda self: self.value
        surface_mocks.append(sm)
    spec.surfaces = surface_mocks

    # Workspaces
    workspace_mocks = []
    for w in workspaces or []:
        wm = MagicMock()
        wm.name = w["name"]
        # Access control
        if "allow_personas" in w:
            wm.access = MagicMock()
            wm.access.level = MagicMock()
            wm.access.level.value = "persona"
            wm.access.allow_personas = w["allow_personas"]
            wm.access.deny_personas = w.get("deny_personas", [])
        else:
            wm.access = None
        # Regions
        region_mocks = []
        for r in w.get("regions", []):
            rm = MagicMock()
            rm.name = r["name"]
            rm.source = r.get("source")
            rm.display = MagicMock()
            rm.display.value = r.get("display", "list")
            region_mocks.append(rm)
        wm.regions = region_mocks
        workspace_mocks.append(wm)
    spec.workspaces = workspace_mocks

    return spec


class TestBuildNavigationPlan:
    def test_basic_plan(self) -> None:
        from dazzle.agent.missions.journey import build_navigation_plan

        appspec = _make_appspec(
            personas=[{"id": "teacher", "default_workspace": "teaching"}],
            workspaces=[
                {
                    "name": "teaching",
                    "regions": [
                        {"name": "tasks", "source": "Task"},
                        {"name": "students", "source": "Student"},
                    ],
                },
            ],
            surfaces=[
                {"name": "task_list", "entity_ref": "Task", "mode": "list"},
                {"name": "task_create", "entity_ref": "Task", "mode": "create"},
                {"name": "student_list", "entity_ref": "Student", "mode": "list"},
            ],
        )
        plan = build_navigation_plan(appspec, "teacher")
        assert len(plan) > 0
        # Should include URLs for Task and Student entities
        urls = [t.url for t in plan]
        assert any("/task" in u.lower() for u in urls)
        assert any("/student" in u.lower() for u in urls)

    def test_respects_workspace_access(self) -> None:
        from dazzle.agent.missions.journey import build_navigation_plan

        appspec = _make_appspec(
            personas=[{"id": "student", "default_workspace": "learning"}],
            workspaces=[
                {
                    "name": "teaching",
                    "allow_personas": ["teacher"],
                    "regions": [{"name": "grades", "source": "Grade"}],
                },
                {
                    "name": "learning",
                    "allow_personas": ["student", "teacher"],
                    "regions": [{"name": "homework", "source": "Homework"}],
                },
            ],
            surfaces=[
                {"name": "grade_list", "entity_ref": "Grade", "mode": "list"},
                {"name": "homework_list", "entity_ref": "Homework", "mode": "list"},
            ],
        )
        plan = build_navigation_plan(appspec, "student")
        urls = [t.url for t in plan]
        # Student should NOT get Grade (from teaching workspace)
        assert not any("/grade" in u.lower() for u in urls)
        # Student SHOULD get Homework
        assert any("/homework" in u.lower() for u in urls)

    def test_no_default_workspace(self) -> None:
        from dazzle.agent.missions.journey import build_navigation_plan

        appspec = _make_appspec(
            personas=[{"id": "admin", "default_workspace": None}],
            workspaces=[
                {
                    "name": "dashboard",
                    "regions": [{"name": "tasks", "source": "Task"}],
                },
            ],
            surfaces=[
                {"name": "task_list", "entity_ref": "Task", "mode": "list"},
            ],
        )
        plan = build_navigation_plan(appspec, "admin")
        # Should still produce targets even without default_workspace
        assert len(plan) > 0

    def test_returns_navigation_targets(self) -> None:
        from dazzle.agent.missions.journey import build_navigation_plan

        appspec = _make_appspec(
            personas=[{"id": "admin"}],
            workspaces=[
                {
                    "name": "admin_dash",
                    "regions": [{"name": "users", "source": "User"}],
                },
            ],
            surfaces=[
                {"name": "user_list", "entity_ref": "User", "mode": "list"},
            ],
        )
        plan = build_navigation_plan(appspec, "admin")
        for target in plan:
            assert isinstance(target, NavigationTarget)
            assert target.url
            assert target.entity_name
            assert target.expectation


# ---------------------------------------------------------------------------
# run_phase1_exploration tests (mocked browser)
# ---------------------------------------------------------------------------


class TestRunPhase1Exploration:
    @pytest.mark.asyncio
    async def test_records_steps_per_target(self) -> None:
        from dazzle.agent.missions.journey import run_phase1_exploration

        targets = [
            NavigationTarget(
                url="/app/tasks",
                entity_name="Task",
                surface_mode="list",
                expectation="Task list page",
            ),
            NavigationTarget(
                url="/app/users",
                entity_name="User",
                surface_mode="list",
                expectation="User list page",
            ),
        ]

        page = AsyncMock()
        page.url = "http://localhost:3000/app/tasks"
        page.title = AsyncMock(return_value="Tasks")
        page.goto = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        page.screenshot = AsyncMock(return_value=b"fake-png")
        page.query_selector_all = AsyncMock(return_value=[])
        page.evaluate = AsyncMock(return_value=0)

        writer = MagicMock()
        writer.save_screenshot = MagicMock(return_value="screenshots/test.png")

        steps = await run_phase1_exploration(
            plan=targets,
            page=page,
            credentials={"email": "test@test.com", "password": "pass"},
            persona="teacher",
            writer=writer,
            base_url="http://localhost:3000",
        )

        assert len(steps) >= 2
        assert all(s.phase == "explore" for s in steps)
        assert writer.write_step.call_count >= 2

    @pytest.mark.asyncio
    async def test_handles_timeout(self) -> None:
        from dazzle.agent.missions.journey import run_phase1_exploration

        targets = [
            NavigationTarget(
                url="/app/tasks",
                entity_name="Task",
                surface_mode="list",
                expectation="Task list page",
            ),
        ]

        call_count = 0

        async def goto_side_effect(url: str, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Login page loads fine
                page.url = "http://localhost:3000/app/"
                return
            raise TimeoutError("Page load timeout")

        page = AsyncMock()
        page.url = "http://localhost:3000/login"
        page.title = AsyncMock(return_value="Tasks")
        page.goto = AsyncMock(side_effect=goto_side_effect)
        page.wait_for_load_state = AsyncMock()
        page.screenshot = AsyncMock(return_value=b"fake-png")
        page.fill = AsyncMock()
        page.click = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.query_selector = AsyncMock(return_value=MagicMock())

        writer = MagicMock()
        writer.save_screenshot = MagicMock(return_value="screenshots/test.png")

        steps = await run_phase1_exploration(
            plan=targets,
            page=page,
            credentials={"email": "test@test.com", "password": "pass"},
            persona="teacher",
            writer=writer,
            base_url="http://localhost:3000",
        )

        # Should have a login step + timeout step
        timeout_steps = [s for s in steps if s.verdict == Verdict.TIMEOUT]
        assert len(timeout_steps) >= 1

    @pytest.mark.asyncio
    async def test_login_failure_returns_early(self) -> None:
        from dazzle.agent.missions.journey import run_phase1_exploration

        targets = [
            NavigationTarget(
                url="/app/tasks",
                entity_name="Task",
                surface_mode="list",
                expectation="Task list page",
            ),
        ]

        page = AsyncMock()
        # After login attempt, still on login page
        page.url = "http://localhost:3000/login"
        page.title = AsyncMock(return_value="Login")
        page.goto = AsyncMock()
        page.wait_for_load_state = AsyncMock()
        page.screenshot = AsyncMock(return_value=b"fake-png")
        page.fill = AsyncMock()
        page.click = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.query_selector = AsyncMock(return_value=MagicMock())

        writer = MagicMock()
        writer.save_screenshot = MagicMock(return_value="screenshots/test.png")

        steps = await run_phase1_exploration(
            plan=targets,
            page=page,
            credentials={"email": "wrong@test.com", "password": "wrong"},
            persona="teacher",
            writer=writer,
            base_url="http://localhost:3000",
        )

        # Should have a login fail step
        fail_steps = [s for s in steps if s.verdict == Verdict.FAIL]
        assert len(fail_steps) >= 1
        assert any("login" in s.action.lower() or "login" in s.target.lower() for s in fail_steps)
