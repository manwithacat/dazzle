"""Shared private helpers for MCP handler functions.

Utilities that appear (often duplicated) across multiple handler files.
Handler files should import from here instead of re-defining locally.

Note: Higher-level shared infrastructure (load_project_appspec,
handler_error_json, extract_progress) lives in ``common.py``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.core.process import ProcessAdapter


# =============================================================================
# Text helpers
# =============================================================================


def slugify(text: str) -> str:
    """Convert text to a snake_case slug (max 30 chars).

    Duplicated in:
    - process.py (_slugify)
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "_", text)
    return text[:30]


# =============================================================================
# DSL / AppSpec loading
# =============================================================================


def load_app_spec(project_root: Path) -> AppSpec:
    """Load and build AppSpec from a project directory.

    Thin wrapper around ``common.load_project_appspec`` kept for
    call-site compatibility — callers may also import
    ``load_project_appspec`` from ``common`` directly.

    Duplicated in:
    - process.py (_load_app_spec)
    - process/storage.py (_load_app_spec)
    - process/coverage.py (_load_app_spec)
    - discovery.py (_load_appspec)
    """
    from .common import load_project_appspec

    return load_project_appspec(project_root)


# =============================================================================
# Process adapter
# =============================================================================


def get_process_adapter(project_root: Path) -> ProcessAdapter:
    """Get a LiteProcessAdapter for the given project.

    Duplicated in:
    - process.py (_get_process_adapter)
    - process/storage.py (_get_process_adapter)
    """
    from dazzle.core.process import LiteProcessAdapter

    db_path = project_root / ".dazzle" / "processes.db"
    return LiteProcessAdapter(db_path=db_path)


# =============================================================================
# Issue / lint helpers
# =============================================================================


def extract_issue_key(message: str) -> str:
    """Extract ``Entity.field`` key from a lint/validation message.

    Falls back to a truncated message if no entity/field pattern is found.

    Duplicated in:
    - dsl.py (_extract_issue_key)
    """
    entity_match = re.search(r"[Ee]ntity ['\"](\w+)['\"]", message)
    field_match = re.search(r"[Ff]ield ['\"](\w+)['\"]", message)

    if entity_match and field_match:
        return f"{entity_match.group(1)}.{field_match.group(1)}"
    if entity_match:
        return entity_match.group(1)

    return message[:80] if len(message) > 80 else message


# =============================================================================
# Discovery report helpers
# =============================================================================


def load_report_data(
    project_path: Path,
    session_id: str | None,
) -> tuple[dict[str, Any], str] | str:
    """Find and load a discovery report.

    Returns ``(data_dict, session_id)`` on success, or a JSON error string
    on failure.

    Defined in:
    - discovery.py (_load_report_data)
    """
    import json

    report_dir = project_path / ".dazzle" / "discovery"

    if session_id:
        report_file = report_dir / f"{session_id}.json"
    else:
        if not report_dir.exists():
            return json.dumps({"error": "No discovery reports found"})
        reports = sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not reports:
            return json.dumps({"error": "No discovery reports found"})
        report_file = reports[0]
        session_id = report_file.stem

    if not report_file.exists():
        return json.dumps({"error": f"Report not found: {session_id}"})

    try:
        data = json.loads(report_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return json.dumps({"error": f"Could not read report: {e}"})

    return data, session_id


def deserialize_observations(raw_observations: list[dict[str, Any]]) -> list[Any]:
    """Reconstruct Observation objects from serialized dicts.

    Defined in:
    - discovery.py (_deserialize_observations)
    """
    from dazzle.agent.transcript import Observation

    observations: list[Observation] = []
    for obs_dict in raw_observations:
        observations.append(
            Observation(
                category=obs_dict.get("category", "gap"),
                severity=obs_dict.get("severity", "medium"),
                title=obs_dict.get("title", ""),
                description=obs_dict.get("description", ""),
                location=obs_dict.get("location", ""),
                related_artefacts=obs_dict.get("related_artefacts", []),
                metadata=obs_dict.get("metadata", {}),
                step_number=obs_dict.get("step_number", 0),
            )
        )
    return observations
