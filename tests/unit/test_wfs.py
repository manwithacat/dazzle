"""Tests for Workflow Friction Score (WFS) computation (#375)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from dazzle.mcp.server.handlers.pulse import compute_wfs


def _ns(**kwargs: Any) -> SimpleNamespace:
    """Shortcut for SimpleNamespace."""
    return SimpleNamespace(**kwargs)


def _make_appspec(
    *,
    personas: list[Any] | None = None,
    workspaces: list[Any] | None = None,
    surfaces: list[Any] | None = None,
    stories: list[Any] | None = None,
) -> SimpleNamespace:
    return _ns(
        personas=personas or [],
        workspaces=workspaces or [],
        surfaces=surfaces or [],
        stories=stories or [],
    )


def _make_persona(
    pid: str,
    *,
    label: str = "",
    default_workspace: str = "",
) -> SimpleNamespace:
    return _ns(id=pid, label=label or pid, default_workspace=default_workspace)


def _make_workspace(
    name: str,
    regions: list[Any] | None = None,
) -> SimpleNamespace:
    return _ns(name=name, regions=regions or [])


def _make_region(
    name: str,
    *,
    source: str = "",
    sources: list[str] | None = None,
    action: str = "",
    filter: Any = None,
    sort: list[Any] | None = None,
    group_by: str = "",
) -> SimpleNamespace:
    return _ns(
        name=name,
        source=source,
        sources=sources or [],
        action=action,
        filter=filter,
        sort=sort or [],
        group_by=group_by,
    )


def _make_surface(name: str, *, entity_ref: str = "") -> SimpleNamespace:
    return _ns(name=name, entity_ref=entity_ref)


def _make_story(
    story_id: str,
    *,
    title: str = "",
    actor: str = "",
    scope: list[str] | None = None,
) -> SimpleNamespace:
    return _ns(
        story_id=story_id,
        title=title or story_id,
        actor=actor,
        scope=scope or [],
    )


class TestWfsBasic:
    """Basic WFS computation tests."""

    def test_empty_appspec(self) -> None:
        result = compute_wfs(_make_appspec())
        assert result["overall_avg"] == 0.0
        assert result["personas"] == []

    def test_persona_with_no_stories(self) -> None:
        appspec = _make_appspec(
            personas=[_make_persona("admin", default_workspace="admin_dash")],
            workspaces=[_make_workspace("admin_dash")],
        )
        result = compute_wfs(appspec)
        assert len(result["personas"]) == 1
        assert result["personas"][0]["avg_wfs"] == 0.0
        assert result["personas"][0]["stories"] == []

    def test_persona_with_no_workspace(self) -> None:
        """Persona without a workspace gets maximum friction."""
        appspec = _make_appspec(
            personas=[_make_persona("admin")],
            stories=[_make_story("s1", actor="admin", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        p = result["personas"][0]
        assert p["avg_wfs"] > 0
        assert p["stories"][0]["note"] == "No workspace assigned to persona"
        assert p["stories"][0]["rating"] == "needs_work"


class TestWfsVisibility:
    """Tests for the Visibility (V) factor."""

    def test_entity_on_dashboard(self) -> None:
        """Entity directly on workspace dashboard → V=0."""
        appspec = _make_appspec(
            personas=[_make_persona("staff", default_workspace="staff_dash")],
            workspaces=[
                _make_workspace(
                    "staff_dash",
                    regions=[
                        _make_region("tasks", source="Task", action="task_detail"),
                    ],
                ),
            ],
            surfaces=[_make_surface("task_detail", entity_ref="Task")],
            stories=[_make_story("s1", actor="staff", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        factors = result["personas"][0]["stories"][0]["factors"]
        assert factors["V"] == 0

    def test_entity_not_on_dashboard(self) -> None:
        """Entity NOT on any workspace region → V=2."""
        appspec = _make_appspec(
            personas=[_make_persona("staff", default_workspace="staff_dash")],
            workspaces=[
                _make_workspace(
                    "staff_dash",
                    regions=[
                        _make_region("orders", source="Order"),
                    ],
                ),
            ],
            surfaces=[],
            stories=[_make_story("s1", actor="staff", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        factors = result["personas"][0]["stories"][0]["factors"]
        assert factors["V"] == 2


class TestWfsDiscovery:
    """Tests for the Discovery (D) factor."""

    def test_region_with_action(self) -> None:
        """Region has action link → D=0."""
        appspec = _make_appspec(
            personas=[_make_persona("staff", default_workspace="staff_dash")],
            workspaces=[
                _make_workspace(
                    "staff_dash",
                    regions=[
                        _make_region("tasks", source="Task", action="task_detail"),
                    ],
                ),
            ],
            surfaces=[_make_surface("task_detail", entity_ref="Task")],
            stories=[_make_story("s1", actor="staff", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        factors = result["personas"][0]["stories"][0]["factors"]
        assert factors["D"] == 0

    def test_region_without_action(self) -> None:
        """Region exists but no action link → D=1."""
        appspec = _make_appspec(
            personas=[_make_persona("staff", default_workspace="staff_dash")],
            workspaces=[
                _make_workspace(
                    "staff_dash",
                    regions=[
                        _make_region("tasks", source="Task"),
                    ],
                ),
            ],
            surfaces=[],
            stories=[_make_story("s1", actor="staff", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        factors = result["personas"][0]["stories"][0]["factors"]
        assert factors["D"] == 1


class TestWfsAmbiguity:
    """Tests for the Ambiguity (A) factor."""

    def test_filtered_region(self) -> None:
        """Region with filter → A=0."""
        appspec = _make_appspec(
            personas=[_make_persona("staff", default_workspace="staff_dash")],
            workspaces=[
                _make_workspace(
                    "staff_dash",
                    regions=[
                        _make_region(
                            "tasks",
                            source="Task",
                            action="task_detail",
                            filter=_ns(field="status", op="eq", value="pending"),
                        ),
                    ],
                ),
            ],
            surfaces=[_make_surface("task_detail", entity_ref="Task")],
            stories=[_make_story("s1", actor="staff", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        factors = result["personas"][0]["stories"][0]["factors"]
        assert factors["A"] == 0

    def test_sorted_region(self) -> None:
        """Region with sort → A=0."""
        appspec = _make_appspec(
            personas=[_make_persona("staff", default_workspace="staff_dash")],
            workspaces=[
                _make_workspace(
                    "staff_dash",
                    regions=[
                        _make_region(
                            "tasks",
                            source="Task",
                            action="task_detail",
                            sort=[_ns(field="due_date", direction="asc")],
                        ),
                    ],
                ),
            ],
            surfaces=[_make_surface("task_detail", entity_ref="Task")],
            stories=[_make_story("s1", actor="staff", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        factors = result["personas"][0]["stories"][0]["factors"]
        assert factors["A"] == 0

    def test_unfiltered_region(self) -> None:
        """Region without filter or sort → A=1."""
        appspec = _make_appspec(
            personas=[_make_persona("staff", default_workspace="staff_dash")],
            workspaces=[
                _make_workspace(
                    "staff_dash",
                    regions=[
                        _make_region("tasks", source="Task", action="task_detail"),
                    ],
                ),
            ],
            surfaces=[_make_surface("task_detail", entity_ref="Task")],
            stories=[_make_story("s1", actor="staff", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        factors = result["personas"][0]["stories"][0]["factors"]
        assert factors["A"] == 1


class TestWfsClicks:
    """Tests for the Clicks (C) factor."""

    def test_action_link_one_click(self) -> None:
        """Region with action → C=1."""
        appspec = _make_appspec(
            personas=[_make_persona("staff", default_workspace="staff_dash")],
            workspaces=[
                _make_workspace(
                    "staff_dash",
                    regions=[
                        _make_region("tasks", source="Task", action="task_detail"),
                    ],
                ),
            ],
            surfaces=[_make_surface("task_detail", entity_ref="Task")],
            stories=[_make_story("s1", actor="staff", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        factors = result["personas"][0]["stories"][0]["factors"]
        assert factors["C"] == 1

    def test_no_action_two_clicks(self) -> None:
        """Region without action → C=2."""
        appspec = _make_appspec(
            personas=[_make_persona("staff", default_workspace="staff_dash")],
            workspaces=[
                _make_workspace(
                    "staff_dash",
                    regions=[
                        _make_region("tasks", source="Task"),
                    ],
                ),
            ],
            surfaces=[],
            stories=[_make_story("s1", actor="staff", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        factors = result["personas"][0]["stories"][0]["factors"]
        assert factors["C"] == 2


class TestWfsFormula:
    """Tests for the complete WFS formula."""

    def test_excellent_score(self) -> None:
        """Best case: entity on dashboard, action link, filtered → WFS ≤ 2."""
        appspec = _make_appspec(
            personas=[_make_persona("staff", default_workspace="staff_dash")],
            workspaces=[
                _make_workspace(
                    "staff_dash",
                    regions=[
                        _make_region(
                            "tasks",
                            source="Task",
                            action="task_detail",
                            filter=_ns(field="status", op="eq", value="pending"),
                        ),
                    ],
                ),
            ],
            surfaces=[_make_surface("task_detail", entity_ref="Task")],
            stories=[_make_story("s1", actor="staff", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        wfs = result["personas"][0]["stories"][0]["wfs"]
        # C=1, V=0, D=0, A=0 → WFS = 1 + 0 + 0 + 0 = 1.0
        assert wfs == 1.0
        assert result["personas"][0]["stories"][0]["rating"] == "excellent"

    def test_needs_work_score(self) -> None:
        """Worst case: no workspace → high friction."""
        appspec = _make_appspec(
            personas=[_make_persona("admin")],
            stories=[_make_story("s1", actor="admin", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        wfs = result["personas"][0]["stories"][0]["wfs"]
        # C=2, V=2, D=2, A=1 → WFS = 2 + 1 + 3 + 0.75 = 6.75
        assert wfs == 6.75
        assert result["personas"][0]["stories"][0]["rating"] == "needs_work"


class TestWfsMultiSource:
    """Tests for multi-source regions."""

    def test_multi_source_region(self) -> None:
        """Multi-source region reduces friction same as single source."""
        appspec = _make_appspec(
            personas=[_make_persona("manager", default_workspace="mgr_dash")],
            workspaces=[
                _make_workspace(
                    "mgr_dash",
                    regions=[
                        _make_region(
                            "inbox",
                            sources=["Task", "Request"],
                        ),
                    ],
                ),
            ],
            surfaces=[],
            stories=[_make_story("s1", actor="manager", scope=["Task"])],
        )
        result = compute_wfs(appspec)
        factors = result["personas"][0]["stories"][0]["factors"]
        assert factors["V"] == 0
        assert factors["D"] == 0  # multi-source counts as discoverable


class TestWfsPersonaFilter:
    """Tests for the persona filter."""

    def test_filter_by_persona(self) -> None:
        appspec = _make_appspec(
            personas=[
                _make_persona("admin", default_workspace="admin_dash"),
                _make_persona("staff", default_workspace="staff_dash"),
            ],
            workspaces=[
                _make_workspace("admin_dash"),
                _make_workspace("staff_dash"),
            ],
            stories=[
                _make_story("s1", actor="admin", scope=["Task"]),
                _make_story("s2", actor="staff", scope=["Task"]),
            ],
        )
        result = compute_wfs(appspec, persona_filter="admin")
        assert len(result["personas"]) == 1
        assert result["personas"][0]["persona"] == "admin"


class TestWfsRating:
    """Tests for the rating classification."""

    def test_excellent(self) -> None:
        from dazzle.mcp.server.handlers.pulse import _wfs_rating

        assert _wfs_rating(0.0) == "excellent"
        assert _wfs_rating(1.0) == "excellent"
        assert _wfs_rating(2.0) == "excellent"

    def test_acceptable(self) -> None:
        from dazzle.mcp.server.handlers.pulse import _wfs_rating

        assert _wfs_rating(2.5) == "acceptable"
        assert _wfs_rating(4.0) == "acceptable"

    def test_needs_work(self) -> None:
        from dazzle.mcp.server.handlers.pulse import _wfs_rating

        assert _wfs_rating(5.0) == "needs_work"
        assert _wfs_rating(6.75) == "needs_work"
