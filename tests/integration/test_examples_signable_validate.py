"""Integration test: contact_manager validates with EngagementLetter signable entity.

Verifies that:
1. ``dazzle validate`` exits 0 on contact_manager after signing.dsl is added.
2. The EngagementLetter entity is resolvable via ``dazzle inspect project``.
"""

import subprocess
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _run_validate(project_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["dazzle", "validate"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_inspect_entity(project_dir: Path, entity_name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["dazzle", "inspect", "project", "--entity", entity_name],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )


def test_contact_manager_validates_with_engagement_letter():
    project_dir = EXAMPLES / "contact_manager"
    result = _run_validate(project_dir)
    assert result.returncode == 0, (
        f"dazzle validate failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_contact_manager_engagement_letter_entity_inspectable():
    project_dir = EXAMPLES / "contact_manager"
    result = _run_inspect_entity(project_dir, "EngagementLetter")
    assert result.returncode == 0, (
        f"dazzle inspect project --entity EngagementLetter failed:\n"
        f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
    assert "EngagementLetter" in result.stdout, (
        f"EngagementLetter not found in inspect output:\n{result.stdout}"
    )
