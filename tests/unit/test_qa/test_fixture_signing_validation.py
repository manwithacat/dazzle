"""Tests for signing_validation fixture."""

from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "signing_validation"


def test_fixture_dazzle_toml_exists():
    assert (FIXTURE / "dazzle.toml").is_file()


def test_fixture_has_signable_entity():
    dsl_text = (FIXTURE / "dsl" / "app.dsl").read_text()
    assert "signable: true" in dsl_text
    assert "entity TestDoc" in dsl_text
