"""Tests for experience flow progress persistence."""

from __future__ import annotations

import time
from pathlib import Path
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
from dazzle_ui.runtime.experience_persistence import (
    ExperienceProgress,
    ExperienceProgressStore,
)
from dazzle_ui.runtime.experience_routes import create_experience_routes
from dazzle_ui.runtime.experience_state import (
    ExperienceState,
    cookie_name,
    sign_state,
)

# ---------------------------------------------------------------------------
# ExperienceProgressStore unit tests
# ---------------------------------------------------------------------------


class TestExperienceProgressStore:
    def test_save_and_load(self, tmp_path: Path) -> None:
        store = ExperienceProgressStore(tmp_path)
        progress = ExperienceProgress(
            experience_name="onboarding",
            current_step="step_2",
            completed_steps=["step_1"],
            step_data={"Client_id": "abc-123"},
        )
        store.save(progress)
        loaded = store.load("onboarding")
        assert loaded is not None
        assert loaded.current_step == "step_2"
        assert loaded.completed_steps == ["step_1"]
        assert loaded.step_data["Client_id"] == "abc-123"

    def test_load_nonexistent_returns_none(self, tmp_path: Path) -> None:
        store = ExperienceProgressStore(tmp_path)
        assert store.load("nonexistent") is None

    def test_delete_removes_file(self, tmp_path: Path) -> None:
        store = ExperienceProgressStore(tmp_path)
        progress = ExperienceProgress(
            experience_name="onboarding",
            current_step="step_1",
        )
        store.save(progress)
        assert store.load("onboarding") is not None

        store.delete("onboarding")
        assert store.load("onboarding") is None

    def test_delete_nonexistent_is_noop(self, tmp_path: Path) -> None:
        store = ExperienceProgressStore(tmp_path)
        store.delete("nonexistent")  # should not raise

    def test_expired_progress_returns_none(self, tmp_path: Path) -> None:
        store = ExperienceProgressStore(tmp_path)
        progress = ExperienceProgress(
            experience_name="onboarding",
            current_step="step_1",
            last_activity=time.time() - (8 * 24 * 3600),  # 8 days ago
        )
        # Write directly to bypass save()'s last_activity update
        store._dir.mkdir(parents=True, exist_ok=True)
        path = store._progress_path("onboarding")
        path.write_text(progress.model_dump_json(indent=2))

        assert store.load("onboarding") is None
        # File should be cleaned up
        assert not path.exists()

    def test_corrupt_file_returns_none(self, tmp_path: Path) -> None:
        store = ExperienceProgressStore(tmp_path)
        store._dir.mkdir(parents=True, exist_ok=True)
        path = store._progress_path("onboarding")
        path.write_text("not valid json {{{")

        assert store.load("onboarding") is None
        # File should be cleaned up
        assert not path.exists()

    def test_user_email_keying(self, tmp_path: Path) -> None:
        store = ExperienceProgressStore(tmp_path)
        progress_a = ExperienceProgress(
            experience_name="onboarding",
            current_step="step_2",
            user_email="alice@example.com",
        )
        progress_b = ExperienceProgress(
            experience_name="onboarding",
            current_step="step_3",
            user_email="bob@example.com",
        )
        store.save(progress_a)
        store.save(progress_b)

        loaded_a = store.load("onboarding", "alice@example.com")
        loaded_b = store.load("onboarding", "bob@example.com")
        assert loaded_a is not None
        assert loaded_a.current_step == "step_2"
        assert loaded_b is not None
        assert loaded_b.current_step == "step_3"

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        store = ExperienceProgressStore(tmp_path)
        progress = ExperienceProgress(
            experience_name="onboarding",
            current_step="step_1",
        )
        store.save(progress)
        assert store._dir.exists()

    def test_save_updates_last_activity(self, tmp_path: Path) -> None:
        store = ExperienceProgressStore(tmp_path)
        old_time = time.time() - 3600
        progress = ExperienceProgress(
            experience_name="onboarding",
            current_step="step_1",
            last_activity=old_time,
        )
        store.save(progress)
        loaded = store.load("onboarding")
        assert loaded is not None
        assert loaded.last_activity > old_time


# ---------------------------------------------------------------------------
# Route integration tests: resume from file store
# ---------------------------------------------------------------------------


def _make_appspec() -> AppSpec:
    entity = EntitySpec(
        name="Client",
        fields=[
            FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
            FieldSpec(name="name", type=FieldType(kind="str"), is_required=True),
        ],
    )
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
                transitions=[StepTransition(event="success", next_step="review")],
            ),
            ExperienceStep(
                name="review",
                kind=StepKind.SURFACE,
                surface="client_view",
                transitions=[StepTransition(event="approve", next_step="done")],
            ),
            ExperienceStep(
                name="done",
                kind=StepKind.SURFACE,
                surface="client_view",
                transitions=[],
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


class TestResumeFromFileStore:
    @pytest.fixture()
    def project_root(self, tmp_path: Path) -> Path:
        return tmp_path

    @pytest.fixture()
    def client(self, project_root: Path) -> TestClient:
        appspec = _make_appspec()
        app = FastAPI()
        router = create_experience_routes(appspec, app_prefix="/app", project_root=project_root)
        app.include_router(router, prefix="/app")
        return TestClient(app, follow_redirects=False)

    def test_entry_resumes_from_file_store(self, client: TestClient, project_root: Path) -> None:
        """When cookie is missing but file store has progress, resume from saved step."""
        store = ExperienceProgressStore(project_root)
        store.save(
            ExperienceProgress(
                experience_name="onboarding",
                current_step="review",
                completed_steps=["enter_details"],
                step_data={"Client_id": "abc-123"},
            )
        )

        # No cookie set — should resume from file store
        resp = client.get("/app/experiences/onboarding")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/experiences/onboarding/review"

    def test_entry_sets_cookie_on_resume(self, client: TestClient, project_root: Path) -> None:
        """Resuming from file store should restore the cookie."""
        store = ExperienceProgressStore(project_root)
        store.save(
            ExperienceProgress(
                experience_name="onboarding",
                current_step="review",
                completed_steps=["enter_details"],
            )
        )

        resp = client.get("/app/experiences/onboarding")
        cname = cookie_name("onboarding")
        assert cname in resp.cookies

    def test_step_get_saves_progress(self, client: TestClient, project_root: Path) -> None:
        """Rendering a step should save progress to the file store."""
        resp = client.get("/app/experiences/onboarding/enter_details")
        assert resp.status_code == 200

        store = ExperienceProgressStore(project_root)
        loaded = store.load("onboarding")
        assert loaded is not None
        assert loaded.current_step == "enter_details"

    @patch("dazzle_ui.runtime.experience_routes._proxy_to_backend", new_callable=AsyncMock)
    def test_transition_saves_progress(
        self, mock_proxy: AsyncMock, client: TestClient, project_root: Path
    ) -> None:
        """Successful transition should save updated progress to file store."""
        mock_proxy.return_value = (True, {"id": "new-id"})

        state = ExperienceState(step="enter_details")
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        resp = client.post(
            "/app/experiences/onboarding/enter_details?event=success",
            json={"name": "Test"},
        )
        assert resp.status_code == 302

        store = ExperienceProgressStore(project_root)
        loaded = store.load("onboarding")
        assert loaded is not None
        assert loaded.current_step == "review"
        assert "enter_details" in loaded.completed_steps

    def test_terminal_step_deletes_progress(self, client: TestClient, project_root: Path) -> None:
        """Completing a flow should delete the progress file."""
        store = ExperienceProgressStore(project_root)
        store.save(
            ExperienceProgress(
                experience_name="onboarding",
                current_step="done",
                completed_steps=["enter_details", "review"],
            )
        )

        state = ExperienceState(step="done", completed=["enter_details", "review"])
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        resp = client.post("/app/experiences/onboarding/done?event=success")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/"

        # Progress file should be deleted
        assert store.load("onboarding") is None

    def test_cookie_takes_precedence_over_file(
        self, client: TestClient, project_root: Path
    ) -> None:
        """When both cookie and file exist, cookie state wins."""
        store = ExperienceProgressStore(project_root)
        store.save(
            ExperienceProgress(
                experience_name="onboarding",
                current_step="enter_details",
            )
        )

        # Cookie says we're on "review"
        state = ExperienceState(step="review", completed=["enter_details"])
        cname = cookie_name("onboarding")
        client.cookies.set(cname, sign_state(state))

        resp = client.get("/app/experiences/onboarding")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/experiences/onboarding/review"

    def test_step_get_restores_from_file_store(
        self, client: TestClient, project_root: Path
    ) -> None:
        """Step GET should restore state from file when cookie is missing."""
        store = ExperienceProgressStore(project_root)
        store.save(
            ExperienceProgress(
                experience_name="onboarding",
                current_step="review",
                completed_steps=["enter_details"],
            )
        )

        # No cookie — should restore state and allow access to "review"
        resp = client.get("/app/experiences/onboarding/review")
        assert resp.status_code == 200
