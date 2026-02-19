"""Canonical AppSpec loader.

Single implementation of the manifest → discover → parse → build pipeline.
All code that needs to load a project's AppSpec should import from here.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.ir.appspec import AppSpec
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules


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
    return build_appspec(modules, manifest.project_root)
