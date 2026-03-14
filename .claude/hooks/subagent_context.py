#!/usr/bin/env python3
"""SubagentStart hook: Inject Dazzle project context into subagents.

Reads the project's dazzle.toml and DSL files to build a context summary,
then returns it as additionalContext so every subagent is oriented to the
Dazzle codebase.
"""

import json
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


def _get_project_name(project_root: Path) -> str:
    """Read project name from dazzle.toml."""
    toml_path = project_root / "dazzle.toml"
    if not toml_path.exists():
        return "unknown"
    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("name", "unknown")
    except Exception:
        return "unknown"


def _get_git_branch(project_root: Path) -> str:
    """Get current git branch."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _get_dsl_names(project_root: Path) -> dict[str, list[str]]:
    """Extract entity and surface names from DSL files."""
    entities: list[str] = []
    surfaces: list[str] = []

    # Search only common DSL locations to avoid slow full-tree scan
    search_dirs = [project_root / "dsl", project_root / "src", project_root / "examples"]
    dsl_files = []
    for d in search_dirs:
        if d.exists():
            dsl_files.extend(d.rglob("*.dazzle"))
    # Also check project root directly
    dsl_files.extend(project_root.glob("*.dazzle"))

    for dsl_file in dsl_files[:50]:
        try:
            content = dsl_file.read_text()
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("entity "):
                    parts = stripped.split('"')
                    if len(parts) >= 2:
                        entities.append(parts[1])
                elif stripped.startswith("surface "):
                    parts = stripped.split('"')
                    if len(parts) >= 2:
                        surfaces.append(parts[1])
        except Exception:
            continue

    return {"entities": entities[:20], "surfaces": surfaces[:20]}


def main():
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    project_root = Path.cwd()
    project_name = _get_project_name(project_root)
    branch = _get_git_branch(project_root)
    dsl_names = _get_dsl_names(project_root)

    context_parts = [
        f"Dazzle project: {project_name} (branch: {branch})",
        "Key dirs: src/dazzle/core/ (parser+IR), src/dazzle/mcp/ (MCP server), "
        "src/dazzle_back/ (FastAPI runtime), src/dazzle_ui/ (UI templates)",
        "Commands: dazzle serve|validate|lint|mcp|lsp",
        "Quality: ruff check src/ tests/ --fix && ruff format src/ tests/ | mypy src/dazzle | pytest tests/ -m 'not e2e'",
        "MCP tools: dsl, story, rhythm, process, test_design, discovery, graph, knowledge, "
        "semantics, composition, policy, sentinel, test_intelligence, api_pack, mock, "
        "demo_data, pitch, sitespec, status, spec_analyze, bootstrap, pulse",
    ]

    if dsl_names["entities"]:
        context_parts.append(f"Entities: {', '.join(dsl_names['entities'])}")
    if dsl_names["surfaces"]:
        context_parts.append(f"Surfaces: {', '.join(dsl_names['surfaces'])}")

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SubagentStart",
            "additionalContext": "\n".join(context_parts),
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
