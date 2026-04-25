"""Regression tests: every runtime call site of parse_modules uses the live path (#885).

The old `dazzle.core.dsl_parser` module was split into `dazzle.core.parser`
(re-exporting `parse_modules`) and the `dazzle.core.dsl_parser_impl/` package
(parser mixins). Three call sites — alembic env.py, the migrate CLI, and the
process worker — kept stale imports and only failed at runtime when a project
actually ran `dazzle db migrate` etc. This pins the import path so a future
rename surfaces in CI rather than in a downstream user's terminal.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Files that import parse_modules at runtime to drive schema migrations,
# DSL deployment, or background worker DSL loading.
RUNTIME_PARSE_MODULES_CALLERS = [
    "src/dazzle_back/alembic/env.py",
    "src/dazzle/cli/migrate.py",
    "src/dazzle/process/worker.py",
]


def _module_imports_parse_modules_from(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    sources: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "parse_modules":
                    sources.add(node.module)
    return sources


def test_parse_modules_lives_in_dazzle_core_parser() -> None:
    """The canonical home for parse_modules — if this moves, callers must too."""
    from dazzle.core.parser import parse_modules

    assert callable(parse_modules)


@pytest.mark.parametrize("relpath", RUNTIME_PARSE_MODULES_CALLERS)
def test_runtime_callers_import_from_live_module(relpath: str) -> None:
    """Each runtime caller must import from `dazzle.core.parser`, not the removed `dsl_parser`."""
    path = REPO_ROOT / relpath
    sources = _module_imports_parse_modules_from(path)
    assert sources, f"{relpath} no longer imports parse_modules — update this test."
    stale = {s for s in sources if s == "dazzle.core.dsl_parser"}
    assert not stale, (
        f"{relpath} imports parse_modules from removed module {stale!r}. "
        f"Use `from dazzle.core.parser import parse_modules`."
    )


def _build_appspec_argshapes(path: Path) -> list[tuple[int, str]]:
    """Find every `build_appspec(modules, <expr>)` call in `path`.

    Returns ``(lineno, second_arg_source)`` pairs where the second arg
    is rendered back to source via ``ast.unparse`` so the test can
    assert what the call actually passes.
    """
    tree = ast.parse(path.read_text())
    sites: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name == "build_appspec" and len(node.args) >= 2:
                sites.append((node.lineno, ast.unparse(node.args[1])))
    return sites


@pytest.mark.parametrize("relpath", RUNTIME_PARSE_MODULES_CALLERS)
def test_build_appspec_passes_module_name_not_filesystem_path(relpath: str) -> None:
    """``build_appspec``'s second arg is the ROOT MODULE NAME (a dotted
    string from `[project] root` in dazzle.toml — e.g. ``"myapp.core"``),
    NOT the filesystem path. ProjectManifest.project_root is misleadingly
    named — despite the name, it holds the module string.

    Surfaced by #886: alembic env.py / migrate.py / process worker were
    all passing ``str(project_root)`` (a Path) which raised ``LinkError:
    Root module '/abs/path' not found``. This test pins each call site
    to use ``manifest.project_root`` (the module string) and rejects the
    cwd-Path patterns that caused the bug.
    """
    path = REPO_ROOT / relpath
    sites = _build_appspec_argshapes(path)
    assert sites, f"{relpath} no longer calls build_appspec — update this test."
    BAD_PATTERNS = ("str(project_root)", "str(Path.cwd())", "str(cwd)")
    for lineno, arg in sites:
        for bad in BAD_PATTERNS:
            assert bad != arg.replace(" ", ""), (
                f"{relpath}:{lineno} passes {arg!r} as the second arg to "
                f"build_appspec — this is the cwd Path, not the module "
                f"name. Use `manifest.project_root` instead (#886)."
            )
