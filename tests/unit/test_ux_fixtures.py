"""Tests for UX verification fixture generation."""

from datetime import UTC, datetime
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

    def test_fk_chain_seeds_in_dependency_order(self) -> None:
        """Regression: fixtures are emitted FK-dependency-first so a required
        FK resolves to an already-emitted fixture id.

        In declaration order, an entity whose required-FK target is declared
        later gets its ref skipped → the ``/__test__/seed`` insert fails the
        NOT NULL constraint → that table stays empty → the entity's
        ``list_page`` contract spuriously fails with "no clickable rows".
        ``acme_billing`` is a real FK chain: Organization ← Project/User ←
        Invoice/Membership.
        """
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "acme_billing"
        appspec = load_project_appspec(project)
        payload = generate_seed_payload(appspec)
        fixtures = payload["fixtures"]

        first_idx: dict[str, int] = {}
        id_to_entity: dict[str, str] = {}
        for i, fx in enumerate(fixtures):
            first_idx.setdefault(fx["entity"], i)
            id_to_entity[fx["id"]] = fx["entity"]

        # The referenced parent must actually be seeded.
        assert "Organization" in first_idx, "Organization fixtures missing"

        # Every FK ref must point to an entity that first appears no later
        # than the referencing fixture, so the seed endpoint can resolve it.
        for i, fx in enumerate(fixtures):
            for field_name, ref_id in (fx.get("refs") or {}).items():
                ref_entity = id_to_entity.get(ref_id)
                assert ref_entity is not None, (
                    f"{fx['entity']}.{field_name} refs unknown fixture {ref_id!r}"
                )
                assert first_idx[ref_entity] <= i, (
                    f"{fx['entity']}.{field_name} refs {ref_entity}, "
                    f"which is seeded later — not FK-dependency-ordered"
                )


class TestLifecycleSeedIntegrity:
    """TR-10: demo/UX seeds must not put resolved_at on open tickets or in the future."""

    def test_support_tickets_open_rows_omit_resolved_at(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        project = Path(__file__).resolve().parents[2] / "examples" / "support_tickets"
        appspec = load_project_appspec(project)
        payload = generate_seed_payload(appspec)
        now = datetime.now(UTC)
        tickets = [f for f in payload["fixtures"] if f["entity"] == "Ticket"]
        assert tickets, "expected Ticket fixtures"
        for fx in tickets:
            data = fx["data"]
            status = str(data.get("status") or "").lower()
            if status in {"open", "in_progress", "new", "pending"}:
                assert "resolved_at" not in data, (
                    f"open-ish ticket {fx['id']} status={status!r} must not set resolved_at"
                )
                assert "resolution" not in data, (
                    f"open-ish ticket {fx['id']} must not set resolution text"
                )
            for key, val in data.items():
                if not isinstance(val, str) or "T" not in val:
                    continue
                if key.lower().endswith("_at") or "date" in key.lower():
                    # ISO datetimes we emit should parse and not be in the future
                    # (due/deadline fields may be slightly ahead — skip those names).
                    if any(t in key.lower() for t in ("due", "deadline", "expires", "scheduled")):
                        continue
                    try:
                        parsed = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    assert parsed <= now + __import__("datetime").timedelta(minutes=1), (
                        f"{fx['entity']}.{key}={val} is in the future (TR-10)"
                    )
