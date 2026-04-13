"""Tests for parse_component_contract's `## Anchor` section handling (v1.0.3 task 1)."""

from __future__ import annotations

from pathlib import Path

from dazzle.agent.missions._shared import parse_component_contract


def _write_contract(tmp_path: Path, name: str, body: str) -> Path:
    """Write a minimal contract with a Quality Gates section + the given body."""
    path = tmp_path / f"{name}.md"
    path.write_text(f"# {name}\n\n{body}\n\n## Quality Gates\n\n1. Sample gate\n")
    return path


def test_parse_contract_extracts_anchor_from_section(tmp_path: Path) -> None:
    path = _write_contract(tmp_path, "auth-page", "## Anchor\n\n/login")

    contract = parse_component_contract(path)

    assert contract.component_name == "auth-page"
    assert contract.anchor == "/login"


def test_parse_contract_anchor_none_when_section_missing(tmp_path: Path) -> None:
    path = _write_contract(tmp_path, "no-anchor", "")

    contract = parse_component_contract(path)

    assert contract.anchor is None


def test_parse_contract_anchor_none_when_section_empty(tmp_path: Path) -> None:
    path = _write_contract(tmp_path, "empty-anchor", "## Anchor\n")

    contract = parse_component_contract(path)

    assert contract.anchor is None


def test_parse_contract_anchor_takes_first_non_blank_line(tmp_path: Path) -> None:
    path = _write_contract(
        tmp_path,
        "multi-line-anchor",
        "## Anchor\n\n\n/app/dashboard\n\nsome trailing comment\n",
    )

    contract = parse_component_contract(path)

    assert contract.anchor == "/app/dashboard"
