"""Onboarding leftover guide/step must not invent completed state (cycle 2208).

leftover-honest catalog id already exists (oral #69). Onboarding
POST still persisted leftover ``/api/onboarding/zzz/ghost/complete``
as a completed/dismissed row. Valid declared guide+step ride;
leftover stays put (404, no write). Live simple_task
``workspace_setup`` ``welcome_empty``. Oral #88 — not leftover
experience event (oral #87), not leftover catalog picker (oral #69).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.onboarding.routes import (
    create_onboarding_routes,
    leftover_honest_onboarding_step,
)

_ROUTES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "onboarding"
    / "routes.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dsl" / "onboarding.dsl"


def _guides() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            name="workspace_setup",
            steps=[
                SimpleNamespace(name="welcome_empty"),
                SimpleNamespace(name="fill_title"),
                SimpleNamespace(name="invite_team"),
            ],
            step_order=["welcome_empty", "fill_title", "invite_team"],
        )
    ]


def _app(repo: MagicMock) -> FastAPI:
    app = FastAPI()
    app.state.onboarding_state = repo
    app.state.appspec = SimpleNamespace(guides=_guides())

    @app.middleware("http")
    async def attach_user(request, call_next):  # type: ignore[no-untyped-def]
        request.state.current_user = SimpleNamespace(id="u1")
        return await call_next(request)

    app.include_router(create_onboarding_routes())
    return app


@pytest.mark.parametrize(
    ("guide", "step", "expected"),
    [
        ("zzz", "ghost", ("", "")),
        ("workspace_setup", "zzz", ("", "")),
        ("ghost", "welcome_empty", ("", "")),
        ("WORKSPACE_SETUP", "welcome_empty", ("", "")),
        ("workspace_setup", "welcome_empty", ("workspace_setup", "welcome_empty")),
        ("workspace_setup", "fill_title", ("workspace_setup", "fill_title")),
        ("", "welcome_empty", ("", "")),
        (None, None, ("", "")),
    ],
    ids=[
        "leftover-both",
        "leftover-step",
        "leftover-guide",
        "leftover-case",
        "valid-welcome",
        "valid-fill",
        "empty",
        "none",
    ],
)
def test_leftover_honest_onboarding_step_does_not_invent(
    guide: object, step: object, expected: tuple[str, str]
) -> None:
    assert leftover_honest_onboarding_step(guide, step, _guides()) == expected


def test_leftover_complete_does_not_write() -> None:
    repo = MagicMock()
    client = TestClient(_app(repo))
    resp = client.post("/api/onboarding/zzz/ghost/complete")
    assert resp.status_code == 404
    repo.mark_step_completed.assert_not_called()
    repo.mark_step_dismissed.assert_not_called()


def test_leftover_dismiss_does_not_write() -> None:
    repo = MagicMock()
    client = TestClient(_app(repo))
    resp = client.post("/api/onboarding/workspace_setup/zzz/dismiss")
    assert resp.status_code == 404
    repo.mark_step_dismissed.assert_not_called()


def test_valid_complete_still_writes() -> None:
    repo = MagicMock()
    client = TestClient(_app(repo))
    resp = client.post("/api/onboarding/workspace_setup/welcome_empty/complete")
    assert resp.status_code == 200
    repo.mark_step_completed.assert_called_once()
    call = repo.mark_step_completed.call_args
    assert call.kwargs["guide_name"] == "workspace_setup"
    assert call.kwargs["step_name"] == "welcome_empty"


def test_valid_dismiss_still_writes() -> None:
    repo = MagicMock()
    client = TestClient(_app(repo))
    resp = client.post("/api/onboarding/workspace_setup/invite_team/dismiss")
    assert resp.status_code == 200
    repo.mark_step_dismissed.assert_called_once()


def test_helper_source_pins_onboarding_step_leftover() -> None:
    src = _ROUTES.read_text()
    assert "def leftover_honest_onboarding_step" in src
    assert "def _require_honest_onboarding_step" in src
    assert "leftover_honest_catalog_id" in src


def test_live_simple_task_workspace_setup_declares_welcome_empty() -> None:
    src = _LIVE.read_text()
    assert "guide workspace_setup" in src
    assert "step welcome_empty:" in src
    assert "step fill_title:" in src
