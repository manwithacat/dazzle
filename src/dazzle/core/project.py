"""
Project loading utilities.

Provides convenient functions for the common load → parse → build pipeline.
"""

from pathlib import Path

from . import ir
from .fileset import discover_dsl_files
from .linker import build_appspec
from .manifest import ProjectManifest, load_manifest
from .parser import parse_modules


def load_project(
    project_dir: Path | str,
    manifest_path: Path | str | None = None,
) -> ir.AppSpec:
    """
    Load a DAZZLE project and return its AppSpec.

    This is a convenience function that performs the common pipeline:
    1. Load manifest (dazzle.toml)
    2. Discover DSL files
    3. Parse modules
    4. Link and build AppSpec

    Args:
        project_dir: Path to the project root directory
        manifest_path: Optional explicit path to dazzle.toml.
                      If not provided, looks for dazzle.toml in project_dir.

    Returns:
        The linked AppSpec ready for use

    Raises:
        FileNotFoundError: If manifest or DSL files not found
        ParseError: If DSL parsing fails
        LinkError: If linking fails (e.g., invalid references)

    Example:
        >>> from dazzle.core import load_project
        >>> spec = load_project("./my-project")
        >>> print(spec.name, len(spec.domain.entities))
    """
    project_dir = Path(project_dir).resolve()

    if manifest_path is None:
        manifest_path = project_dir / "dazzle.toml"
    else:
        manifest_path = Path(manifest_path).resolve()

    manifest = load_manifest(manifest_path)
    dsl_files = discover_dsl_files(project_dir, manifest)
    modules = parse_modules(dsl_files)
    return build_appspec(modules, manifest.project_root)


def load_project_with_manifest(
    project_dir: Path | str,
    manifest_path: Path | str | None = None,
) -> tuple[ir.AppSpec, ProjectManifest]:
    """
    Load a DAZZLE project and return both AppSpec and manifest.

    Same as load_project() but also returns the ProjectManifest
    for cases where you need access to project configuration.

    Args:
        project_dir: Path to the project root directory
        manifest_path: Optional explicit path to dazzle.toml

    Returns:
        Tuple of (AppSpec, ProjectManifest)

    Example:
        >>> from dazzle.core import load_project_with_manifest
        >>> spec, manifest = load_project_with_manifest("./my-project")
        >>> print(manifest.name, manifest.title)
    """
    project_dir = Path(project_dir).resolve()

    if manifest_path is None:
        manifest_path = project_dir / "dazzle.toml"
    else:
        manifest_path = Path(manifest_path).resolve()

    manifest = load_manifest(manifest_path)
    dsl_files = discover_dsl_files(project_dir, manifest)
    modules = parse_modules(dsl_files)
    appspec = build_appspec(modules, manifest.project_root)
    return appspec, manifest
