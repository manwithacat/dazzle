"""Unit tests for the guide-walk oracle (scope A: first-step overlay render).

Follows the stub pattern of ``test_interaction_walks.py`` — no real server, no
Playwright. A ``_StubHttp`` returns canned page HTML keyed by path.
"""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.testing.ux.interactions.guide_walk import (
    GuideWalkInteraction,
    _surface_url,
)


def _surface(name: str, entity: str, mode: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, entity_ref=entity, mode=mode)


def _guide(name: str, step_order: list[str], targets: dict[str, str]) -> SimpleNamespace:
    steps = [SimpleNamespace(name=s, target=targets[s], cta_target=None) for s in step_order]
    return SimpleNamespace(name=name, step_order=step_order, steps=steps)


class _StubHttp:
    def __init__(self, pages: dict[str, tuple[int, str]]) -> None:
        self._pages = pages
        self.posted: list[str] = []

    def get(self, path: str) -> SimpleNamespace:
        status, html = self._pages.get(path, (404, ""))
        return SimpleNamespace(status_code=status, text=html)

    def post(self, path: str) -> SimpleNamespace:
        self.posted.append(path)
        return SimpleNamespace(status_code=200, text="")


_OVERLAY = '<dz-onboarding-step class="dz-onboarding-empty-state" data-guide="{g}" data-step="{s}" data-kind="empty_state">'


def test_surface_url_list_and_create_and_detail() -> None:
    assert _surface_url(_surface("task_list", "Task", "list")) == ("/app/task", "list")
    assert _surface_url(_surface("task_create", "Task", "create")) == ("/app/task/create", "create")
    url, mode = _surface_url(_surface("task_detail", "Task", "view"))
    assert url is None and mode == "view"


def test_guide_walk_passes_when_first_step_overlay_renders() -> None:
    guide = _guide(
        "member_onboarding",
        ["your_board", "next"],
        {"your_board": "surface.task_list", "next": "surface.task_detail"},
    )
    surfaces = [_surface("task_list", "Task", "list")]
    http = _StubHttp({"/app/task": (200, _OVERLAY.format(g="member_onboarding", s="your_board"))})
    result = GuideWalkInteraction(
        guide=guide, persona="member", surfaces=surfaces, http=http
    ).execute()
    assert result.passed, result.reason
    assert "rendered" in result.reason


def test_guide_walk_fails_when_overlay_missing() -> None:
    guide = _guide("member_onboarding", ["your_board"], {"your_board": "surface.task_list"})
    surfaces = [_surface("task_list", "Task", "list")]
    http = _StubHttp({"/app/task": (200, "<div>no overlay</div>")})
    result = GuideWalkInteraction(
        guide=guide, persona="member", surfaces=surfaces, http=http
    ).execute()
    assert not result.passed
    assert "did NOT render" in result.reason


def test_guide_walk_fails_on_non_200() -> None:
    guide = _guide("member_onboarding", ["your_board"], {"your_board": "surface.task_list"})
    surfaces = [_surface("task_list", "Task", "list")]
    http = _StubHttp({"/app/task": (403, "")})
    result = GuideWalkInteraction(
        guide=guide, persona="member", surfaces=surfaces, http=http
    ).execute()
    assert not result.passed
    assert "403" in result.reason


def test_guide_walk_skips_detail_first_step_without_failing() -> None:
    # hr_records/employee_onboarding shape: first step targets a view surface.
    guide = _guide("employee_onboarding", ["your_record"], {"your_record": "surface.person_detail"})
    surfaces = [_surface("person_detail", "Person", "view")]
    http = _StubHttp({})
    result = GuideWalkInteraction(
        guide=guide, persona="employee", surfaces=surfaces, http=http
    ).execute()
    assert result.passed  # skip is not a failure
    assert result.evidence.get("skipped") is True
    assert "deferred" in result.reason


# --- assembly: _audience_personas + _build_guide_walk --------------------


def test_audience_personas_extracts_all_clauses() -> None:
    from dazzle.cli.ux_interactions import _audience_personas

    assert _audience_personas("persona = agent or persona = manager") == ["agent", "manager"]
    assert _audience_personas("persona = customer") == ["customer"]
    assert _audience_personas("entity.Task.count = 0") == []
    assert _audience_personas(None) == []


def test_build_guide_walk_one_per_guide_authed_as_audience() -> None:
    from dazzle.cli.ux_interactions import _build_guide_walk

    appspec = SimpleNamespace(
        surfaces=[_surface("task_list", "Task", "list")],
        guides=[
            SimpleNamespace(
                name="customer_onboarding",
                audience="persona = customer",
                step_order=["a"],
                steps=[SimpleNamespace(name="a", target="surface.task_list", cta_target=None)],
            ),
            SimpleNamespace(
                name="agent_onboarding",
                audience="persona = agent or persona = manager",
                step_order=["a"],
                steps=[SimpleNamespace(name="a", target="surface.task_list", cta_target=None)],
            ),
        ],
    )
    seen: list[str] = []

    def client_for(p: str) -> object:
        seen.append(p)
        return _StubHttp({})

    # No persona filter: every guide walked as its first audience persona.
    walks = _build_guide_walk(appspec, persona="", client_for=client_for)
    assert [w.persona for w in walks] == ["customer", "agent"]
    assert seen == ["customer", "agent"]

    # Persona filter: only guides whose audience admits 'manager'.
    walks2 = _build_guide_walk(appspec, persona="manager", client_for=client_for)
    assert [w.guide.name for w in walks2] == ["agent_onboarding"]
    assert [w.persona for w in walks2] == ["manager"]
