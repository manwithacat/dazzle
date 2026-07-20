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
