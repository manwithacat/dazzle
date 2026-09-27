"""Keep the fixed job-screen panel aligned with real example app jobs."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from dazzle.core.access import workspace_allowed_personas
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.ir.identity import spec_display_id
from dazzle.qa.capture import VIEWPORTS

pytestmark = pytest.mark.gate

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "docs/evaluation/example-job-scenes.toml"


def test_example_job_scenes_resolve_to_accessible_trial_jobs() -> None:
    panel = tomllib.loads(PANEL.read_text())
    assert panel["version"] == 1
    scenes = panel["scene"]
    assert scenes
    assert len({scene["id"] for scene in scenes}) == len(scenes)

    for scene in scenes:
        project = ROOT / "examples" / scene["app"]
        assert project.is_dir(), scene["id"]
        trial = tomllib.loads((project / "trial.toml").read_text())
        scenario = next(
            (row for row in trial["scenario"] if row["name"] == scene["trial_scenario"]),
            None,
        )
        assert scenario is not None, scene["id"]
        assert scene["decision"].strip(), scene["id"]
        assert scenario["tasks"] and scenario["adoption_criteria"], scene["id"]
        assert scene["viewport"] in VIEWPORTS, scene["id"]
        assert set(scene["themes"]) == {"light", "dark"}, scene["id"]

        appspec = load_project_appspec(project)
        persona = scenario["login_persona"]
        assert persona in {spec_display_id(item) for item in appspec.personas}, scene["id"]
        workspace = next(
            (item for item in appspec.workspaces if item.name == scene["workspace"]),
            None,
        )
        assert workspace is not None, scene["id"]
        allowed = workspace_allowed_personas(workspace, appspec.personas)
        assert allowed is None or persona in allowed, scene["id"]
        if starting_url := scenario.get("starting_url"):
            assert starting_url == f"/app/workspaces/{scene['workspace']}", scene["id"]
