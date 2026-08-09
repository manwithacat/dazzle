"""Static hyperpart opportunity scan."""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.qa.hyperpart_opportunity import (
    build_opportunity_report,
    scan_appspec,
    scan_person_ref_opportunities,
)
from dazzle.qa.hyperpart_scenarios import catalogue_snapshot, load_scenarios


def _field(name: str, kind: str, ref_entity: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        type=SimpleNamespace(kind=kind, ref_entity=ref_entity or None),
    )


def _surface_with_widgets(
    name: str,
    entity: str,
    fields: list[tuple[str, str | None]],
    mode: str = "edit",
) -> SimpleNamespace:
    """fields: list of (field_name, widget or None)."""
    elements = [
        SimpleNamespace(field_name=fn, options={"widget": w} if w else {}) for fn, w in fields
    ]
    return SimpleNamespace(
        name=name,
        entity_ref=entity,
        mode=SimpleNamespace(value=mode),
        sections=[SimpleNamespace(elements=elements)],
    )


def _appspec_with_bool_settings(*, with_switch: bool = False) -> SimpleNamespace:
    entity = SimpleNamespace(
        name="AlertPref",
        fields=[
            _field("title", "str"),
            _field("notify_email", "bool"),
            _field("muted", "boolean"),
        ],
    )
    w = "switch" if with_switch else None
    return SimpleNamespace(
        domain=SimpleNamespace(entities=[entity]),
        surfaces=[
            _surface_with_widgets(
                "alert_settings",
                "AlertPref",
                [("title", None), ("notify_email", w), ("muted", w)],
                mode="edit",
            ),
        ],
        workspaces=[],
    )


def _surface(name: str, entity: str, fields: list[str], mode: str = "list") -> SimpleNamespace:
    elements = [SimpleNamespace(field_name=f) for f in fields]
    return SimpleNamespace(
        name=name,
        entity_ref=entity,
        mode=SimpleNamespace(value=mode),
        sections=[SimpleNamespace(elements=elements)],
    )


def _appspec() -> SimpleNamespace:
    entity = SimpleNamespace(
        name="Task",
        fields=[
            _field("title", "str"),
            _field("assigned_to", "ref", "User"),
            _field("client", "ref", "Client"),
            _field("status", "enum"),
        ],
    )
    return SimpleNamespace(
        domain=SimpleNamespace(entities=[entity]),
        surfaces=[
            _surface("TaskList", "Task", ["title", "assigned_to", "client", "status"]),
        ],
        workspaces=[
            SimpleNamespace(
                name="lead",
                regions=[
                    SimpleNamespace(
                        name="overdue_tasks",
                        title="Overdue",
                        source="Task",
                        display=SimpleNamespace(value="list"),
                    ),
                    SimpleNamespace(
                        name="done_queue",
                        title="Done",
                        source="Task",
                        display=SimpleNamespace(value="queue"),
                    ),
                ],
            )
        ],
    )


class TestScan:
    def test_person_ref_found(self) -> None:
        opps = scan_person_ref_opportunities(_appspec())
        fields = {(o.field, o.hyperpart) for o in opps}
        assert ("assigned_to", "avatar") in fields
        assert all(
            o.status in ("emit_covered", "emit_partial", "default_emit")
            for o in opps
            if o.field == "assigned_to"
        )
        # Client is not person
        assert not any(o.field == "client" for o in opps)

    def test_queue_opportunity(self) -> None:
        report = build_opportunity_report(app="simple_task", opportunities=scan_appspec(_appspec()))
        kinds = {o["kind"] for o in report["opportunities"]}
        assert "person_ref" in kinds
        assert "work_queue" in kinds
        # overdue_tasks region (not parent workspace name) drives the queue flag
        locs = {o["location"] for o in report["opportunities"] if o["kind"] == "work_queue"}
        assert any("overdue_tasks" in loc for loc in locs)
        # Queue author_action can auto_seed when medium product missing
        assert report["count"] >= 2

    def test_workspace_name_not_false_queue(self) -> None:
        """my_work/* regions must not all flag as queues via workspace name."""
        appspec = _appspec()
        appspec.workspaces = [
            SimpleNamespace(
                name="my_work",
                regions=[
                    SimpleNamespace(
                        name="my_discussion",
                        title="Comments",
                        source="TaskComment",
                        display=SimpleNamespace(value="list"),
                    ),
                ],
            )
        ]
        opps = scan_appspec(appspec)
        assert not any(o.kind == "work_queue" for o in opps)

    def test_scenario_catalogue_loads(self) -> None:
        load_scenarios.cache_clear()
        rows = load_scenarios()
        assert len(rows) >= 5
        ids = {s.id for s in rows}
        assert "person_ref_cell" in ids
        assert "boolean_settings_switch" in ids
        switch = next(s for s in rows if s.id == "boolean_settings_switch")
        assert switch.authoring == "widget=switch"
        assert switch.scanner == "boolean_switch"
        snap = catalogue_snapshot()
        assert snap["count"] == len(rows)

    def test_switch_scenario_author_action_without_widget(self) -> None:
        opps = scan_appspec(_appspec_with_bool_settings(with_switch=False))
        switch_rows = [o for o in opps if o.hyperpart == "switch"]
        assert switch_rows
        assert all(o.status == "author_action" for o in switch_rows)
        report = build_opportunity_report(app="ops_dashboard", opportunities=opps)
        assert report["schema_version"] >= 3
        assert report["residual"]["author_action"] >= 1
        assert report["residual"]["force_lane"] == "example-apps"
        assert "scenario_catalogue" in report

    def test_switch_scenario_emit_covered_with_widget(self) -> None:
        opps = scan_appspec(_appspec_with_bool_settings(with_switch=True))
        switch_rows = [o for o in opps if o.hyperpart == "switch"]
        assert switch_rows
        assert all(o.status == "emit_covered" for o in switch_rows)
        report = build_opportunity_report(app="simple_task", opportunities=opps)
        assert report["residual"]["author_action"] == 0
        assert report["residual"]["force_lane"] is None

    def test_switch_skips_platform_headless_notification_sent(self) -> None:
        """FeedbackReport.notification_sent must not thrash agent_qa_smoke residual.

        Headless platform create falls back to the entity field map; the
        bookkeeping flag matches ``notification`` settings-ish but is toast
        idempotency (#721), not a product preferences control.
        """
        entity = SimpleNamespace(
            name="FeedbackReport",
            domain="platform",
            fields=[
                _field("description", "str"),
                _field("notification_sent", "bool"),
                _field("is_active", "bool"),
            ],
        )
        surface = SimpleNamespace(
            name="feedback_create",
            entity_ref="FeedbackReport",
            mode=SimpleNamespace(value="create"),
            sections=[],
            headless=True,
        )
        appspec = SimpleNamespace(
            domain=SimpleNamespace(entities=[entity]),
            surfaces=[surface],
            workspaces=[],
        )
        opps = scan_appspec(appspec)
        switch_rows = [o for o in opps if o.hyperpart == "switch"]
        assert not any(o.field == "notification_sent" for o in switch_rows)
        assert not any(o.status == "author_action" for o in switch_rows)
        report = build_opportunity_report(app="simple_task", opportunities=opps)
        assert report["residual"]["author_action"] == 0
        assert not report.get("auto_seed")


def test_shapes_scenario_coverage_pick_matrix() -> None:
    """Every live pick-matrix shape has a scenario (agent discovery residual)."""
    from dazzle.qa.hyperpart_dsl_shapes import load_shapes, shapes_snapshot
    from dazzle.qa.hyperpart_scenarios import load_scenarios

    load_shapes.cache_clear()
    load_scenarios.cache_clear()
    snap = shapes_snapshot()
    assert snap.get("schema_version", 0) >= 2
    assert snap.get("scenario_missing", 0) == 0, snap.get("scenario_missing_ids")
    assert snap.get("planned", 0) == 0
    assert snap.get("live", 0) >= 80
