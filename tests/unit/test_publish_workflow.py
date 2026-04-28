"""
Regression test for the PyPI publish workflow.

Originally guarded the CI chain that rebuilt the Tailwind CSS bundle
before packaging (issue #843). v0.62 removed that pipeline as part of
the Phase 4 teardown — every Dazzle UI template now consumes semantic
.dz-* class families served by static CSS files that are checked into
the repo, so there's no longer a runtime JIT step to regenerate.

The test file is retained as a guard against accidental re-introduction
of the build-css step, and to pin the wheel-shape invariants that
matter post-teardown.
"""

from __future__ import annotations

from pathlib import Path

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "publish-pypi.yml"


class TestPublishWorkflow:
    def test_workflow_exists(self) -> None:
        assert WORKFLOW_PATH.is_file(), f"Workflow missing: {WORKFLOW_PATH}"

    def test_runs_python_build(self) -> None:
        """The workflow must still run `python -m build` to produce the
        wheel + sdist artefacts."""
        content = WORKFLOW_PATH.read_text()
        assert "python -m build" in content, "Workflow no longer runs `python -m build`."

    def test_no_build_css_step(self) -> None:
        """v0.62 (Phase 4 teardown): `dazzle build-css` must NOT run in
        the publish workflow. The Tailwind compiled bundle is gone; if
        someone re-adds the step, this test fails to flag the
        regression."""
        content = WORKFLOW_PATH.read_text()
        assert "dazzle build-css" not in content, (
            "Workflow re-introduced `dazzle build-css` — Phase 4 teardown "
            "removed both the CLI command and the underlying build_css.py "
            "module. Drop the step or restore the module + CLI."
        )

    def test_no_dazzle_bundle_reference(self) -> None:
        """v0.62 (Phase 4 teardown): no part of the publish workflow
        should reference `dazzle-bundle.css` (the file no longer ships
        in the wheel)."""
        content = WORKFLOW_PATH.read_text()
        assert "dazzle-bundle.css" not in content, (
            "Workflow still references `dazzle-bundle.css` — that file "
            "was removed in the Phase 4 teardown. Drop the verification "
            "step or restore the build pipeline."
        )
