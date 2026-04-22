"""
Regression test for the PyPI publish workflow (#843).

Guards the CI chain that ensures every tagged release ships a fresh
Tailwind CSS bundle. The bundle is gitignored — if the CI step that
regenerates it ever disappears, wheels revert to shipping nothing
(or whatever stale copy the runner happens to have), and new Tailwind
classes added in template refactors silently drop from downstream
installs.
"""

from __future__ import annotations

from pathlib import Path

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "publish-pypi.yml"


class TestPublishWorkflow:
    def test_workflow_exists(self) -> None:
        assert WORKFLOW_PATH.is_file(), f"Workflow missing: {WORKFLOW_PATH}"

    def test_runs_build_css_before_python_build(self) -> None:
        """`dazzle build-css` must run before `python -m build` in the build job.

        If this test fails, the wheel is being packaged with a stale or
        missing dazzle-bundle.css — see #843 for the user-facing symptom.
        """
        content = WORKFLOW_PATH.read_text()
        build_css_idx = content.find("dazzle build-css")
        python_build_idx = content.find("python -m build")
        assert build_css_idx != -1, "Workflow no longer runs `dazzle build-css` — #843 regression."
        assert python_build_idx != -1, "Workflow no longer runs `python -m build`."
        assert build_css_idx < python_build_idx, (
            "`dazzle build-css` must run before `python -m build` so the wheel "
            "ships a fresh bundle. Re-order the steps in publish-pypi.yml."
        )

    def test_verifies_bundle_in_wheel(self) -> None:
        """A post-build guard must assert dazzle-bundle.css is in the wheel."""
        content = WORKFLOW_PATH.read_text()
        assert "dazzle-bundle.css" in content, (
            "Workflow no longer verifies the bundle is in the built wheel — "
            "see #843 — add the `python -m zipfile -l` grep guard back."
        )
