"""Tests for UX verification fixture generation."""

from pathlib import Path

from dazzle.testing.ux.fixtures import generate_seed_payload


class TestFixtureGeneration:
    def test_generates_fixtures_for_simple_task(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        payload = generate_seed_payload(appspec)
        assert "fixtures" in payload
        assert len(payload["fixtures"]) > 0

    def test_each_entity_has_fixtures(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        payload = generate_seed_payload(appspec)
        entity_names = {f["entity"] for f in payload["fixtures"]}
        # At least one surfaced entity should have fixtures
        surfaced = {s.entity_ref for s in appspec.surfaces if s.entity_ref}
        assert surfaced.intersection(entity_names)

    def test_fixture_has_required_fields(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
        appspec = load_project_appspec(project)
        payload = generate_seed_payload(appspec)
        for fixture in payload["fixtures"]:
            assert "id" in fixture
            assert "entity" in fixture
            assert "data" in fixture
            assert isinstance(fixture["data"], dict)
