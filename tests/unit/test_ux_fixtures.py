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

    def test_support_tickets_user_fixtures_pass_staff_selector_filter(self) -> None:
        """Cycle 2087: INTERACTION_WALK needs ≥2 context-options after
        agent_console ``filter: support_tier = l1 and department != External``.
        NULL department/tier (optional-skip) would empty the picker.
        """
        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle.http.runtime.workspace_route_builder import (
            context_selector_option_filters,
        )

        project = Path(__file__).resolve().parents[2] / "examples" / "support_tickets"
        appspec = load_project_appspec(project)
        ws = next(w for w in appspec.workspaces if w.name == "agent_console")
        assert ws.context_selector is not None
        opt = context_selector_option_filters(ws.context_selector)
        payload = generate_seed_payload(appspec)
        users = [f["data"] for f in payload["fixtures"] if f["entity"] == "User"]
        matching = [
            u
            for u in users
            if u.get("support_tier") == opt.get("support_tier")
            and u.get("department") != opt.get("department__ne")
            and u.get("department") is not None
        ]
        assert len(matching) >= 2, (
            f"UX seed User rows must populate staff grain for context_select; "
            f"got {len(matching)} matching of {len(users)} ({opt=})"
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
