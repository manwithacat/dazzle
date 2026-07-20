"""Scene walk models, loader, discovery, validate (#1638 PR1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.testing.walk.discovery import default_walks_dir, discover_walk_paths
from dazzle.testing.walk.loader import WalkLoadError, load_walk
from dazzle.testing.walk.models import CORE_ACTION_TYPES, WalkActionType
from dazzle.testing.walk.validate import validate_walk, validate_walks

_REPO = Path(__file__).resolve().parents[2]
_SIMPLE = _REPO / "examples" / "simple_task"
_SHOWCASE = _SIMPLE / "fixtures" / "scene_walks" / "land_and_see_tasks.yaml"


class TestDiscover:
    def test_default_dir(self) -> None:
        assert default_walks_dir(_SIMPLE) == _SIMPLE / "fixtures" / "scene_walks"

    def test_discovers_showcase(self) -> None:
        paths = discover_walk_paths(_SIMPLE)
        stems = {p.stem for p in paths}
        assert "land_and_see_tasks" in stems

    def test_missing_dir_empty(self, tmp_path: Path) -> None:
        assert discover_walk_paths(tmp_path) == []


class TestLoadShowcase:
    def test_load_land_and_see(self) -> None:
        walk = load_walk(_SHOWCASE)
        assert walk.walk_id == "land_and_see_tasks"
        assert walk.persona == "member"
        assert walk.home_workspace == "my_work"
        assert walk.story_ids() == ["ST-020"]
        assert walk.core_only() is True
        assert len(walk.scenes) == 1
        assert walk.scenes[0].actions[0].type == WalkActionType.NAVIGATE

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(WalkLoadError, match="file not found"):
            load_walk(tmp_path / "nope.yaml")

    def test_invalid_action_type(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text(
            "persona: member\nscenes:\n  - id: s\n    actions:\n      - type: not_a_verb\n",
            encoding="utf-8",
        )
        with pytest.raises(WalkLoadError, match="schema validation"):
            load_walk(p)


class TestValidate:
    def test_showcase_clean_with_appspec(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        appspec = load_project_appspec(_SIMPLE)
        walk = load_walk(_SHOWCASE)
        issues = validate_walk(walk, appspec=appspec, require_core_only=True, require_story=True)
        errors = [i for i in issues if i.level == "error"]
        assert errors == [], [e.format() for e in errors]

    def test_unknown_persona(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec

        appspec = load_project_appspec(_SIMPLE)
        walk = load_walk(_SHOWCASE)
        walk.persona = "not_a_persona"
        issues = validate_walk(walk, appspec=appspec)
        assert any(i.code == "unknown_persona" for i in issues)

    def test_extension_action_warns(self, tmp_path: Path) -> None:
        p = tmp_path / "ext.yaml"
        p.write_text(
            "persona: member\n"
            "scenes:\n"
            "  - id: s\n"
            "    story: ST-020\n"
            "    actions:\n"
            "      - type: api_find\n"
            "        path: /tasks\n",
            encoding="utf-8",
        )
        walk = load_walk(p)
        assert walk.core_only() is False
        issues = validate_walk(walk)
        assert any(i.code == "extension_action" and i.level == "warning" for i in issues)
        hard = validate_walk(walk, require_core_only=True)
        assert any(i.code == "extension_action" and i.level == "error" for i in hard)

    def test_validate_walks_batch(self) -> None:
        paths = discover_walk_paths(_SIMPLE)
        walks, issues = validate_walks(paths)
        assert len(walks) >= 1
        assert not any(i.level == "error" and i.code == "load_failed" for i in issues)


class TestCoreSet:
    def test_core_subset_of_enum(self) -> None:
        assert CORE_ACTION_TYPES <= set(WalkActionType)


class TestRunnerDryRun:
    def test_dry_run_showcase(self) -> None:
        from dazzle.testing.walk.runner import run_walk_sync

        walk = load_walk(_SHOWCASE)
        result = run_walk_sync(
            walk,
            base_url="http://example.test",
            project_root=_SIMPLE,
            dry_run=True,
        )
        assert result.ok is True
        assert result.dry_run is True
        assert len(result.scenes) == 1
        assert all(a.ok for a in result.scenes[0].actions)
        assert "PASS" in result.summary()

    def test_api_find_missing_path_fails(self, tmp_path: Path) -> None:
        """api_find without path: fails closed (extension is implemented, args required)."""
        import asyncio
        from unittest.mock import AsyncMock

        from dazzle.testing.walk.runner import WalkRunner, run_walk_sync

        p = tmp_path / "ext.yaml"
        p.write_text(
            "persona: member\nscenes:\n  - id: s\n    actions:\n      - type: api_find\n",
            encoding="utf-8",
        )
        walk = load_walk(p)
        dry = run_walk_sync(walk, base_url="http://x", dry_run=True)
        assert dry.ok is True

        async def _go() -> None:
            async with WalkRunner(
                base_url="http://example.test",
                project_root=_SIMPLE,
                dry_run=False,
            ) as runner:
                runner.authenticate = AsyncMock()  # type: ignore[method-assign]
                res = await runner.run(walk)
                assert res.ok is False
                assert any(
                    a.type == "api_find" and not a.ok and "path" in a.message.lower()
                    for s in res.scenes
                    for a in s.actions
                )

        asyncio.run(_go())

    def test_assert_any_text_on_body(self) -> None:
        import asyncio

        from dazzle.testing.walk.models import ActionSpec, SceneSpec, WalkActionType
        from dazzle.testing.walk.runner import WalkRunner

        async def _go() -> None:
            async with WalkRunner(base_url="http://example.test", dry_run=False) as runner:
                runner.last_body = "Hello Task Board My Work"
                runner.last_status = 200
                runner.last_url = "http://example.test/app/workspaces/my_work"
                scene = SceneSpec(id="s", actions=[ActionSpec(type=WalkActionType.NAVIGATE)])
                ok = await runner._act_assert_any_text(
                    ActionSpec(type=WalkActionType.ASSERT_ANY_TEXT, texts=["Task", "Nope"]),
                    scene,
                )
                assert ok.ok is True
                bad = await runner._act_assert_any_text(
                    ActionSpec(type=WalkActionType.ASSERT_ANY_TEXT, texts=["Nope"]),
                    scene,
                )
                assert bad.ok is False
                login = await runner._act_assert_not_login(
                    ActionSpec(type=WalkActionType.ASSERT_NOT_LOGIN),
                    scene,
                )
                assert login.ok is True

        asyncio.run(_go())


class TestJobClaims:
    def test_load_showcase_registry(self) -> None:
        from dazzle.testing.walk.claims import discover_registry_path, load_registry

        path = discover_registry_path(_SIMPLE)
        assert path is not None
        reg = load_registry(path)
        assert reg.version == 1
        assert len(reg.guides) >= 1
        g = reg.guides[0]
        assert g.walk == "land_and_see_tasks"
        assert g.persona == "member"

    def test_check_documented_clean(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle.testing.walk.claims import check_registry, discover_registry_path, load_registry

        appspec = load_project_appspec(_SIMPLE)
        reg = load_registry(discover_registry_path(_SIMPLE))  # type: ignore[arg-type]
        result = check_registry(reg, project_root=_SIMPLE, appspec=appspec, run_walks=False)
        assert result.ok, [i.format() for i in result.errors]

    def test_verified_requires_walk(self, tmp_path: Path) -> None:
        from dazzle.testing.walk.claims import check_registry, load_registry

        p = tmp_path / "job_claims.yaml"
        p.write_text(
            "version: 1\n"
            "guides:\n"
            "  - id: bad\n"
            "    path: no-doc.md\n"
            "    persona: member\n"
            "    status: verified\n",
            encoding="utf-8",
        )
        # need dazzle.toml for project? check only uses paths
        (tmp_path / "dazzle.toml").write_text("[project]\nname = 't'\n", encoding="utf-8")
        reg = load_registry(p)
        result = check_registry(reg, project_root=tmp_path, appspec=None, run_walks=False)
        codes = {i.code for i in result.errors}
        assert "walk_required" in codes


class TestPackDryRun:
    def test_pack_a_simple_task(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle.testing.walk.pack import pack_dry_run

        appspec = load_project_appspec(_SIMPLE)
        result = pack_dry_run(_SIMPLE, "A", appspec=appspec, execute=False)
        assert result.pack == "A"
        assert "member-view-own-tasks" in result.guides
        assert "land_and_see_tasks" in result.walk_ids
        assert result.ok is True
        assert result.residuals == []
        assert all(w.dry_run for w in result.walk_results)

    def test_claims_residuals_empty_when_clean(self) -> None:
        from dazzle.core.appspec_loader import load_project_appspec
        from dazzle.testing.walk.pack import claims_residuals

        appspec = load_project_appspec(_SIMPLE)
        gaps = claims_residuals(_SIMPLE, appspec=appspec)
        assert gaps == []

    def test_unknown_pack_empty(self) -> None:
        from dazzle.testing.walk.pack import pack_dry_run

        result = pack_dry_run(_SIMPLE, "Z", execute=False)
        assert result.guides == []
        assert result.ok is True


class TestApiActions:
    """#1639 extension api_* handlers with mocked httpx."""

    def test_api_find_save_as(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from dazzle.testing.walk.actions_api import api_find
        from dazzle.testing.walk.models import ActionSpec, WalkActionType

        rows = [
            {"id": "a1", "period_key": "26A1", "company_name": "Other Co", "status": "open"},
            {
                "id": "b2",
                "period_key": "26A1",
                "company_name": "Demo · Briar",
                "status": "awaiting_client_approval",
            },
        ]

        async def fake_get(path, params=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"items": rows}
            return resp

        client = MagicMock()
        client.get = AsyncMock(side_effect=fake_get)
        vars_: dict[str, str] = {}
        action = ActionSpec(
            type=WalkActionType.API_FIND,
            path="/vatreturns",
            where={"period_key": "26A1"},
            company_name_contains="Demo · Briar",
            prefer_status="awaiting_client_approval",
            save_as="vat_id",
        )
        result = asyncio.run(api_find(client, action, vars_))
        assert result.ok is True
        assert vars_["vat_id"] == "b2"

    def test_api_assert_field(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from dazzle.testing.walk.actions_api import api_assert_field
        from dazzle.testing.walk.models import ActionSpec, WalkActionType

        async def fake_get(path):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"id": "b2", "status": "client_approved"}
            return resp

        client = MagicMock()
        client.get = AsyncMock(side_effect=fake_get)
        action = ActionSpec(
            type=WalkActionType.API_ASSERT_FIELD,
            path_template="/vatreturns/{vat_id}",
            field="status",
            equals="client_approved",
        )
        result = asyncio.run(api_assert_field(client, action, {"vat_id": "b2"}))
        assert result.ok is True

    def test_api_ensure_status_already(self) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from dazzle.testing.walk.actions_api import api_ensure_status
        from dazzle.testing.walk.models import ActionSpec, WalkActionType

        async def fake_get(path):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"status": "awaiting_client_approval"}
            return resp

        client = MagicMock()
        client.get = AsyncMock(side_effect=fake_get)
        action = ActionSpec(
            type=WalkActionType.API_ENSURE_STATUS,
            path_template="/vatreturns/{vat_id}",
            status="awaiting_client_approval",
        )
        result = asyncio.run(api_ensure_status(client, action, {"vat_id": "x"}))
        assert result.ok is True
        assert "already" in result.message

    def test_extension_action_runs_in_runner(self, tmp_path: Path) -> None:
        """Dry-run no longer fails on api_find; live dispatches (mocked auth)."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from dazzle.testing.walk.loader import load_walk
        from dazzle.testing.walk.runner import WalkRunner

        p = tmp_path / "ext.yaml"
        p.write_text(
            "persona: member\n"
            "scenes:\n"
            "  - id: s\n"
            "    actions:\n"
            "      - type: api_find\n"
            "        path: /tasks\n"
            "        save_as: tid\n",
            encoding="utf-8",
        )
        walk = load_walk(p)

        async def fake_get(path, params=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = [{"id": "t1", "title": "x"}]
            return resp

        async def _go() -> None:
            async with WalkRunner(
                base_url="http://example.test",
                project_root=_SIMPLE,
                dry_run=False,
            ) as runner:
                runner.authenticate = AsyncMock()  # type: ignore[method-assign]
                assert runner._client is not None
                runner._client.get = AsyncMock(side_effect=fake_get)  # type: ignore[method-assign]
                res = await runner.run(walk)
                assert res.ok is True
                assert runner.vars.get("tid") == "t1"

        asyncio.run(_go())


class TestCsrfPolicy:
    """CyFuture walk-runner-csrf-requirements R1–R2."""

    def test_mutating_request_gets_csrf_header(self) -> None:
        import asyncio

        import httpx

        from dazzle.testing.walk.policies import (
            CSRF_COOKIE,
            CSRF_HEADER,
            attach_csrf_request_hook,
            prime_csrf_cookie,
        )

        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            if request.url.path.endswith("/health"):
                return httpx.Response(
                    200,
                    headers=[(b"set-cookie", f"{CSRF_COOKIE}=tok123; Path=/".encode())],
                    json={"ok": True},
                )
            return httpx.Response(200, json={"status": "ok"})

        transport = httpx.MockTransport(handler)

        async def _go() -> None:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                attach_csrf_request_hook(client)
                token = await prime_csrf_cookie(client, "http://test")
                assert token == "tok123"
                await client.patch("/vatreturns/1", json={"status": "x"})
                await client.get("/vatreturns/1")

        asyncio.run(_go())
        patch_req = next(r for r in captured if r.method == "PATCH")
        get_req = next(r for r in captured if r.method == "GET" and "vatreturns" in str(r.url))
        assert patch_req.headers.get(CSRF_HEADER) == "tok123"
        assert CSRF_HEADER not in get_req.headers or get_req.headers.get(CSRF_HEADER) is None

    def test_multipart_post_includes_header(self) -> None:
        import asyncio

        import httpx

        from dazzle.testing.walk.policies import CSRF_COOKIE, CSRF_HEADER, attach_csrf_request_hook

        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                seen["csrf"] = request.headers.get(CSRF_HEADER, "")
            return httpx.Response(200, json={})

        async def _go() -> None:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler), base_url="http://test"
            ) as client:
                client.cookies.set(CSRF_COOKIE, "upload-tok")
                attach_csrf_request_hook(client)
                await client.post(
                    "/files/upload",
                    files={"file": ("a.txt", b"hello")},
                )

        asyncio.run(_go())
        assert seen.get("csrf") == "upload-tok"


class TestApiUploadSaveAs:
    def test_upload_honours_save_as(self, tmp_path: Path) -> None:
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from dazzle.testing.walk.actions_api import api_upload_file
        from dazzle.testing.walk.models import ActionSpec

        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 fake")

        async def fake_post(path, data=None, files=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"id": "file-99", "name": "doc.pdf"}
            return resp

        client = MagicMock()
        client.post = AsyncMock(side_effect=fake_post)
        vars_: dict[str, str] = {}
        action = ActionSpec.model_validate(
            {
                "type": "api_upload_file",
                "path": "/files/upload",
                "file_path": str(f),
                "file_field": "file",
                "save_as": "file_id",
            }
        )
        result = asyncio.run(api_upload_file(client, action, vars_, project_root=tmp_path))
        assert result.ok is True, result.message
        assert vars_.get("file_id") == "file-99"
