"""Tests for experience flow route handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
from dazzle_ui.runtime.experience_routes import create_experience_routes
from dazzle_ui.runtime.experience_state import (
    ExperienceState,
    cookie_name,
    sign_state,
    verify_state,
)


def _make_entity(name: str = "Client") -> EntitySpec:
    return EntitySpec(
        name=name,
        fields=[
            FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
            FieldSpec(name="name", type=FieldType(kind="str"), is_required=True),
            FieldSpec(name="email", type=FieldType(kind="email")),
        ],
    )


def _make_appspec() -> AppSpec:
    entity = _make_entity()
    surfaces = [
        SurfaceSpec(name="client_form", entity_ref="Client", mode=SurfaceMode.CREATE),
        SurfaceSpec(name="client_view", entity_ref="Client", mode=SurfaceMode.VIEW),
    ]
    experience = ExperienceSpec(
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
                transitions=[],  # terminal
            ),
        ],
    )
    return AppSpec(
        name="test_app",
        title="Test App",
        domain=DomainSpec(entities=[entity]),
        surfaces=surfaces,
        experiences=[experience],
    )


@pytest.fixture()
def app() -> FastAPI:
    appspec = _make_appspec()
    app = FastAPI()
    router = create_experience_routes(appspec, app_prefix="/app")
    app.include_router(router, prefix="/app")
    return app


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app, follow_redirects=False)


class TestEntryRedirect:
    def test_redirect_to_start_step(self, client: TestClient) -> None:
        resp = client.get("/app/experiences/onboarding")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/experiences/onboarding/enter_details"

    def test_redirect_resumes_from_cookie(self, client: TestClient) -> None:
        state = ExperienceState(step="review", completed=["enter_details"])
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        resp = client.get("/app/experiences/onboarding")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/experiences/onboarding/review"

    def test_unknown_experience_redirects_home(self, client: TestClient) -> None:
        resp = client.get("/app/experiences/nonexistent")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/"


class TestStepRendering:
    def test_renders_first_step(self, client: TestClient) -> None:
        resp = client.get("/app/experiences/onboarding/enter_details")
        assert resp.status_code == 200
        assert "Client Onboarding" in resp.text

    def test_renders_with_progress_indicator(self, client: TestClient) -> None:
        resp = client.get("/app/experiences/onboarding/enter_details")
        assert resp.status_code == 200
        # Should contain the DaisyUI steps component
        assert "step" in resp.text

    def test_unknown_step_redirects(self, client: TestClient) -> None:
        resp = client.get("/app/experiences/onboarding/nonexistent")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/experiences/onboarding"

    def test_sets_cookie_on_render(self, client: TestClient) -> None:
        resp = client.get("/app/experiences/onboarding/enter_details")
        assert resp.status_code == 200
        cname = cookie_name("onboarding")
        assert cname in resp.cookies

    def test_navigation_buttons_use_post(self, client: TestClient) -> None:
        """Non-success transition buttons must use hx-post, not GET links (#307)."""
        resp = client.get("/app/experiences/onboarding/enter_details")
        assert resp.status_code == 200
        # The "cancel" transition should render as hx-post button, not <a href>
        assert 'hx-post="/app/experiences/onboarding/enter_details?event=cancel"' in resp.text
        # Should NOT have a plain <a href> for transition events
        assert '<a href="/app/experiences/onboarding/enter_details?event=cancel"' not in resp.text

    def test_detail_step_transitions_use_post_forms(self, client: TestClient) -> None:
        """Detail/view step transitions use <form method=post>."""
        state = ExperienceState(step="review", completed=["enter_details"])
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        resp = client.get("/app/experiences/onboarding/review")
        assert resp.status_code == 200
        # Should use <form method="post"> for transitions
        assert 'method="post"' in resp.text


class TestSkipPrevention:
    def test_cannot_skip_ahead(self, client: TestClient) -> None:
        # No state — try to access step 2 directly
        resp = client.get("/app/experiences/onboarding/review")
        assert resp.status_code == 302
        # Should redirect to current step (enter_details, since no state)
        assert "enter_details" in resp.headers["location"]

    def test_can_access_completed_step(self, client: TestClient) -> None:
        state = ExperienceState(step="review", completed=["enter_details"])
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        resp = client.get("/app/experiences/onboarding/enter_details")
        assert resp.status_code == 200


class TestBackNavigation:
    def test_revisiting_completed_step_rewinds(self, client: TestClient) -> None:
        state = ExperienceState(step="done", completed=["enter_details", "review"])
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        resp = client.get("/app/experiences/onboarding/enter_details")
        assert resp.status_code == 200

        # Parse the set cookie to verify state was rewound
        raw_cookie = resp.cookies.get(cname)
        assert raw_cookie is not None
        new_state = verify_state(raw_cookie)
        assert new_state is not None
        assert new_state.step == "enter_details"
        assert "review" not in new_state.completed
        assert "done" not in new_state.completed


class TestTransition:
    @patch("dazzle_ui.runtime.experience_routes._proxy_to_backend", new_callable=AsyncMock)
    def test_successful_transition(self, mock_proxy: AsyncMock, client: TestClient) -> None:
        mock_proxy.return_value = (True, {"id": "new-id-123"})

        state = ExperienceState(step="enter_details")
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        resp = client.post(
            "/app/experiences/onboarding/enter_details?event=success",
            json={"name": "Test Client", "email": "test@example.com"},
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/experiences/onboarding/review"

        # Verify state advanced
        raw_cookie = resp.cookies.get(cname)
        assert raw_cookie is not None
        new_state = verify_state(raw_cookie)
        assert new_state is not None
        assert new_state.step == "review"
        assert "enter_details" in new_state.completed

    def test_non_form_transition(self, client: TestClient) -> None:
        state = ExperienceState(step="review", completed=["enter_details"])
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        resp = client.post("/app/experiences/onboarding/review?event=approve")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/experiences/onboarding/done"

    def test_back_transition(self, client: TestClient) -> None:
        state = ExperienceState(step="review", completed=["enter_details"])
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        resp = client.post("/app/experiences/onboarding/review?event=back")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/experiences/onboarding/enter_details"


class TestTerminalStep:
    def test_terminal_step_clears_cookie(self, client: TestClient) -> None:
        state = ExperienceState(step="done", completed=["enter_details", "review"])
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        resp = client.post("/app/experiences/onboarding/done?event=success")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/"

        # Cookie should be cleared (max-age=0 or deleted)
        set_cookie = resp.headers.get("set-cookie", "")
        # FastAPI/Starlette deletes by setting max-age=0
        assert cname in set_cookie


class TestBranching:
    def test_different_events_different_targets(self, client: TestClient) -> None:
        state = ExperienceState(step="review", completed=["enter_details"])
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        # approve -> done
        resp1 = client.post("/app/experiences/onboarding/review?event=approve")
        assert resp1.status_code == 302
        assert resp1.headers["location"] == "/app/experiences/onboarding/done"

        # Reset state and try back -> enter_details
        client.cookies.set(cname, sign_state(state))
        resp2 = client.post("/app/experiences/onboarding/review?event=back")
        assert resp2.status_code == 302
        assert resp2.headers["location"] == "/app/experiences/onboarding/enter_details"


class TestFormProxy:
    @patch("dazzle_ui.runtime.experience_routes._proxy_to_backend", new_callable=AsyncMock)
    def test_proxy_success_stores_entity_id(
        self, mock_proxy: AsyncMock, client: TestClient
    ) -> None:
        mock_proxy.return_value = (True, {"id": "created-456"})

        state = ExperienceState(step="enter_details")
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        resp = client.post(
            "/app/experiences/onboarding/enter_details?event=success",
            json={"name": "Test"},
        )
        assert resp.status_code == 302

        raw_cookie = resp.cookies.get(cname)
        new_state = verify_state(raw_cookie)
        assert new_state is not None
        assert new_state.data.get("Client_id") == "created-456"

    @patch("dazzle_ui.runtime.experience_routes._proxy_to_backend", new_callable=AsyncMock)
    def test_proxy_failure_returns_error(self, mock_proxy: AsyncMock, client: TestClient) -> None:
        mock_proxy.return_value = (
            False,
            {"detail": [{"loc": ["body", "name"], "msg": "required"}]},
        )

        state = ExperienceState(step="enter_details")
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        # Non-HTMX request — should redirect back
        resp = client.post(
            "/app/experiences/onboarding/enter_details?event=success",
            json={"email": "test@example.com"},
        )
        assert resp.status_code == 302
        assert "enter_details" in resp.headers["location"]
