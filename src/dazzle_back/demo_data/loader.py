"""
Demo data loader for scenarios and dev mode.

Loads demo data from JSON files or inline DSL demo blocks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class DemoDataLoader:
    """
    Loads demo data from various sources.

    Supports:
    - JSON files (per-entity or combined)
    - Inline demo data (from DSL demo block)
    """

    def __init__(self, project_root: Path | None = None) -> None:
        """
        Initialize the loader.

        Args:
            project_root: Root directory for resolving relative paths
        """
        self.project_root = project_root or Path.cwd()

    def load_from_json_file(self, path: str | Path) -> dict[str, list[dict[str, Any]]]:
        """
        Load demo data from a JSON file.

        The file should have the format:
        {
            "EntityName": [
                {"field1": "value1", ...},
                ...
            ],
            ...
        }

        Args:
            path: Path to the JSON file (absolute or relative to project_root)

        Returns:
            Dictionary mapping entity names to lists of entity data

        Raises:
            FileNotFoundError: If the file doesn't exist
            json.JSONDecodeError: If the file isn't valid JSON
        """
        full_path = Path(path)
        if not full_path.is_absolute():
            full_path = self.project_root / path

        if not full_path.exists():
            raise FileNotFoundError(f"Demo data file not found: {full_path}")

        with open(full_path, encoding="utf-8") as f:
            data = json.load(f)

        # Validate structure
        if not isinstance(data, dict):
            raise ValueError("Demo data file must contain a JSON object")

        for entity_name, records in data.items():
            if not isinstance(records, list):
                raise ValueError(f"Entity '{entity_name}' data must be a list")
            for i, record in enumerate(records):
                if not isinstance(record, dict):
                    raise ValueError(f"Entity '{entity_name}' record {i} must be an object")

        return data

    def load_from_json_dir(self, dir_path: str | Path) -> dict[str, list[dict[str, Any]]]:
        """
        Load demo data from a directory of JSON files.

        Each file should be named {EntityName}.json and contain a list of records.

        Args:
            dir_path: Path to the directory

        Returns:
            Dictionary mapping entity names to lists of entity data

        Raises:
            NotADirectoryError: If the path isn't a directory
        """
        full_path = Path(dir_path)
        if not full_path.is_absolute():
            full_path = self.project_root / dir_path

        if not full_path.is_dir():
            raise NotADirectoryError(f"Demo data directory not found: {full_path}")

        result: dict[str, list[dict[str, Any]]] = {}

        for json_file in full_path.glob("*.json"):
            entity_name = json_file.stem
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                result[entity_name] = data
            elif isinstance(data, dict):
                # If it's a dict, treat it as a combined file
                result.update(data)

        return result

    def load_inline_demo(
        self, demo_data: dict[str, list[dict[str, Any]]]
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Load demo data from inline DSL demo block.

        The demo_data is already parsed from DSL, so just validate and return.

        Args:
            demo_data: Demo data from DSL parsing

        Returns:
            Validated demo data
        """
        # Validate structure
        for entity_name, records in demo_data.items():
            if not isinstance(records, list):
                raise ValueError(f"Entity '{entity_name}' data must be a list")
            for i, record in enumerate(records):
                if not isinstance(record, dict):
                    raise ValueError(f"Entity '{entity_name}' record {i} must be an object")

        return demo_data

    def merge_demo_data(
        self, *sources: dict[str, list[dict[str, Any]]]
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Merge multiple demo data sources.

        Later sources override earlier ones (for same entity).

        Args:
            *sources: Demo data dictionaries to merge

        Returns:
            Merged demo data
        """
        result: dict[str, list[dict[str, Any]]] = {}

        for source in sources:
            for entity_name, records in source.items():
                if entity_name in result:
                    # Append records
                    result[entity_name].extend(records)
                else:
                    result[entity_name] = list(records)

        return result

    def load_scenario_data(
        self,
        scenario_id: str,
        persona_id: str | None = None,
        seed_script: str | None = None,
        seed_data_path: str | None = None,
        inline_demo: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Load demo data for a scenario with fallback chain.

        Order of precedence:
        1. Per-persona seed_script (if persona_id and seed_script provided)
        2. Scenario seed_data_path (if provided)
        3. Inline demo block (if provided)
        4. Empty dict (generator will create data)

        Args:
            scenario_id: Scenario identifier
            persona_id: Current persona ID (for per-persona data)
            seed_script: Path to per-persona seed script
            seed_data_path: Path to scenario-level seed data
            inline_demo: Inline demo data from DSL

        Returns:
            Demo data for the scenario
        """
        # Try per-persona seed script first
        if persona_id and seed_script:
            try:
                return self.load_from_json_file(seed_script)
            except FileNotFoundError:
                pass  # Fall through to next source

        # Try scenario-level seed data
        if seed_data_path:
            try:
                path = Path(seed_data_path)
                if path.is_dir() or (not path.suffix and (self.project_root / path).is_dir()):
                    return self.load_from_json_dir(seed_data_path)
                return self.load_from_json_file(seed_data_path)
            except (FileNotFoundError, NotADirectoryError):
                pass  # Fall through to next source

        # Try inline demo
        if inline_demo:
            return self.load_inline_demo(inline_demo)

        # Return empty - generator will create data
        return {}
