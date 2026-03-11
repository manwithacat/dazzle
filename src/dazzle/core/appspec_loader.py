"""Canonical AppSpec loader.

Single implementation of the manifest → discover → parse → build pipeline.
All code that needs to load a project's AppSpec should import from here.
"""

from __future__ import annotations

import logging
from pathlib import Path

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.ir.appspec import AppSpec
from dazzle.core.ir.module import ModuleIR
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

_log = logging.getLogger(__name__)


def _inject_json_stories(modules: list[ModuleIR], project_root: Path) -> None:
    """Inject stories from stories.json into modules so the linker can validate them.

    Stories saved via ``story save`` live in ``.dazzle/stories/stories.json``,
    not in DSL files.  Without this step the linker rejects ``story:`` references
    in rhythm scenes because they aren't in the symbol table.
    """
    from dazzle.core.stories_persistence import load_stories

    json_stories = load_stories(project_root)
    if not json_stories:
        return

    # Collect story IDs already present in DSL modules
    dsl_story_ids: set[str] = set()
    for mod in modules:
        for s in mod.fragment.stories:
            dsl_story_ids.add(s.story_id)

    # Add JSON-only stories to the first module's fragment
    new_stories = [s for s in json_stories if s.story_id not in dsl_story_ids]
    if new_stories and modules:
        modules[0].fragment.stories.extend(new_stories)
        _log.debug("Injected %d stories from stories.json into symbol table", len(new_stories))


def load_project_appspec(project_root: Path) -> AppSpec:
    """Load and return the fully-linked AppSpec for a project.

    Combines the four-step boilerplate: manifest → discover → parse → build.

    Args:
        project_root: Path to the project directory containing ``dazzle.toml``.

    Returns:
        Fully-linked AppSpec ready for runtime or analysis use.
    """
    manifest = load_manifest(project_root / "dazzle.toml")
    dsl_files = discover_dsl_files(project_root, manifest)
    modules = parse_modules(dsl_files)
    _inject_json_stories(modules, project_root)
    return build_appspec(modules, manifest.project_root)
