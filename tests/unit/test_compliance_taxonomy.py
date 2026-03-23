"""Tests for dazzle.compliance.taxonomy module."""

from pathlib import Path

import pytest

from dazzle.compliance.taxonomy import TaxonomyError, load_taxonomy

FIXTURES = Path(__file__).parent / "fixtures" / "compliance"


def test_load_valid_taxonomy():
    tax = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
    assert tax.id == "mini_test"
    assert tax.name == "Mini Test Framework"
    assert tax.jurisdiction == "UK"
    assert tax.version == "1.0"
    assert len(tax.themes) == 2


def test_all_controls():
    tax = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
    controls = tax.all_controls()
    assert len(controls) == 5
    ids = [c.id for c in controls]
    assert "AC-1" in ids
    assert "OP-2" in ids


def test_controls_by_id():
    tax = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
    by_id = tax.controls_by_id()
    assert "AC-1" in by_id
    assert by_id["AC-1"].name == "Access Policy"


def test_dsl_evidence_loaded():
    tax = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
    ac1 = tax.controls_by_id()["AC-1"]
    assert len(ac1.dsl_evidence) == 1
    assert ac1.dsl_evidence[0].construct == "permit"


def test_control_without_evidence():
    tax = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
    op2 = tax.controls_by_id()["OP-2"]
    assert len(op2.dsl_evidence) == 0


def test_missing_file_raises():
    with pytest.raises(TaxonomyError, match="not found"):
        load_taxonomy(FIXTURES / "nonexistent.yaml")


def test_bad_taxonomy_raises():
    with pytest.raises(TaxonomyError, match="Missing 'framework' key"):
        load_taxonomy(FIXTURES / "bad_taxonomy.yaml")


def test_theme_attributes():
    tax = load_taxonomy(FIXTURES / "mini_taxonomy.yaml")
    assert tax.themes[0].id == "theme_access"
    assert tax.themes[0].name == "Access Control"
    assert len(tax.themes[0].controls) == 3
    assert tax.themes[1].id == "theme_ops"
    assert len(tax.themes[1].controls) == 2
