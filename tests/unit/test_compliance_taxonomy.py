"""Tests for compliance taxonomy loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.compliance.models import Taxonomy
from dazzle.compliance.taxonomy import TaxonomyError, load_taxonomy

FIXTURES = Path(__file__).parent / "fixtures" / "compliance"


class TestLoadTaxonomy:
    def test_load_valid_taxonomy(self) -> None:
        tax = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
        assert isinstance(tax, Taxonomy)
        assert tax.id == "mini_test"
        assert len(tax.themes) >= 1

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(TaxonomyError, match="not found"):
            load_taxonomy(tmp_path / "nonexistent.yaml")

    def test_missing_framework_key_raises(self) -> None:
        with pytest.raises(TaxonomyError, match="framework"):
            load_taxonomy(FIXTURES / "bad_taxonomy.yaml")

    def test_controls_by_id(self) -> None:
        tax = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
        by_id = tax.controls_by_id()
        assert isinstance(by_id, dict)
        assert all(isinstance(k, str) for k in by_id)

    def test_all_controls_flat(self) -> None:
        tax = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
        controls = tax.all_controls()
        assert len(controls) > 0

    def test_missing_control_id_raises(self, tmp_path: Path) -> None:
        """Taxonomy with control missing 'id' field should raise TaxonomyError."""
        bad = tmp_path / "bad.yaml"
        bad.write_text(
            "framework:\n"
            "  id: test\n"
            "  name: Test\n"
            "  themes:\n"
            "    - id: t1\n"
            "      name: Theme 1\n"
            "      controls:\n"
            "        - name: Missing ID\n"
        )
        with pytest.raises(TaxonomyError, match="Missing required field"):
            load_taxonomy(bad)

    def test_missing_themes_returns_empty(self, tmp_path: Path) -> None:
        """Taxonomy with no themes is valid (just empty)."""
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text("framework:\n  id: test\n  name: Test\n")
        tax = load_taxonomy(minimal)
        assert tax.themes == []
