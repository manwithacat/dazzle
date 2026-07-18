"""#1627 — closed-loop demo reset-and-load + tribal playbook."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SIMPLE = REPO / "examples" / "simple_task"


def test_demo_ops_playbook_has_stable_ids_and_order() -> None:
    from dazzle.demo_data.test_mode_load import PERSONA_EMAIL_DOMAIN, demo_ops_playbook

    pb = demo_ops_playbook()
    assert pb["issue"] == 1627
    assert pb["persona_email_domain"] == PERSONA_EMAIL_DOMAIN
    assert "member" in pb["stable_persona_user_ids"]
    assert pb["stable_persona_user_ids"]["member"].startswith("a1000000-")
    assert any("reset-and-load" in step for step in pb["order"])
    assert any("after" in r.lower() or "Never authenticate before" in r for r in pb["rules"])


def test_jsonl_dir_to_fixtures_simple_task() -> None:
    from dazzle.demo_data.test_mode_load import find_demo_data_dir, jsonl_dir_to_fixtures

    data_dir = find_demo_data_dir(SIMPLE)
    assert data_dir is not None
    fixtures = jsonl_dir_to_fixtures(data_dir)
    assert fixtures
    entities = {f["entity"] for f in fixtures}
    assert "Task" in entities or "User" in entities
    for f in fixtures:
        assert "id" in f and "entity" in f and "data" in f
        assert isinstance(f["data"], dict)


def test_reset_and_load_fails_loud_without_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dazzle.demo_data.test_mode_load import reset_and_load

    monkeypatch.delenv("DAZZLE_TEST_SECRET", raising=False)
    monkeypatch.delenv("DAZZLE_API_URL", raising=False)
    (tmp_path / "dazzle.toml").write_text('[project]\nname = "t"\n', encoding="utf-8")
    seeds = tmp_path / "dsl" / "seeds" / "demo_data"
    seeds.mkdir(parents=True)
    (seeds / "Thing.jsonl").write_text(
        json.dumps({"id": "t1", "name": "x"}) + "\n",
        encoding="utf-8",
    )
    report = reset_and_load(tmp_path, verify_persona_homes=False)
    assert report["ok"] is False
    assert "test_secret" in report["error"].lower() or "No test_secret" in report["error"]
    assert "playbook" in report


def test_reset_and_load_http_roundtrip() -> None:
    from unittest.mock import MagicMock, patch

    from dazzle.demo_data.test_mode_load import reset_and_load

    class _Resp:
        def __init__(self, code: int, body: dict | str = ""):
            self.status_code = code
            self.text = body if isinstance(body, str) else json.dumps(body)

        def json(self) -> dict:
            return json.loads(self.text) if self.text.startswith("{") else {}

    mock_client = MagicMock()
    mock_client.__enter__ = lambda s: s
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.side_effect = [
        _Resp(200, {"ok": True}),
        _Resp(200, {"created": {"a": {}}}),
    ]

    with patch("dazzle.demo_data.test_mode_load.httpx.Client", return_value=mock_client):
        report = reset_and_load(
            SIMPLE,
            base_url="http://test.local:9",
            test_secret="sekrit",
            verify_persona_homes=True,
        )
    assert report["fixture_count"] > 0
    assert mock_client.post.call_count >= 2
    assert mock_client.post.call_args_list[0][0][0] == "/__test__/reset"
    assert mock_client.post.call_args_list[1][0][0] == "/__test__/seed"
    # seed HTTP ok; residual score is static over seeds (may be 0)
    assert report.get("steps")


def test_agent_context_includes_demo_ops() -> None:
    from dazzle.agent_loop import build_context

    if not (SIMPLE / "dazzle.toml").is_file():
        pytest.skip("simple_task missing")
    ctx = build_context(SIMPLE)
    assert "demo_ops" in ctx
    assert ctx["demo_ops"].get("issue") == 1627
    assert "stable_persona_user_ids" in ctx["demo_ops"]


def test_demo_world_includes_demo_ops() -> None:
    from dazzle.mcp.server.handlers.status import get_demo_world_handler

    raw = get_demo_world_handler(SIMPLE, {})
    data = json.loads(raw)
    assert data.get("demo_ops", {}).get("issue") == 1627
    assert "reset-and-load" in data.get("seed_hint", "")
