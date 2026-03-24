"""Tests for compliance taxonomy loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.compliance.models import EvidenceItem, EvidenceMap, Taxonomy
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


# ---------------------------------------------------------------------------
# SOC 2 Taxonomy (#657)
# ---------------------------------------------------------------------------

SOC2_FRAMEWORK = (
    Path(__file__).parents[2] / "src" / "dazzle" / "compliance" / "frameworks" / "soc2.yaml"
)


class TestSoc2Taxonomy:
    """Tests for SOC 2 Trust Services Criteria taxonomy (#657)."""

    def test_load_soc2_taxonomy(self) -> None:
        """Full soc2.yaml loads and has expected structure."""
        tax = load_taxonomy(SOC2_FRAMEWORK)
        assert isinstance(tax, Taxonomy)
        assert tax.id == "soc2"
        assert len(tax.themes) == 5
        theme_ids = {t.id for t in tax.themes}
        assert theme_ids == {
            "security",
            "availability",
            "confidentiality",
            "processing_integrity",
            "privacy",
        }

    def test_soc2_control_count(self) -> None:
        """SOC 2 TSC has 63 controls across all categories."""
        tax = load_taxonomy(SOC2_FRAMEWORK)
        total = sum(len(th.controls) for th in tax.themes)
        assert total == 63

    def test_soc2_theme_control_counts(self) -> None:
        """Each theme has the correct number of controls."""
        tax = load_taxonomy(SOC2_FRAMEWORK)
        counts = {th.id: len(th.controls) for th in tax.themes}
        assert counts["security"] == 33
        assert counts["availability"] == 3
        assert counts["confidentiality"] == 2
        assert counts["processing_integrity"] == 5
        assert counts["privacy"] == 20

    def test_soc2_points_of_focus(self) -> None:
        """Controls with points_of_focus preserve them through load."""
        tax = load_taxonomy(SOC2_FRAMEWORK)
        # CC6.1 should have points_of_focus
        by_id = tax.controls_by_id()
        cc6_1 = by_id.get("CC6.1")
        assert cc6_1 is not None
        assert cc6_1.attributes is not None
        pof = cc6_1.attributes.get("points_of_focus", [])
        assert isinstance(pof, list)
        assert len(pof) > 0
        assert all(isinstance(p, str) for p in pof)


class TestSoc2MiniFixture:
    """Tests for SOC 2 mini fixture and pipeline integration."""

    def test_load_mini_soc2(self) -> None:
        """Mini SOC 2 fixture loads correctly."""
        tax = load_taxonomy(FIXTURES / "mini_soc2_taxonomy.yaml")
        assert tax.id == "soc2_test"
        assert len(tax.themes) == 2

    def test_soc2_compile_pipeline(self) -> None:
        """Full compile pipeline with mock evidence."""
        from dazzle.compliance.compiler import compile_auditspec

        tax = load_taxonomy(FIXTURES / "mini_soc2_taxonomy.yaml")
        evidence = EvidenceMap(
            items={
                "permit": [
                    EvidenceItem(
                        construct="permit",
                        entity="Task",
                        detail="admin: create, read, update, delete",
                        dsl_ref="Task.access",
                    )
                ],
            }
        )
        result = compile_auditspec(tax, evidence)
        # CC6.1 has permit in dsl_evidence → should be evidenced
        by_id = {r.control_id: r for r in result.controls}
        assert by_id["CC6.1"].status == "evidenced"
        assert by_id["CC6.1"].tier == 1
        # CC1.1 has empty dsl_evidence → excluded
        assert by_id["CC1.1"].status == "excluded"
        assert by_id["CC1.1"].tier == 0
        # CC8.1 has transitions+processes but no evidence → gap
        assert by_id["CC8.1"].status == "gap"
        assert by_id["CC8.1"].tier == 3
        # P6.1 has permit → evidenced (permit evidence matches)
        assert by_id["P6.1"].status == "evidenced"
        # Summary counts
        assert result.summary.evidenced >= 2
        assert result.summary.excluded >= 1

    def test_soc2_mini_points_of_focus(self) -> None:
        """Mini fixture preserves points_of_focus in attributes."""
        tax = load_taxonomy(FIXTURES / "mini_soc2_taxonomy.yaml")
        by_id = tax.controls_by_id()
        cc6_1 = by_id["CC6.1"]
        assert cc6_1.attributes is not None
        pof = cc6_1.attributes["points_of_focus"]
        assert pof == [
            "Restricts Access",
            "Protects Encryption Keys",
            "Uses Encryption to Protect Data",
        ]
