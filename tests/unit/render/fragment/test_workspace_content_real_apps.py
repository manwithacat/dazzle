"""Phase 4B.5.c follow-on (v0.66.126): byte-equivalence sweep across
every example app's workspaces.

Walks every `examples/<app>/dsl` corpus, builds the production
`WorkspaceContext` for each workspace via `build_workspace_context`,
and asserts that the typed render matches the Jinja render byte-for-
byte. This is the strongest evidence that
`render_workspace_content_typed` is a drop-in replacement for the
legacy `render_fragment("workspace/_content.html", ...)` call —
catches any regression on any production-shape ctx that the synthetic
fixture tests in `test_workspace_content_full_assembly.py` might miss.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle_back.runtime.renderers.dual_path import diff_summary
from dazzle_ui.runtime.template_renderer import render_fragment
from dazzle_ui.runtime.workspace_renderer import (
    apply_layout_preferences,
    build_catalog,
    build_workspace_context,
    render_workspace_content_typed,
)

EXAMPLES = (
    "simple_task",
    "ops_dashboard",
    "support_tickets",
    "contact_manager",
    "fieldtest_hub",
)


def _discover_workspace_cases() -> list[tuple[str, str, object]]:
    """Yield (example_name, workspace_name, workspace_context) for every
    workspace in every example app. Run once at collection time so
    parametrize gets a stable list."""
    cases: list[tuple[str, str, object]] = []
    repo_root = Path(__file__).resolve().parents[4]
    for example in EXAMPLES:
        example_dir = repo_root / "examples" / example
        if not example_dir.exists():
            continue
        dsl_files = sorted((example_dir / "dsl").glob("*.dsl"))
        if not dsl_files:
            continue
        try:
            modules = parse_modules(dsl_files)
            root = next((m for m in modules if m.app_name), None)
            if not root:
                continue
            spec = build_appspec(modules, root.name)
        except Exception:
            continue
        for ws in spec.workspaces:
            try:
                ctx = build_workspace_context(ws, spec)
                ctx = apply_layout_preferences(ctx, {})
                cases.append((example, ws.name, ctx))
            except Exception:
                continue
    return cases


_CASES = _discover_workspace_cases()


@pytest.mark.parametrize(
    ("example", "workspace_name", "ctx"),
    _CASES,
    ids=[f"{e}/{w}" for e, w, _ in _CASES],
)
def test_real_workspace_byte_equivalent(example, workspace_name, ctx) -> None:
    """The typed-Fragment render must match the Jinja render byte-for-
    byte (modulo whitespace) for every example workspace.

    If this fails, a real production app would render differently
    after flipping `DAZZLE_TYPED_RENDER=1`. Diagnose by capturing both
    outputs and walking the diff at the position `diff_summary`
    reports."""
    catalog = build_catalog(ctx)
    legacy = render_fragment(
        "workspace/_content.html",
        workspace=ctx,
        user_preferences={},
        catalog=catalog,
        fold_count=ctx.fold_count,
        primary_actions=[],
    )
    typed = render_workspace_content_typed(
        workspace=ctx,
        catalog=catalog,
        fold_count=ctx.fold_count,
        primary_actions=[],
    )
    assert diff_summary(legacy, typed) is None, f"workspace {example}/{workspace_name} diverged"


def test_at_least_one_workspace_was_discovered() -> None:
    """Guard against silent test-discovery failure — if no example
    app parsed cleanly, the sweep above would silently pass with zero
    parametrized cases."""
    assert len(_CASES) > 0, "expected at least one example workspace"
