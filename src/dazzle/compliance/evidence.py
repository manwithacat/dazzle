"""DSL Evidence Extractor — pulls compliance-relevant data from Dazzle DSL specifications.

Uses:
1. Dazzle CLI (python3 -m dazzle policy coverage) for permit evidence (proper AST parser)
2. Targeted regex for simple patterns (classify, visible directives)
3. JSON parsing for processes and stories
4. Anchored entity search for scope/transitions (never greedy entity block regex)

Key principle: **never regex-parse entity blocks with greedy patterns**.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Top-level DSL keywords that end an entity block
_TOP_LEVEL_KEYWORDS = (
    "persona ",
    "workspace ",
    "scenario ",
    "rhythm ",
    "policies:",
    "archetype ",
    "surface ",
    "param ",
)


# ---------------------------------------------------------------------------
# DSL file discovery
# ---------------------------------------------------------------------------


def _find_dsl_files(project_path: Path) -> list[Path]:
    """Discover DSL files in a project directory.

    Searches for:
    1. dsl/*.dsl (standard Dazzle convention)
    2. *.dsl in project root (single-file projects)
    """
    dsl_dir = project_path / "dsl"
    if dsl_dir.is_dir():
        files = sorted(dsl_dir.glob("*.dsl"))
        if files:
            return files

    root_files = sorted(project_path.glob("*.dsl"))
    if root_files:
        return root_files

    return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_dazzle_cli(project_path: Path, *args: str) -> Any:
    """Run a Dazzle CLI command and return parsed JSON output."""
    cmd = ["python3", "-m", "dazzle", *args, "--format", "json"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(project_path),
        )
        if result.returncode != 0:
            logger.debug("Dazzle CLI failed: %s", result.stderr.strip())
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as exc:
        logger.debug("Dazzle CLI error: %s", exc)
        return None


def _read_dsl(project_path: Path) -> str:
    """Read all DSL file contents, concatenated."""
    files = _find_dsl_files(project_path)
    if not files:
        raise FileNotFoundError(f"No .dsl files found in {project_path}/dsl/ or {project_path}/")
    parts = []
    for f in files:
        parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _get_entity_names(project_path: Path) -> list[str]:
    """Extract entity names from the DSL using a line-start anchored regex."""
    text = _read_dsl(project_path)
    return re.findall(r'^entity\s+(\w+)\s+"', text, re.MULTILINE)


def _get_entity_blocks(project_path: Path) -> dict[str, str]:
    """Return a dict mapping entity name -> block text.

    Uses anchored search: find each entity's start line, then bound it
    by the next entity or next top-level keyword.
    """
    text = _read_dsl(project_path)
    names = _get_entity_names(project_path)

    # Find the start offset of each entity
    starts: list[tuple[str, int]] = []
    for name in names:
        marker = f'entity {name} "'
        idx = text.find(marker)
        if idx >= 0:
            starts.append((name, idx))

    # Sort by position (should already be in order, but be safe)
    starts.sort(key=lambda x: x[1])

    blocks: dict[str, str] = {}
    for i, (name, start) in enumerate(starts):
        if i + 1 < len(starts):
            end = starts[i + 1][1]
        else:
            # Last entity — find next top-level keyword
            end = len(text)
            for keyword in _TOP_LEVEL_KEYWORDS:
                pos = text.find(f"\n{keyword}", start + 1)
                if pos >= 0 and pos < end:
                    end = pos
        blocks[name] = text[start:end]

    return blocks


# ---------------------------------------------------------------------------
# Classify evidence
# ---------------------------------------------------------------------------


def extract_classify_evidence(project_path: Path) -> list[dict[str, str]]:
    """Extract classify directives from the policies: block.

    Pattern: ``classify Entity.field as CATEGORY``
    """
    text = _read_dsl(project_path)
    matches = re.findall(r"classify\s+(\w+)\.(\w+)\s+as\s+(\w+)", text)
    return [{"entity": m[0], "field": m[1], "classification": m[2]} for m in matches]


# ---------------------------------------------------------------------------
# Permit evidence
# ---------------------------------------------------------------------------


def extract_permit_evidence(project_path: Path) -> dict[str, dict]:
    """Extract permit (RBAC) rules for each entity.

    Tries Dazzle CLI first; falls back to anchored regex.
    """
    cli_result = _run_dazzle_cli(project_path, "policy", "coverage")
    if cli_result and isinstance(cli_result, dict):
        return _normalize_cli_permit(cli_result)
    return _extract_permit_via_regex(project_path)


def _normalize_cli_permit(cli_data: dict) -> dict[str, dict]:
    """Normalize CLI output into our standard format."""
    result: dict[str, dict] = {}
    for entity_name, entity_data in cli_data.items():
        if isinstance(entity_data, dict) and "operations" in entity_data:
            result[entity_name] = entity_data
    return result if result else {}


def _extract_permit_via_regex(project_path: Path) -> dict[str, dict]:
    """Extract permit blocks using anchored entity search."""
    blocks = _get_entity_blocks(project_path)
    result: dict[str, dict] = {}

    permit_re = re.compile(r"^\s+permit:\s*$", re.MULTILINE)
    for entity_name, block_text in blocks.items():
        pm = permit_re.search(block_text)
        if not pm:
            continue

        # Parse operations after permit:
        operations: dict[str, list[str]] = {}
        # Only look at text after "permit:" until next block keyword
        after_permit = block_text[pm.end() :]
        for line in after_permit.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            # Stop at next block-level keyword
            if stripped.startswith(
                (
                    "scope:",
                    "transitions:",
                    "index ",
                    "invariant",
                    "examples:",
                    "entity ",
                    "surface ",
                )
            ):
                break
            om = re.match(r"(read|list|create|update|delete):\s+(.+)", stripped)
            if om:
                op_name = om.group(1)
                roles_str = om.group(2)
                roles = _extract_roles(roles_str)
                operations[op_name] = roles

        if operations:
            result[entity_name] = {"operations": operations}

    return result


def _extract_roles(expr: str) -> list[str]:
    """Extract role names from a permit expression like ``role(teacher) or role(admin)``."""
    return re.findall(r"role\((\w+)\)", expr)


# ---------------------------------------------------------------------------
# Scope evidence
# ---------------------------------------------------------------------------


def extract_scope_evidence(project_path: Path) -> list[dict[str, Any]]:
    """Extract scope blocks using anchored entity search."""
    blocks = _get_entity_blocks(project_path)
    result: list[dict[str, Any]] = []

    for entity_name, block_text in blocks.items():
        scope_match = re.search(r"^\s+scope:\s*$", block_text, re.MULTILINE)
        if not scope_match:
            continue

        after_scope = block_text[scope_match.end() :]
        current_rule: dict[str, Any] | None = None

        for line in after_scope.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            # Stop at next block keyword
            if stripped.startswith(
                (
                    "permit:",
                    "transitions:",
                    "index ",
                    "invariant",
                    "examples:",
                    "entity ",
                    "surface ",
                )
            ):
                break

            # Scope rule line: "read: school = current_user.school" or "read: all"
            rule_match = re.match(r"(read|list|create|update|delete):\s+(.+)", stripped)
            if rule_match:
                if current_rule:
                    result.append(current_rule)
                current_rule = {
                    "entity": entity_name,
                    "operation": rule_match.group(1),
                    "rule": rule_match.group(2),
                    "for_roles": [],
                }
                continue

            # for: clause
            for_match = re.match(r"for:\s+(.+)", stripped)
            if for_match and current_rule:
                roles = [r.strip() for r in for_match.group(1).split(",")]
                current_rule["for_roles"] = roles
                continue

        if current_rule:
            result.append(current_rule)

    return result


# ---------------------------------------------------------------------------
# Transition evidence
# ---------------------------------------------------------------------------


def extract_transition_evidence(project_path: Path) -> list[dict[str, Any]]:
    """Extract transition guards using anchored entity search."""
    blocks = _get_entity_blocks(project_path)
    result: list[dict[str, Any]] = []

    transition_re = re.compile(r"(\w+)\s*->\s*(\w+):\s+(.+)", re.MULTILINE)

    for entity_name, block_text in blocks.items():
        tm = re.search(r"^\s+transitions:\s*$", block_text, re.MULTILINE)
        if not tm:
            continue

        after_trans = block_text[tm.end() :]
        for line in after_trans.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            # Stop at next block keyword
            if stripped.startswith(
                ("permit:", "scope:", "index ", "invariant", "examples:", "entity ", "surface ")
            ):
                break

            t_match = transition_re.match(stripped)
            if t_match:
                roles = _extract_roles(t_match.group(3))
                result.append(
                    {
                        "entity": entity_name,
                        "from_state": t_match.group(1),
                        "to_state": t_match.group(2),
                        "roles": roles,
                        "guard_expr": t_match.group(3).strip(),
                    }
                )

    return result


# ---------------------------------------------------------------------------
# Visible evidence
# ---------------------------------------------------------------------------


def extract_visible_evidence(project_path: Path) -> list[dict[str, Any]]:
    """Extract visible: directives with context about which entity/surface they appear in."""
    text = _read_dsl(project_path)
    lines = text.split("\n")
    result: list[dict[str, Any]] = []
    current_entity = None
    current_surface = None

    for line in lines:
        # Track current entity/surface context
        entity_m = re.match(r'^entity\s+(\w+)\s+"', line)
        if entity_m:
            current_entity = entity_m.group(1)
            current_surface = None
            continue

        surface_m = re.match(r'^surface\s+(\w+)\s+"', line)
        if surface_m:
            current_surface = surface_m.group(1)
            current_entity = None
            continue

        # Reset context on other top-level blocks
        if line and not line[0].isspace() and not line.startswith("#"):
            for kw in _TOP_LEVEL_KEYWORDS:
                if line.startswith(kw):
                    current_entity = None
                    current_surface = None
                    break

        if "visible:" not in line:
            continue

        # Skip param scope: lines that happen to say "scope: tenant"
        stripped = line.strip()
        if stripped.startswith("scope:"):
            continue

        # Extract the visible expression
        vis_match = re.search(r"visible:\s+(.+)", stripped)
        if not vis_match:
            continue

        roles = _extract_roles(vis_match.group(1))
        # Try to determine what the visible: is attached to
        field_match = re.match(r'field\s+(\w+)\s+"([^"]*)"', stripped)
        entry: dict[str, Any] = {
            "context": current_entity or current_surface or "unknown",
            "context_type": "entity" if current_entity else "surface",
            "roles": roles,
            "expr": vis_match.group(1).strip(),
        }
        if field_match:
            entry["field"] = field_match.group(1)
            entry["label"] = field_match.group(2)
            entry["type"] = "field"
        else:
            entry["type"] = "section"

        result.append(entry)

    return result


# ---------------------------------------------------------------------------
# Persona evidence
# ---------------------------------------------------------------------------


def extract_persona_evidence(project_path: Path) -> list[dict[str, Any]]:
    """Extract persona blocks from the DSL."""
    text = _read_dsl(project_path)
    personas: list[dict[str, Any]] = []

    # Find all persona block starts
    persona_re = re.compile(r'^persona\s+(\w+)\s+"([^"]*)":', re.MULTILINE)
    matches = list(persona_re.finditer(text))

    for i, m in enumerate(matches):
        start = m.end()
        # Find end: next persona or next top-level keyword
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(text)
            for kw in _TOP_LEVEL_KEYWORDS:
                if kw == "persona ":
                    continue
                pos = text.find(f"\n{kw}", start)
                if 0 <= pos < end:
                    end = pos

        block = text[start:end]
        persona: dict[str, Any] = {
            "name": m.group(1),
            "label": m.group(2),
        }

        # Extract fields
        desc_m = re.search(r'description:\s+"([^"]*)"', block)
        if desc_m:
            persona["description"] = desc_m.group(1)

        goals_m = re.search(r'goals:\s+"([^"]*)"', block)
        if goals_m:
            persona["goals"] = [g.strip() for g in goals_m.group(1).split('",')]
        else:
            # Multi-value goals
            goal_matches = re.findall(r'goals:.*?"([^"]+)"', block)
            if goal_matches:
                persona["goals"] = goal_matches

        prof_m = re.search(r"proficiency:\s+(\w+)", block)
        if prof_m:
            persona["proficiency"] = prof_m.group(1)

        ws_m = re.search(r"default_workspace:\s+(\w+)", block)
        if ws_m:
            persona["default_workspace"] = ws_m.group(1)

        personas.append(persona)

    return personas


# ---------------------------------------------------------------------------
# Process evidence
# ---------------------------------------------------------------------------


def extract_process_evidence(project_path: Path) -> list[dict[str, Any]]:
    """Parse process definitions from .dazzle/processes/ JSON files."""
    proc_dir = project_path / ".dazzle" / "processes"
    if not proc_dir.exists():
        return []

    result: list[dict[str, Any]] = []
    for json_file in sorted(proc_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse %s: %s", json_file.name, exc)
            continue

        processes: list[dict] = []
        if isinstance(data, list):
            processes = data
        elif isinstance(data, dict) and "processes" in data:
            processes = data["processes"]

        for proc in processes:
            if not isinstance(proc, dict):
                continue
            result.append(
                {
                    "name": proc.get("name", "unknown"),
                    "title": proc.get("title", ""),
                    "description": proc.get("description", ""),
                    "file": json_file.name,
                    "steps": proc.get("steps", []),
                    "implements": proc.get("implements", []),
                    "trigger": proc.get("trigger", ""),
                }
            )

    return result


# ---------------------------------------------------------------------------
# Story evidence
# ---------------------------------------------------------------------------


def extract_story_evidence(project_path: Path) -> list[dict[str, Any]]:
    """Parse stories from .dazzle/stories/stories.json."""
    stories_file = project_path / ".dazzle" / "stories" / "stories.json"
    if not stories_file.exists():
        return []

    try:
        data = json.loads(stories_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    stories: list[dict] = []
    if isinstance(data, list):
        stories = data
    elif isinstance(data, dict) and "stories" in data:
        stories = data["stories"]

    result: list[dict[str, Any]] = []
    for s in stories:
        if not isinstance(s, dict):
            continue
        entry: dict[str, Any] = {
            "title": s.get("title", ""),
        }
        # Use story_id if present, fall back to id
        if "story_id" in s:
            entry["story_id"] = s["story_id"]
        elif "id" in s:
            entry["story_id"] = s["id"]

        # Include useful metadata
        for key in (
            "actor",
            "scope",
            "preconditions",
            "happy_path_outcome",
            "trigger",
            "status",
            "given",
            "when",
            "then",
        ):
            if key in s:
                entry[key] = s[key]

        result.append(entry)

    return result


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


def extract_all_evidence(project_path: Path) -> dict[str, Any]:
    """Run all extractors and return a combined dict."""
    return {
        "classify": extract_classify_evidence(project_path),
        "permit": extract_permit_evidence(project_path),
        "scope": extract_scope_evidence(project_path),
        "transitions": extract_transition_evidence(project_path),
        "visible": extract_visible_evidence(project_path),
        "processes": extract_process_evidence(project_path),
        "stories": extract_story_evidence(project_path),
        "personas": extract_persona_evidence(project_path),
    }
