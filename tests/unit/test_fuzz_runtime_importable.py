"""Smoke test for the headless-Playwright fuzz runner.

Just confirms the module is importable, the public surface exists,
and the rich-text battery is wired up. The runner itself only runs
under a live booted app + Playwright — that lives in the /fuzz
slash command and is exercised manually after framework JS changes.
"""

from __future__ import annotations

from dataclasses import is_dataclass


def test_module_importable() -> None:
    from dazzle.testing.fuzz_runtime import FuzzReport, run_app_fuzz

    assert callable(run_app_fuzz)
    assert is_dataclass(FuzzReport)


def test_report_shape() -> None:
    from dazzle.testing.fuzz_runtime import FuzzReport
    from dazzle.testing.fuzz_runtime.runner import FuzzCheck

    r = FuzzReport(project="x")
    assert r.project == "x"
    assert r.passed == 0
    assert r.total == 0
    assert r.failures == []

    r.checks.append(FuzzCheck(name="ok", passed=True))
    r.checks.append(FuzzCheck(name="bad", passed=False, detail="why"))
    assert r.passed == 1
    assert r.total == 2
    assert len(r.failures) == 1
    assert r.failures[0].name == "bad"


def test_richtext_battery_present() -> None:
    """The battery must include the #1000 regression check so future
    refactors of toggleInline can't silently re-introduce the
    block-vs-inline nesting bug."""
    from dazzle.testing.fuzz_runtime import runner

    # Source-grep — the actual assertion runs under Playwright.
    src = __import__("inspect").getsource(runner)
    assert "Ctrl+B does NOT wrap <p> in <strong> (#1000)" in src
    assert "javascript: href stripped on paste" in src
    assert "<script> in paste does NOT execute" in src
    assert "h1 demoted to h2" in src
    assert "editor functional after htmx-style remount" in src
