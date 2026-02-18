"""
Demo Data Blueprint Persistence Layer.

Handles loading and saving Demo Data Blueprints to/from
.dazzle/demo_data/blueprint.json files, with fallback to
dsl/seeds/demo_data/ for checked-in seed blueprints.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from dazzle.mcp.server.paths import project_demo_data_dir

if TYPE_CHECKING:
    from dazzle.core.ir.demo_blueprint import DemoDataBlueprint

SEEDS_BLUEPRINT_DIR = "dsl/seeds/demo_data"
BLUEPRINT_FILE = "blueprint.json"


def get_blueprint_dir(project_root: Path) -> Path:
    """Get the .dazzle/demo_data/ directory (runtime location).

    Args:
        project_root: Root directory of the project

    Returns:
        Path to the demo_data directory
    """
    return project_demo_data_dir(project_root)


def get_seeds_blueprint_dir(project_root: Path) -> Path:
    """Get the dsl/seeds/demo_data/ directory (checked-in fallback).

    Args:
        project_root: Root directory of the project

    Returns:
        Path to the seeds demo_data directory
    """
    return project_root / SEEDS_BLUEPRINT_DIR


def get_blueprint_file(project_root: Path) -> Path:
    """Get the blueprint.json file path (runtime location).

    Args:
        project_root: Root directory of the project

    Returns:
        Path to blueprint.json
    """
    return get_blueprint_dir(project_root) / BLUEPRINT_FILE


def _find_blueprint_file(project_root: Path) -> Path | None:
    """Find the blueprint.json file, checking runtime then seeds.

    Args:
        project_root: Root directory of the project

    Returns:
        Path to existing blueprint.json, or None if not found.
    """
    # Check runtime location first (.dazzle/demo_data/)
    runtime_file = get_blueprint_dir(project_root) / BLUEPRINT_FILE
    if runtime_file.exists():
        return runtime_file

    # Fall back to seeds location (dsl/seeds/demo_data/)
    seeds_file = get_seeds_blueprint_dir(project_root) / BLUEPRINT_FILE
    if seeds_file.exists():
        return seeds_file

    return None


def load_blueprint(project_root: Path) -> DemoDataBlueprint | None:
    """Load a Demo Data Blueprint from the project.

    Checks the runtime location (.dazzle/demo_data/) first, then falls
    back to the checked-in seeds location (dsl/seeds/demo_data/).

    Args:
        project_root: Root directory of the project

    Returns:
        DemoDataBlueprint if found, None otherwise
    """
    from dazzle.core.ir.demo_blueprint import BlueprintContainer, DemoDataBlueprint

    blueprint_file = _find_blueprint_file(project_root)
    if blueprint_file is None:
        return None

    try:
        content = json.loads(blueprint_file.read_text(encoding="utf-8"))

        # Handle both wrapped and unwrapped formats
        if "version" in content and "blueprint" in content:
            container = BlueprintContainer.model_validate(content)
            return container.blueprint
        else:
            # Direct blueprint format
            return DemoDataBlueprint.model_validate(content)

    except (json.JSONDecodeError, ValueError):
        return None


def save_blueprint(project_root: Path, blueprint: DemoDataBlueprint) -> Path:
    """Save a Demo Data Blueprint to the project.

    Args:
        project_root: Root directory of the project
        blueprint: Blueprint to save

    Returns:
        Path to the saved file
    """
    from dazzle.core.ir.demo_blueprint import BlueprintContainer

    blueprint_dir = get_blueprint_dir(project_root)
    blueprint_dir.mkdir(parents=True, exist_ok=True)

    blueprint_file = get_blueprint_file(project_root)

    container = BlueprintContainer(blueprint=blueprint)

    content = container.model_dump(mode="json")
    blueprint_file.write_text(
        json.dumps(content, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return blueprint_file


def delete_blueprint(project_root: Path) -> bool:
    """Delete the Demo Data Blueprint file.

    Args:
        project_root: Root directory of the project

    Returns:
        True if deleted, False if not found
    """
    blueprint_file = get_blueprint_file(project_root)
    if blueprint_file.exists():
        blueprint_file.unlink()
        return True
    return False
