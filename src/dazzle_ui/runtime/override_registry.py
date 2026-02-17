"""Override registry for project-level template customizations (v0.29.0).

Scans project ``templates/`` for declaration headers, tracks overrides
in ``.dazzle/overrides.json``, and provides compatibility checking
against the framework's template blocks.

Declaration headers in project templates::

    {# dazzle:override layouts/app_shell.html #}
    {# dazzle:blocks sidebar_brand, sidebar_nav #}
    {% extends "dz://layouts/app_shell.html" %}

The registry persists as JSON so upgrade checks can compare block
hashes across framework versions without re-scanning.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Regex for declaration headers in template files
_OVERRIDE_RE = re.compile(r"\{#\s*dazzle:override\s+(.+?)\s*#\}")
_BLOCKS_RE = re.compile(r"\{#\s*dazzle:blocks\s+(.+?)\s*#\}")

# Regex to extract {% block name %} definitions from framework templates
_BLOCK_DEF_RE = re.compile(r"\{%[-\s]*block\s+(\w+)")


def scan_project_overrides(project_templates_dir: Path) -> list[dict[str, Any]]:
    """Scan a project templates directory for override declarations.

    Args:
        project_templates_dir: Path to the project's ``templates/`` directory.

    Returns:
        List of override descriptors, each with keys:
        ``source``, ``target``, ``blocks``.
    """
    overrides: list[dict[str, Any]] = []
    if not project_templates_dir.is_dir():
        return overrides

    for template_file in project_templates_dir.rglob("*.html"):
        try:
            content = template_file.read_text(encoding="utf-8")
        except OSError:
            continue

        override_match = _OVERRIDE_RE.search(content)
        if not override_match:
            continue

        target = override_match.group(1).strip()
        blocks: list[str] = []
        blocks_match = _BLOCKS_RE.search(content)
        if blocks_match:
            blocks = [b.strip() for b in blocks_match.group(1).split(",") if b.strip()]

        rel_path = template_file.relative_to(project_templates_dir)
        overrides.append(
            {
                "source": str(rel_path),
                "target": target,
                "blocks": blocks,
            }
        )

    return overrides


def extract_block_hashes(
    framework_templates_dir: Path,
    target_template: str,
    block_names: list[str],
) -> dict[str, str]:
    """Compute content hashes for named blocks in a framework template.

    Args:
        framework_templates_dir: Path to the framework ``templates/`` directory.
        target_template: Relative path to the template (e.g. ``layouts/app_shell.html``).
        block_names: Block names to hash.

    Returns:
        Dict mapping block name to its SHA-256 hash (first 8 chars).
    """
    template_path = framework_templates_dir / target_template
    if not template_path.is_file():
        return {}

    content = template_path.read_text(encoding="utf-8")
    hashes: dict[str, str] = {}

    for block_name in block_names:
        block_content = _extract_block_content(content, block_name)
        if block_content is not None:
            digest = hashlib.sha256(block_content.encode("utf-8")).hexdigest()[:8]
            hashes[block_name] = digest

    return hashes


def _extract_block_content(template_source: str, block_name: str) -> str | None:
    """Extract the raw content of a named block from template source.

    Returns None if the block is not found.
    """
    # Match {% block <name> %} ... {% endblock %} or {% endblock <name> %}
    pattern = re.compile(
        r"\{%[-\s]*block\s+" + re.escape(block_name) + r"\s*[-]?%\}(.*?)\{%[-\s]*endblock",
        re.DOTALL,
    )
    match = pattern.search(template_source)
    if match:
        return match.group(1).strip()
    return None


def build_registry(
    project_templates_dir: Path,
    framework_templates_dir: Path,
    framework_version: str = "",
) -> dict[str, Any]:
    """Build the full override registry with block hashes.

    Args:
        project_templates_dir: Path to the project's ``templates/`` directory.
        framework_templates_dir: Path to the framework's ``templates/`` directory.
        framework_version: Current framework version string.

    Returns:
        Registry dict suitable for writing to ``overrides.json``.
    """
    overrides = scan_project_overrides(project_templates_dir)

    entries: list[dict[str, Any]] = []
    for override in overrides:
        block_hashes = extract_block_hashes(
            framework_templates_dir,
            override["target"],
            override["blocks"],
        )
        entries.append(
            {
                "source": override["source"],
                "target": override["target"],
                "blocks": override["blocks"],
                "framework_version": framework_version,
                "block_hashes": block_hashes,
            }
        )

    return {"template_overrides": entries}


def save_registry(registry: dict[str, Any], output_path: Path) -> None:
    """Write the override registry to disk.

    Args:
        registry: Registry dict from :func:`build_registry`.
        output_path: Path to write (typically ``.dazzle/overrides.json``).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "Override registry saved to %s (%d overrides)",
        output_path,
        len(registry.get("template_overrides", [])),
    )


def load_registry(registry_path: Path) -> dict[str, Any]:
    """Load an existing override registry from disk.

    Returns an empty registry if the file doesn't exist.
    """
    if not registry_path.is_file():
        return {"template_overrides": []}
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return {"template_overrides": []}


def check_overrides(
    project_templates_dir: Path,
    framework_templates_dir: Path,
    registry_path: Path,
) -> list[dict[str, Any]]:
    """Check registered overrides against current framework templates.

    Compares stored block hashes with current framework block content
    to detect when a framework upgrade has changed a block that the
    project overrides.

    Args:
        project_templates_dir: Path to the project's ``templates/`` directory.
        framework_templates_dir: Path to the framework's ``templates/`` directory.
        registry_path: Path to the ``.dazzle/overrides.json`` file.

    Returns:
        List of check results, each with keys:
        ``source``, ``target``, ``block``, ``status`` ("ok" or "changed"),
        ``old_hash``, ``new_hash``.
    """
    registry = load_registry(registry_path)
    results: list[dict[str, Any]] = []

    for entry in registry.get("template_overrides", []):
        target = entry["target"]
        stored_hashes = entry.get("block_hashes", {})

        current_hashes = extract_block_hashes(
            framework_templates_dir,
            target,
            entry.get("blocks", []),
        )

        for block_name in entry.get("blocks", []):
            old_hash = stored_hashes.get(block_name, "")
            new_hash = current_hashes.get(block_name, "")

            if not old_hash:
                status = "new"
            elif old_hash == new_hash:
                status = "ok"
            else:
                status = "changed"

            results.append(
                {
                    "source": entry["source"],
                    "target": target,
                    "block": block_name,
                    "status": status,
                    "old_hash": old_hash,
                    "new_hash": new_hash,
                }
            )

    return results
