"""The signing_validation fixture (booted by the opt-in Postgres signing trials)
still parses and declares exactly one signable entity, TestDoc."""

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "signing_validation"


def test_fixture_declares_one_signable_entity() -> None:
    appspec = load_project_appspec(FIXTURE)
    assert [e.name for e in appspec.domain.entities if e.signable] == ["TestDoc"]
