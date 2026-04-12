"""Tests for parse_component_contract() — extracts spec info from a ux-architect markdown contract."""

from pathlib import Path

import pytest

from dazzle.agent.missions._shared import (
    parse_component_contract,
)

SAMPLE_CONTRACT = """# Dashboard Grid Component Contract

**Aesthetic target:** Linear
**Stack:** HTMX + Alpine + Tailwind

## Anatomy

- `grid-root` — CSS grid container, `grid-cols-12`, `gap-4`
- `grid-toolbar` — top strip: "Add card", "Save layout"
- `grid-card-wrapper` — grid-positioned wrapper around each Card

## Primitives invoked

- `drag-and-drop`
- `resize`

## Quality Gates

1. Drag a card less than 4px — does it stay put? (drag threshold)
2. Drag rapidly across the grid — does it stay locked to the cursor? (transform-only)
3. Resize a card to overlap another — does the border turn danger and revert on release? (collision detection)
4. Refresh the page mid-edit — does the layout revert to last saved? (persistence boundary)
5. Tab through the dashboard — can you reach every card and enter keyboard-move mode? (a11y)

## Open Questions for v0.2

- Responsive collapse
"""


@pytest.fixture
def sample_contract_file(tmp_path: Path) -> Path:
    p = tmp_path / "dashboard-grid.md"
    p.write_text(SAMPLE_CONTRACT)
    return p


class TestParseComponentContract:
    def test_extracts_component_name_from_filename(self, sample_contract_file: Path):
        contract = parse_component_contract(sample_contract_file)
        assert contract.component_name == "dashboard-grid"

    def test_extracts_five_quality_gates(self, sample_contract_file: Path):
        contract = parse_component_contract(sample_contract_file)
        assert len(contract.quality_gates) == 5

    def test_quality_gates_have_ids_and_descriptions(self, sample_contract_file: Path):
        contract = parse_component_contract(sample_contract_file)
        # Each gate should have a non-empty id and description
        for gate in contract.quality_gates:
            assert gate.id
            assert gate.description
            assert len(gate.description) > 10  # real sentence, not a stub

    def test_gate_ids_are_unique(self, sample_contract_file: Path):
        contract = parse_component_contract(sample_contract_file)
        ids = [g.id for g in contract.quality_gates]
        assert len(ids) == len(set(ids))

    def test_extracts_anatomy_parts(self, sample_contract_file: Path):
        contract = parse_component_contract(sample_contract_file)
        assert "grid-root" in contract.anatomy
        assert "grid-toolbar" in contract.anatomy
        assert "grid-card-wrapper" in contract.anatomy

    def test_extracts_primitives(self, sample_contract_file: Path):
        contract = parse_component_contract(sample_contract_file)
        assert "drag-and-drop" in contract.primitives
        assert "resize" in contract.primitives

    def test_missing_quality_gates_section_raises(self, tmp_path: Path):
        p = tmp_path / "broken.md"
        p.write_text("# Broken\n\nNo quality gates section here.\n")
        with pytest.raises(ValueError, match="Quality Gates"):
            parse_component_contract(p)

    def test_nonexistent_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_component_contract(tmp_path / "missing.md")

    def test_real_dashboard_grid_contract(self):
        """Smoke test against the actual skill artefact."""
        p = Path.home() / ".claude/skills/ux-architect/components/dashboard-grid.md"
        if not p.exists():
            pytest.skip("ux-architect skill not installed at expected location")
        contract = parse_component_contract(p)
        assert contract.component_name == "dashboard-grid"
        assert len(contract.quality_gates) == 5
