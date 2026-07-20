"""Scene walk models, loader, discovery, validate (#1638 PR1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.testing.walk.discovery import default_walks_dir, discover_walk_paths
from dazzle.testing.walk.loader import WalkLoadError, load_walk
from dazzle.testing.walk.models import CORE_ACTION_TYPES, WalkActionType
from dazzle.testing.walk.validate import validate_walk, validate_walks

_REPO = Path(__file__).resolve().parents[2]
_SIMPLE = _REPO / "examples" / "simple_task"
_SHOWCASE = _SIMPLE / "fixtures" / "scene_walks" / "land_and_see_tasks.yaml"


class TestDiscover:
    def test_default_dir(self) -> None:
        assert default_walks_dir(_SIMPLE) == _SIMPLE / "fixtures" / "scene_walks"

    def test_discovers_showcase(self) -> None:
        paths = discover_walk_paths(_SIMPLE)
        stems = {p.stem for p in paths}
        assert "land_and_see_tasks" in stems

    def test_missing_dir_empty(self, tmp_path: Path) -> None:
        assert discover_walk_paths(tmp_path) == []


class TestLoadShowcase:
    def test_load_land_and_see(self) -> None:
        walk = load_walk(_SHOWCASE)
        assert walk.walk_id == "land_and_see_tasks"
        assert walk.persona == "member"
        assert walk.home_workspace == "my_work"
        assert walk.story_ids() == ["ST-020"]
        assert walk.core_only() is True
        assert len(walk.scenes) == 1
        assert walk.scenes[0].actions[0].type == WalkActionType.NAVIGATE

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(WalkLoadError, match="file not found"):
            load_walk(tmp_path / "nope.yaml")

    def test_invalid_action_type(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text(
            "persona: member\nscenes:\n  - id: s\n    actions:\n      - type: not_a_verb\n",
            encoding="utf-8",
        )
        with pytest.raises(WalkLoadError, match="schema validation"):
            load_walk(p)


class TestValidate:
    def test_showcase_clean_with_appspec(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        appspec = load_project_appspec(_SIMPLE)
        walk = load_walk(_SHOWCASE)
        issues = validate_walk(walk, appspec=appspec, require_core_only=True, require_story=True)
        errors = [i for i in issues if i.level == "error"]
        assert errors == [], [e.format() for e in errors]

    def test_unknown_persona(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        appspec = load_project_appspec(_SIMPLE)
        walk = load_walk(_SHOWCASE)
        walk.persona = "not_a_persona"
        issues = validate_walk(walk, appspec=appspec)
        assert any(i.code == "unknown_persona" for i in issues)

    def test_extension_action_warns(self, tmp_path: Path) -> None:
        p = tmp_path / "ext.yaml"
        p.write_text(
            "persona: member\n"
            "scenes:\n"
            "  - id: s\n"
            "    story: ST-020\n"
            "    actions:\n"
            "      - type: api_find\n"
            "        path: /tasks\n",
            encoding="utf-8",
        )
        walk = load_walk(p)
        assert walk.core_only() is False
        issues = validate_walk(walk)
        assert any(i.code == "extension_action" and i.level == "warning" for i in issues)
        hard = validate_walk(walk, require_core_only=True)
        assert any(i.code == "extension_action" and i.level == "error" for i in hard)

    def test_validate_walks_batch(self) -> None:
        paths = discover_walk_paths(_SIMPLE)
        walks, issues = validate_walks(paths)
        assert len(walks) >= 1
        assert not any(i.level == "error" and i.code == "load_failed" for i in issues)


class TestCoreSet:
    def test_core_subset_of_enum(self) -> None:
        assert CORE_ACTION_TYPES <= set(WalkActionType)


class TestRunnerDryRun:
    def test_dry_run_showcase(self) -> None:
        from dazzle.testing.walk.runner import run_walk_sync

        walk = load_walk(_SHOWCASE)
        result = run_walk_sync(
            walk,
            base_url="http://example.test",
            project_root=_SIMPLE,
            dry_run=True,
        )
        assert result.ok is True
        assert result.dry_run is True
        assert len(result.scenes) == 1
        assert all(a.ok for a in result.scenes[0].actions)
        assert "PASS" in result.summary()

    def test_extension_action_fails_live(self, tmp_path: Path) -> None:
        from dazzle.testing.walk.runner import run_walk_sync

        p = tmp_path / "ext.yaml"
        p.write_text(
            "persona: member\nscenes:\n  - id: s\n    actions:\n      - type: api_find\n",
            encoding="utf-8",
        )
        walk = load_walk(p)
        # dry-run still ok (skips)
        dry = run_walk_sync(walk, base_url="http://x", dry_run=True)
        assert dry.ok is True
        # live without auth will fail at auth — use dry for extension detail:
        # inject a fake runner state by running action path via dry=False
        # after mocking auth is heavy; check ActionResult via WalkRunner dry=False
        # with authenticate patched.
        import asyncio
        from unittest.mock import AsyncMock

        from dazzle.testing.walk.runner import WalkRunner

        async def _go() -> None:
            async with WalkRunner(
                base_url="http://example.test",
                project_root=_SIMPLE,
                dry_run=False,
            ) as runner:
                runner.authenticate = AsyncMock()  # type: ignore[method-assign]
                res = await runner.run(walk)
                assert res.ok is False
                assert any(a.type == "api_find" and not a.ok for s in res.scenes for a in s.actions)

        asyncio.run(_go())

    def test_assert_any_text_on_body(self) -> None:
        import asyncio

        from dazzle.testing.walk.models import ActionSpec, SceneSpec, WalkActionType
        from dazzle.testing.walk.runner import WalkRunner

        async def _go() -> None:
            async with WalkRunner(base_url="http://example.test", dry_run=False) as runner:
                runner.last_body = "Hello Task Board My Work"
                runner.last_status = 200
                runner.last_url = "http://example.test/app/workspaces/my_work"
                scene = SceneSpec(id="s", actions=[ActionSpec(type=WalkActionType.NAVIGATE)])
                ok = await runner._act_assert_any_text(
                    ActionSpec(type=WalkActionType.ASSERT_ANY_TEXT, texts=["Task", "Nope"]),
                    scene,
                )
                assert ok.ok is True
                bad = await runner._act_assert_any_text(
                    ActionSpec(type=WalkActionType.ASSERT_ANY_TEXT, texts=["Nope"]),
                    scene,
                )
                assert bad.ok is False
                login = await runner._act_assert_not_login(
                    ActionSpec(type=WalkActionType.ASSERT_NOT_LOGIN),
                    scene,
                )
                assert login.ok is True

        asyncio.run(_go())


class TestJobClaims:
    def test_load_showcase_registry(self) -> None:
        from dazzle.testing.walk.claims import discover_registry_path, load_registry

        path = discover_registry_path(_SIMPLE)
        assert path is not None
        reg = load_registry(path)
        assert reg.version == 1
        assert len(reg.guides) >= 1
        g = reg.guides[0]
        assert g.walk == "land_and_see_tasks"
        assert g.persona == "member"

    def test_check_documented_clean(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle.testing.walk.claims import check_registry, discover_registry_path, load_registry

        appspec = load_project_appspec(_SIMPLE)
        reg = load_registry(discover_registry_path(_SIMPLE))  # type: ignore[arg-type]
        result = check_registry(reg, project_root=_SIMPLE, appspec=appspec, run_walks=False)
        assert result.ok, [i.format() for i in result.errors]

    def test_verified_requires_walk(self, tmp_path: Path) -> None:
        from dazzle.testing.walk.claims import check_registry, load_registry

        p = tmp_path / "job_claims.yaml"
        p.write_text(
            "version: 1\n"
            "guides:\n"
            "  - id: bad\n"
            "    path: no-doc.md\n"
            "    persona: member\n"
            "    status: verified\n",
            encoding="utf-8",
        )
        # need dazzle.toml for project? check only uses paths
        (tmp_path / "dazzle.toml").write_text("[project]\nname = 't'\n", encoding="utf-8")
        reg = load_registry(p)
        result = check_registry(reg, project_root=tmp_path, appspec=None, run_walks=False)
        codes = {i.code for i in result.errors}
        assert "walk_required" in codes
