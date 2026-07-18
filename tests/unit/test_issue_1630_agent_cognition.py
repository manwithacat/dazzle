"""#1630 — STABLE User skip, scope persona validate, demo_ops rules."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parents[2]
SIMPLE = REPO / "examples" / "simple_task"


def test_skip_stable_user_fixtures() -> None:
    from dazzle.demo_data.test_mode_load import (
        jsonl_dir_to_fixtures,
    )
    from dazzle.product_quality.persona_homes import STABLE_PERSONA_USER_IDS as SID

    member = SID["member"]
    tmp = SIMPLE / "dsl" / "seeds" / "demo_data"
    if not tmp.is_dir():
        pytest.skip("simple_task seeds missing")
    all_f = jsonl_dir_to_fixtures(tmp, skip_stable_users=False)
    filtered = jsonl_dir_to_fixtures(tmp, skip_stable_users=True)
    # When User.jsonl has STABLE ids they must be dropped
    stable_users_all = [
        f for f in all_f if f["entity"] == "User" and str(f["data"].get("id")) in SID.values()
    ]
    stable_users_filt = [
        f for f in filtered if f["entity"] == "User" and str(f["data"].get("id")) in SID.values()
    ]
    assert stable_users_filt == []
    # Non-user fixtures preserved
    assert len(filtered) == len(all_f) - len(stable_users_all)
    assert member in SID.values()


def test_reset_and_load_skips_stable_users_before_seed() -> None:
    from dazzle.demo_data.test_mode_load import reset_and_load
    from dazzle.product_quality.persona_homes import STABLE_PERSONA_USER_IDS

    class _Resp:
        def __init__(self, code: int, body: dict | str = ""):
            self.status_code = code
            self.text = body if isinstance(body, str) else json.dumps(body)

        def json(self) -> dict:
            return json.loads(self.text) if str(self.text).startswith("{") else {}

    posted: list[tuple] = []

    def _post(url, **kwargs):
        posted.append((url, kwargs.get("json")))
        if url == "/__test__/reset":
            return _Resp(200, {"ok": True})
        if url == "/__test__/seed":
            fixtures = (kwargs.get("json") or {}).get("fixtures") or []
            for f in fixtures:
                if f.get("entity") == "User":
                    rid = (f.get("data") or {}).get("id")
                    assert rid not in STABLE_PERSONA_USER_IDS.values(), f
            return _Resp(200, {"created": {f["id"]: {} for f in fixtures}})
        if url == "/__test__/authenticate":
            return _Resp(200, {"user_id": "x"})
        return _Resp(404, {})

    mock_client = MagicMock()
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.side_effect = _post
    mock_client.get.return_value = _Resp(200, {"total": 3, "items": [1, 2, 3]})

    with patch("dazzle.demo_data.test_mode_load.httpx.Client", return_value=mock_client):
        report = reset_and_load(
            SIMPLE,
            base_url="http://test.local:9",
            test_secret="sekrit",
            verify_persona_homes=True,
        )
    seed_calls = [p for p in posted if p[0] == "/__test__/seed"]
    assert seed_calls, posted
    assert report.get("skipped_stable_user_fixtures", 0) >= 0


def test_validate_scope_personas_undeclared() -> None:
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.core.validation.rbac import validate_scope_personas_declared

    app = load_project_appspec(SIMPLE)
    # Inject a bogus scope persona
    for e in app.domain.entities:
        if e.access and e.access.scopes:
            e.access.scopes[0].personas = list(e.access.scopes[0].personas) + [
                "not_a_real_persona_xyz"
            ]
            break
    else:
        pytest.skip("no scopes in simple_task")
    _errors, warnings = validate_scope_personas_declared(app)
    assert any("not_a_real_persona_xyz" in w and "#1630" in w for w in warnings)


def test_validate_stable_persona_warns_on_free_id() -> None:
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.core.validation.rbac import validate_stable_persona_ids_for_demo

    app = load_project_appspec(SIMPLE)
    # Rename member → promoter (free id) while keeping default_workspace
    new_personas = []
    found = False
    for p in app.personas:
        if p.id == "member":
            new_personas.append(p.model_copy(update={"id": "promoter"}))
            found = True
        else:
            new_personas.append(p)
    if not found:
        pytest.skip("no member persona")
    app = app.model_copy(update={"personas": new_personas})
    _errors, warnings = validate_stable_persona_ids_for_demo(app)
    assert any("promoter" in w and "STABLE" in w for w in warnings)


def test_demo_ops_lists_stable_ids_and_1630_rules() -> None:
    from dazzle.demo_data.test_mode_load import demo_ops_playbook

    pb = demo_ops_playbook()
    assert "requester" in pb["stable_persona_ids"]
    assert any("User.jsonl" in r or "STABLE" in r for r in pb["rules"])
    assert 1630 in pb.get("related_issues", [])
    assert any("runtime.json" in s for s in pb["order"])


def test_init_template_framework_version_placeholder() -> None:
    text = (REPO / "src/dazzle/templates/blank/dazzle.toml").read_text()
    assert "framework_minor" in text or "~0.106" in text
    assert "~0.38" not in text
