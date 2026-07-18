"""Schema + inventory unit tests for agent QA ladder (#1625)."""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.agent.missions.trial import build_trial_mission
from dazzle.qa.trial_friction import (
    filter_auto_seed,
    friction_cluster_key,
    is_auto_seed_eligible,
    normalize_friction_entry,
)
from dazzle.qa.trial_inventory import build_coverage_inventory, classify_http_status
from dazzle.qa.trial_report import build_trial_report, trial_report_to_json


class TestFrictionSchema:
    def test_normalize_maps_framework_vs_app(self) -> None:
        e = normalize_friction_entry(
            {
                "category": "bug",
                "severity": "high",
                "description": "x",
                "framework_vs_app": "framework",
            }
        )
        assert e["ownership"] == "framework"
        assert e["category"] == "bug"

    def test_story_gap_category(self) -> None:
        e = normalize_friction_entry({"category": "story_gap", "description": "can't find"})
        assert e["category"] == "story_gap"

    def test_auto_seed_product_medium_only(self) -> None:
        ok = {
            "category": "bug",
            "severity": "medium",
            "description": "broken queue",
            "ownership": "product",
        }
        assert is_auto_seed_eligible(ok)
        assert not is_auto_seed_eligible({**ok, "ownership": "seed"})
        assert not is_auto_seed_eligible({**ok, "severity": "low"})
        assert not is_auto_seed_eligible({**ok, "category": "praise"})

    def test_filter_and_cluster(self) -> None:
        rows = [
            {
                "category": "bug",
                "severity": "high",
                "description": "UUID leak",
                "ownership": "product",
            },
            {
                "category": "bug",
                "severity": "high",
                "description": "UUID   leak",
                "ownership": "product",
            },
            {
                "category": "bug",
                "severity": "high",
                "description": "timeout",
                "ownership": "harness",
            },
        ]
        seeded = filter_auto_seed(rows)
        assert len(seeded) == 2
        keys = {friction_cluster_key(r) for r in seeded}
        assert len(keys) == 1


class TestInventory:
    def test_build_from_minimal_appspec(self) -> None:
        appspec = SimpleNamespace(
            surfaces=[
                SimpleNamespace(name="ticket_list", entity_ref="Ticket", mode="list"),
                SimpleNamespace(name="ticket_create", entity_ref="Ticket", mode="create"),
                SimpleNamespace(name="ticket_view", entity_ref="Ticket", mode="view"),
            ],
            workspaces=[SimpleNamespace(name="manager_ops", title="Manager Ops")],
        )
        targets = build_coverage_inventory(appspec)
        urls = {t.url for t in targets}
        assert "/app" in urls
        assert "/app/ticket" in urls or any("/app/" in u for u in urls)
        assert any(t.kind == "workspace" for t in targets)
        # view surfaces need record id — not walkable in inventory A
        assert not any(t.kind == "surface_view" for t in targets)

    def test_classify_http(self) -> None:
        assert classify_http_status(200)[0] == "reached"
        assert classify_http_status(403) == ("rbac_denied", "rbac_expected")
        assert classify_http_status(404)[0] == "blocked"
        assert classify_http_status(500)[0] == "error"


class TestJourneyModeAndJson:
    def test_journey_mode_prompt(self) -> None:
        sink: dict = {"friction": []}
        m = build_trial_mission(
            {
                "name": "j",
                "login_persona": "manager",
                "user_identity": "You are Sam.",
                "business_context": "Busy.",
                "tasks": ["Find X"],
                "mode": "journey",
            },
            base_url="http://h",
            transcript_sink=sink,
        )
        assert m.context.get("mode") == "journey"
        assert "Journey-path drive rule" in m.system_prompt
        assert "URL shortcut" in m.system_prompt or "affordances" in m.system_prompt

    def test_ownership_on_record_friction(self) -> None:
        sink: dict = {"friction": []}
        m = build_trial_mission(
            {
                "name": "j",
                "login_persona": "manager",
                "user_identity": "You are Sam.",
                "business_context": "Busy.",
                "tasks": ["Find X"],
            },
            base_url="http://h",
            transcript_sink=sink,
        )
        tool = next(t for t in m.tools if t.name == "record_friction")
        tool.handler(
            category="story_gap",
            description="Cannot find reassignment",
            ownership="product",
            severity="high",
        )
        assert sink["friction"][0]["ownership"] == "product"
        assert sink["friction"][0]["category"] == "story_gap"

    def test_report_json_auto_seed(self) -> None:
        report = build_trial_report(
            scenario_name="s",
            user_identity="You are Sam.",
            friction=[
                {
                    "category": "bug",
                    "severity": "high",
                    "description": "broken",
                    "ownership": "product",
                },
                {
                    "category": "bug",
                    "severity": "high",
                    "description": "lazy",
                    "ownership": "harness",
                },
            ],
            verdict="conditional",
            recommend="conditional",
        )
        payload = trial_report_to_json(report)
        assert payload["schema_version"] == 2
        assert len(payload["auto_seed"]) == 1
        assert payload["auto_seed"][0]["ownership"] == "product"
