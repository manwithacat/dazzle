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
