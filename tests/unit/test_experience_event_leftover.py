"""Experience leftover event must not invent terminal completion (cycle 2207).

leftover-honest catalog id already exists (oral #69). Experience
POST still treated leftover ``?event=zzz`` as "no matching
transition" and invented terminal completion (clear cookie,
redirect home) on a step that still has transitions. Valid
declared events ride; leftover stays put. Missing event still
defaults to ``success``. True terminal (no transitions) still
completes. Live ops_dashboard ``incident_response`` ``on success``.
Oral #87 — not leftover catalog sibling (oral #69), not leftover
GET list typed VALUE (oral #85), not leftover bulk filter (oral #86).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.ir import AppSpec, DomainSpec, EntitySpec, FieldSpec, FieldType, SurfaceSpec
from dazzle.core.ir.experiences import (
    ExperienceSpec,
    ExperienceStep,
    StepKind,
    StepTransition,
)
from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.experience_routes import (
    create_experience_routes,
    leftover_honest_experience_event,
)
from dazzle.page.runtime.experience_state import (
    ExperienceState,
    cookie_name,
    sign_state,
    verify_state,
)

_ROUTES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "experience_routes.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "ops_dashboard" / "dsl" / "app.dsl"


def _make_appspec() -> AppSpec:
    entity = EntitySpec(
        name="Client",
        fields=[
            FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
            FieldSpec(name="name", type=FieldType(kind="str"), is_required=True),
        ],
    )
    return AppSpec(
        name="test_app",
        title="Test App",
        domain=DomainSpec(entities=[entity]),
        surfaces=[
            SurfaceSpec(name="client_form", entity_ref="Client", mode=SurfaceMode.CREATE),
            SurfaceSpec(name="client_view", entity_ref="Client", mode=SurfaceMode.VIEW),
        ],
        experiences=[
            ExperienceSpec(
                name="onboarding",
                title="Client Onboarding",
                start_step="enter_details",
                steps=[
                    ExperienceStep(
                        name="enter_details",
                        kind=StepKind.SURFACE,
                        surface="client_form",
                        transitions=[
                            StepTransition(event="success", next_step="review"),
                            StepTransition(event="cancel", next_step="enter_details"),
                        ],
                    ),
                    ExperienceStep(
                        name="review",
                        kind=StepKind.SURFACE,
                        surface="client_view",
                        transitions=[
                            StepTransition(event="approve", next_step="done"),
                            StepTransition(event="back", next_step="enter_details"),
                        ],
                    ),
                    ExperienceStep(
                        name="done",
                        kind=StepKind.SURFACE,
                        surface="client_view",
                        transitions=[],
                    ),
                ],
            )
        ],
    )


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(create_experience_routes(_make_appspec(), app_prefix="/app"), prefix="/app")
    app.state.entity_create_invokers = {}
    return TestClient(app, follow_redirects=False)


@pytest.mark.parametrize(
    ("raw", "declared", "expected"),
    [
        ("zzz", ("success", "cancel"), ""),
        ("ghost", ("success", "cancel"), ""),
        ("2abc", ("success",), ""),
        ("SUCCESS", ("success",), ""),
        ("success", ("success", "cancel"), "success"),
        ("cancel", ("success", "cancel"), "cancel"),
        ("approve", ("approve", "back"), "approve"),
        ("", ("success",), ""),
        (None, ("success",), ""),
    ],
    ids=[
        "leftover-zzz",
        "leftover-ghost",
        "leftover-suffix",
        "leftover-case",
        "valid-success",
        "valid-cancel",
        "valid-approve",
        "empty",
        "none",
    ],
)
def test_leftover_honest_experience_event_does_not_invent(
    raw: object, declared: tuple[str, ...], expected: str
) -> None:
    assert leftover_honest_experience_event(raw, declared) == expected


def test_leftover_event_stays_put(client: TestClient) -> None:
    """Leftover event must not invent terminal home / cookie clear."""
    state = ExperienceState(step="enter_details")
    cname = cookie_name("onboarding")
    client.cookies.set(cname, sign_state(state))

    resp = client.post("/app/experiences/onboarding/enter_details?event=zzz")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/app/experiences/onboarding/enter_details"
    set_cookie = resp.headers.get("set-cookie", "")
    assert "max-age=0" not in set_cookie.lower()
    raw_cookie = resp.cookies.get(cname)
    if raw_cookie:
        kept = verify_state(raw_cookie)
        assert kept is not None
        assert kept.step == "enter_details"
        assert "enter_details" not in kept.completed


def test_leftover_event_on_review_stays_put(client: TestClient) -> None:
    state = ExperienceState(step="review", completed=["enter_details"])
    cname = cookie_name("onboarding")
    client.cookies.set(cname, sign_state(state))

    resp = client.post("/app/experiences/onboarding/review?event=ghost")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/app/experiences/onboarding/review"


def test_valid_event_still_advances(client: TestClient) -> None:
    state = ExperienceState(step="review", completed=["enter_details"])
    cname = cookie_name("onboarding")
    client.cookies.set(cname, sign_state(state))

    resp = client.post("/app/experiences/onboarding/review?event=approve")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/app/experiences/onboarding/done"


def test_true_terminal_still_completes(client: TestClient) -> None:
    state = ExperienceState(step="done", completed=["enter_details", "review"])
    cname = cookie_name("onboarding")
    client.cookies.set(cname, sign_state(state))

    resp = client.post("/app/experiences/onboarding/done?event=zzz")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/app/"


def test_helper_source_pins_experience_event_leftover() -> None:
    src = _ROUTES.read_text()
    assert "def leftover_honest_experience_event" in src
    assert "def _experience_stay_response" in src
    assert "leftover_honest_catalog_id" in src


def test_post_source_pins_experience_event_leftover() -> None:
    src = _ROUTES.read_text()
    assert "leftover_honest_experience_event" in src
    assert "_experience_stay_response" in src
    assert "declared_events" in src


def test_live_ops_dashboard_incident_response_declares_success() -> None:
    src = _LIVE.read_text()
    assert "experience incident_response" in src
    assert "on success -> step investigate" in src
    assert "on success -> step acknowledge" in src
