from __future__ import annotations

import logging
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

TOML_FILENAME = "test_personas.toml"
TOML_RELPATH = f".dazzle/{TOML_FILENAME}"


def load_credentials(
    project_root: Path,
    persona_filter: list[str] | None = None,
) -> dict[str, dict[str, str]]:
    """Load test persona credentials from .dazzle/test_personas.toml.

    Args:
        project_root: Path to the project root directory.
        persona_filter: If provided, only return credentials for these persona IDs.

    Returns:
        Mapping of persona ID to ``{"email": ..., "password": ...}``.

    Raises:
        FileNotFoundError: If the TOML file does not exist.
        ValueError: If the ``[personas]`` section is missing or empty.
    """
    toml_path = project_root / TOML_RELPATH

    if not toml_path.exists():
        msg = (
            f"test_personas.toml not found at {toml_path}. "
            "Run 'dazzle demo propose' to generate test credentials, "
            "or create the file manually."
        )
        raise FileNotFoundError(msg)

    with toml_path.open("rb") as f:
        data = tomllib.load(f)

    personas_section = data.get("personas")
    if not personas_section:
        msg = (
            f"No [personas] section (or it is empty) in {toml_path}. "
            "Each persona needs an [personas.<id>] table with email and password."
        )
        raise ValueError(msg)

    if persona_filter is not None:
        result: dict[str, dict[str, str]] = {}
        for name in persona_filter:
            if name in personas_section:
                result[name] = personas_section[name]
            else:
                logger.warning(
                    "Persona '%s' listed in filter but not found in %s — skipping",
                    name,
                    toml_path,
                )
        return result

    return dict(personas_section)
