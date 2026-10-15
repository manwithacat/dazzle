"""Tests for the fidelity MCP handlers."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _import_fidelity():
    """Import fidelity handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])

    # Build a common mock with real implementations for DSL loading
    from types import ModuleType

    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules

    common_mock = ModuleType("dazzle.mcp.server.handlers.common")

    def _extract_progress(args=None):
        ctx = MagicMock()
        ctx.log_sync = MagicMock()
        return ctx

    def _load_project_appspec(project_root):
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        return build_appspec(modules, manifest.project_root)

    def _error_response(msg):
        return json.dumps({"error": msg})

    def _unknown_op_response(operation, tool):
        return json.dumps({"error": f"Unknown {tool} operation: {operation}"})

    common_mock.error_response = _error_response
    common_mock.unknown_op_response = _unknown_op_response
    common_mock.extract_progress = _extract_progress
    common_mock.load_project_appspec = _load_project_appspec

    def _handler_error_json(fn):
        from functools import wraps

        @wraps(fn)
        def wrapper(*a, **kw):
            try:
                return fn(*a, **kw)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        return wrapper

    common_mock.handler_error_json = _handler_error_json
    common_mock.wrap_handler_errors = _handler_error_json
    sys.modules["dazzle.mcp.server.handlers.common"] = common_mock

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "fidelity.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.fidelity",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    sys.modules["dazzle.mcp.server.handlers.fidelity"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_fi = _import_fidelity()

# Get references to the functions we need
score_fidelity_handler = _fi.score_fidelity_handler
_build_next_steps = _fi._build_next_steps


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project with minimal DSL structure."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Create dazzle.toml manifest
    manifest = project_dir / "dazzle.toml"
    manifest.write_text(
        """
[project]
name = "test_project"
version = "0.1.0"
root = "test_project"

[modules]
paths = ["./dsl"]
"""
    )

    # Create dsl directory
    dsl_dir = project_dir / "dsl"
    dsl_dir.mkdir()

    # Create main.dsl
    main_dsl = dsl_dir / "main.dsl"
    main_dsl.write_text(
        """
module test_project
app test_project "Test Project"

entity Task "Task":
    id: uuid pk
    title: str(200) required

surface task_list "Tasks":
    uses entity Task
    mode: list
    section main:
        field title "Title"
"""
    )

    return project_dir


# =============================================================================
# Handler Tests
# =============================================================================


class TestScoreFidelityHandler:
    """Tests for score_fidelity_handler."""

    def test_handles_missing_manifest(self, tmp_path) -> None:
        """Test handling when dazzle.toml is missing."""
        project_dir = tmp_path / "no_manifest"
        project_dir.mkdir()

        result = score_fidelity_handler(project_dir, {})
        data = json.loads(result)

        assert "error" in data

    def test_handles_parse_errors(self, tmp_path) -> None:
        """Test handling parse errors."""
        project_dir = tmp_path / "bad_dsl"
        project_dir.mkdir()

        manifest = project_dir / "dazzle.toml"
        manifest.write_text(
            """
[project]
name = "test_project"
version = "0.1.0"
root = "test_project"

[modules]
paths = ["./dsl"]
"""
        )

        dsl_dir = project_dir / "dsl"
        dsl_dir.mkdir()

        # Invalid DSL
        main_dsl = dsl_dir / "main.dsl"
        main_dsl.write_text("this is not valid dsl syntax {{{")

        result = score_fidelity_handler(project_dir, {})
        data = json.loads(result)

        assert "error" in data

    # ------------------------------------------------------------------
    # #1114 — ImportError branching
    # ------------------------------------------------------------------

    def test_internal_import_error_surfaces_real_cause_not_phantom_extras(
        self, temp_project, monkeypatch
    ) -> None:
        """When dazzle.page is installed but a nested import inside it
        breaks (e.g. stale bytecode after a rename), the handler must
        report the real ImportError instead of the misleading
        `pip install '.[dazzle-ui]'` hint (#1114).

        Simulated by poisoning sys.modules for one of the modules the
        handler imports — the next `from … import …` raises ImportError
        with a name that points inside dazzle.page.*, not at the root."""
        # Sanity-check dazzle.page is actually importable in this env —
        # without that, this test wouldn't be exercising the branch we
        # care about.
        import importlib.util

        assert importlib.util.find_spec("dazzle.page") is not None, (
            "test precondition: dazzle.page must be installed"
        )

        # Force the second import to fail at a sub-symbol level —
        # mimics the stale-bytecode-after-rename failure mode from the
        # AegisMark repro.
        target = "dazzle.page.runtime.template_renderer"
        monkeypatch.setitem(sys.modules, target, None)

        result = score_fidelity_handler(temp_project, {})
        data = json.loads(result)

        # Real cause exposed (ModuleNotFoundError subclasses ImportError;
        # either spelling counts).
        assert "raw" in data, f"expected raw ImportError detail surfaced, got {data!r}"
        assert "ImportError" in data["raw"] or "ModuleNotFoundError" in data["raw"]
        # Phantom extras hint NOT present
        assert "[dazzle-ui]" not in json.dumps(data), (
            f"phantom extras hint leaked back into payload: {data!r}"
        )
        # MCP restart hint IS present
        assert "Restart the MCP server" in data["hint"]

    def test_ui_root_missing_uses_reinstall_hint(self, temp_project, monkeypatch) -> None:
        """When `dazzle.page` itself is genuinely absent (find_spec
        returns None AND the ImportError names dazzle.page as the
        missing module), the handler must hint at a reinstall — not
        the phantom `.[dazzle-ui]` extras."""
        # Pretend find_spec can't locate dazzle.page.
        import importlib.util as _il

        real_find_spec = _il.find_spec

        def _fake_find_spec(name, *args, **kwargs):
            if name == "dazzle.page":
                return None
            return real_find_spec(name, *args, **kwargs)

        monkeypatch.setattr(_il, "find_spec", _fake_find_spec)
        # Force the actual import to raise with a name pointing at
        # dazzle.page — sys.modules trick again, but at the root.
        monkeypatch.setitem(sys.modules, "dazzle.page.converters.template_compiler", None)

        result = score_fidelity_handler(temp_project, {})
        data = json.loads(result)

        assert "error" in data
        assert "subpackage missing" in data["error"]
        assert "force-reinstall" in data["hint"]
        # Still no phantom extras hint
        assert "[dazzle-ui]" not in json.dumps(data)


_CRITICAL = "Critical: Many surfaces have structural issues. Fix missing elements first."
_FILE_BUG = "If this looks like a Dazzle bug, file it: `gh issue create --repo manwithacat/dazzle`"
_MAJOR = "Fix major gaps to improve fidelity above 0.8."
_GOOD = "Fidelity is good. Consider adding more story coverage."


# Score band (<0.5 critical, <0.8 major) picks the headline; each gap type and
# story coverage <0.5 adds its own step; the "good" step appears only when nothing
# else does.
@pytest.mark.parametrize(
    ("overall", "gap_counts", "story_coverage", "expected"),
    [
        pytest.param(0.3, {}, 0.5, [_CRITICAL, _FILE_BUG], id="low-score-critical-and-bug-hint"),
        pytest.param(0.6, {}, 0.5, [_MAJOR], id="medium-score-major"),
        pytest.param(0.9, {}, 0.8, [_GOOD], id="good-score-only-when-no-other-step"),
        pytest.param(
            0.9,
            {"missing_field": 3},
            0.5,
            ["Add missing fields to surface HTML outputs."],
            id="missing-field-gap",
        ),
        pytest.param(
            0.9,
            {"incorrect_input_type": 2},
            0.5,
            ["Correct input types to match field type kinds."],
            id="incorrect-input-type-gap",
        ),
        pytest.param(
            0.9,
            {"missing_design_tokens": 1},
            0.5,
            ["Include design tokens in rendered pages."],
            id="missing-design-tokens-gap",
        ),
        pytest.param(
            0.8,
            {},
            0.3,
            ["Add story-related action affordances to surfaces."],
            id="low-story-coverage",
        ),
    ],
)
def test_build_next_steps(
    overall: float, gap_counts: dict, story_coverage: float, expected: list[str]
) -> None:
    report = SimpleNamespace(overall=overall, gap_counts=gap_counts, story_coverage=story_coverage)
    assert _build_next_steps(report) == expected
