"""End-to-end guide-concordance test against ``examples/simple_task`` (#1106 v0.71.0).

The user-named success criterion for v0.71.0: guidance must
demonstrate concordance with the underlying DSL definition of user
experience. This test exercises that on the canonical example app:

- The committed ``examples/simple_task/dsl/onboarding.dsl`` guide
  must parse + link clean.
- Intentional drift (rename the step target to a nonexistent
  surface) must fail ``build_appspec`` with a clear concordance
  error message.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.errors import LinkError

EXAMPLE_ROOT = Path(__file__).resolve().parents[2] / "examples" / "simple_task"


def test_simple_task_committed_guide_links_clean() -> None:
    """The committed onboarding guide must pass concordance against the
    committed DSL — the worked example for v0.71.0."""
    appspec = load_project_appspec(EXAMPLE_ROOT)
    guide_names = {g.name for g in appspec.guides}
    assert "workspace_setup" in guide_names, (
        f"workspace_setup guide missing — got {sorted(guide_names)}"
    )

    workspace_setup = next(g for g in appspec.guides if g.name == "workspace_setup")
    assert workspace_setup.audience == "persona = admin"
    assert workspace_setup.step_order == [
        "welcome_empty",
        "fill_title",
        "invite_team",
    ]


def test_concordance_catches_unknown_target_surface(tmp_path: Path) -> None:
    """Drift case: renaming a step target to a nonexistent surface
    fails the link with a concordance error."""
    appspec = load_project_appspec(EXAMPLE_ROOT)
    guide = next(g for g in appspec.guides if g.name == "workspace_setup")

    # Tamper with one step's target. Rebuild guides list with the
    # drifted step.
    drifted_step = guide.steps[0].model_copy(update={"target": "surface.no_such_surface"})
    drifted_guide = guide.model_copy(update={"steps": [drifted_step, *guide.steps[1:]]})

    from dazzle.core.guide_concordance import check_guide_concordance

    errors, _ = check_guide_concordance(
        [drifted_guide],
        surfaces=appspec.surfaces,
        entities=appspec.domain.entities,
        personas=appspec.personas,
        streams=appspec.streams,
    )
    assert any("target surface 'no_such_surface' does not exist" in e for e in errors), (
        f"expected unknown-surface error, got: {errors}"
    )


def test_concordance_catches_unknown_event_lifecycle() -> None:
    """Drift case: changing a completion event's lifecycle to something
    invalid (e.g. ``Task.exploded``) fails the link."""
    appspec = load_project_appspec(EXAMPLE_ROOT)
    guide = next(g for g in appspec.guides if g.name == "workspace_setup")

    welcome = guide.steps[0]
    drifted = welcome.model_copy(
        update={
            "complete_on": ir.GuideCompleteOn(
                kind=ir.GuideCompleteOnKind.EVENT,
                event_ref="entity.Task.exploded",
            )
        }
    )
    drifted_guide = guide.model_copy(update={"steps": [drifted, *guide.steps[1:]]})

    from dazzle.core.guide_concordance import check_guide_concordance

    errors, _ = check_guide_concordance(
        [drifted_guide],
        surfaces=appspec.surfaces,
        entities=appspec.domain.entities,
        personas=appspec.personas,
        streams=appspec.streams,
    )
    assert any("lifecycle 'exploded'" in e for e in errors), errors


def test_concordance_catches_unknown_persona() -> None:
    appspec = load_project_appspec(EXAMPLE_ROOT)
    guide = next(g for g in appspec.guides if g.name == "workspace_setup")
    drifted = guide.model_copy(update={"audience": "persona = wizard"})

    from dazzle.core.guide_concordance import check_guide_concordance

    errors, _ = check_guide_concordance(
        [drifted],
        surfaces=appspec.surfaces,
        entities=appspec.domain.entities,
        personas=appspec.personas,
        streams=appspec.streams,
    )
    assert any("unknown persona 'wizard'" in e for e in errors), errors


def test_concordance_catches_unknown_cta_surface() -> None:
    appspec = load_project_appspec(EXAMPLE_ROOT)
    guide = next(g for g in appspec.guides if g.name == "workspace_setup")
    drifted_step = guide.steps[0].model_copy(update={"cta_target": "surface.nowhere"})
    drifted = guide.model_copy(update={"steps": [drifted_step, *guide.steps[1:]]})

    from dazzle.core.guide_concordance import check_guide_concordance

    errors, _ = check_guide_concordance(
        [drifted],
        surfaces=appspec.surfaces,
        entities=appspec.domain.entities,
        personas=appspec.personas,
        streams=appspec.streams,
    )
    assert any("cta_target surface 'nowhere' does not exist" in e for e in errors)


def test_build_appspec_raises_link_error_on_drifted_dsl(tmp_path: Path) -> None:
    """Full-pipeline check: writing a drifted guide DSL into a fresh
    project tree and running build_appspec must raise LinkError."""
    # Copy minimal simple_task tree (just dazzle.toml + dsl/) into tmp.
    import shutil

    dst = tmp_path / "broken_app"
    shutil.copytree(EXAMPLE_ROOT, dst, ignore=shutil.ignore_patterns(".dazzle", "build"))

    # Overwrite the onboarding guide with a drifted target.
    (dst / "dsl" / "onboarding.dsl").write_text(
        """\
module simple_task.guides

use simple_task.core

guide workspace_setup "First-run setup":
  audience: persona = admin

  step bad_target:
    kind: popover
    target: surface.does_not_exist
    title: "x"
    body: "y"
    complete_on: click

  step_order: [bad_target]
"""
    )

    with pytest.raises(LinkError) as exc_info:
        load_project_appspec(dst)
    assert "Guide concordance failed" in str(exc_info.value)
    assert "does_not_exist" in str(exc_info.value)
