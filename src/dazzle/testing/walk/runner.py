"""Execute scene walks against a live app (#1638 PR2).

HTTP-first core actions (navigate, assert_*) via httpx + SessionManager
auth (``/__test__/authenticate`` or login). Optional Playwright for
``playwright_click`` / ``playwright_wait`` when the extra is installed.

Extension ``api_*`` actions are not implemented here — fail with a clear
code so pilot YAML can migrate gradually.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from dazzle.testing.session_manager import SessionManager
from dazzle.testing.walk.models import (
    CORE_ACTION_TYPES,
    ActionSpec,
    SceneSpec,
    SceneWalkSpec,
    WalkActionType,
)

LOGIN_PATHS = frozenset({"/login", "/auth/login", "/auth/signin"})


@dataclass
class ActionResult:
    """Outcome of one walk action."""

    type: str
    ok: bool
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneResult:
    """Outcome of one scene."""

    scene_id: str
    ok: bool
    story: str | None = None
    actions: list[ActionResult] = field(default_factory=list)
    error: str | None = None


@dataclass
class WalkRunResult:
    """Outcome of a full walk run."""

    walk_id: str
    persona: str
    ok: bool
    dry_run: bool = False
    base_url: str = ""
    scenes: list[SceneResult] = field(default_factory=list)
    error: str | None = None

    def summary(self) -> str:
        mode = "dry-run" if self.dry_run else "run"
        status = "PASS" if self.ok else "FAIL"
        n_ok = sum(1 for s in self.scenes if s.ok)
        return (
            f"{status} [{mode}] walk={self.walk_id} persona={self.persona} "
            f"scenes={n_ok}/{len(self.scenes)}" + (f" error={self.error}" if self.error else "")
        )


def _render(template: str | None, vars_: dict[str, str]) -> str:
    if not template:
        return ""
    out = template
    for key, val in vars_.items():
        out = out.replace("{" + key + "}", val)
    return out


class WalkRunner:
    """Stateful HTTP (+ optional Playwright) walk executor."""

    def __init__(
        self,
        *,
        base_url: str,
        project_root: Path | None = None,
        dry_run: bool = False,
        use_playwright: bool = False,
        timeout_s: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.project_root = project_root
        self.dry_run = dry_run
        self.use_playwright = use_playwright
        self.timeout_s = timeout_s
        self.vars: dict[str, str] = {}
        self.last_status: int | None = None
        self.last_url: str = ""
        self.last_body: str = ""
        self._cookies: dict[str, str] = {}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> WalkRunner:
        if not self.dry_run:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_s,
                follow_redirects=True,
                cookies=self._cookies,
            )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def authenticate(self, persona: str) -> None:
        """Establish session cookies for *persona* (no-op on dry-run)."""
        if self.dry_run:
            return
        if self.project_root is None:
            raise RuntimeError("project_root required for authentication")
        manager = SessionManager(self.project_root, base_url=self.base_url)
        existing = manager.load_session(persona)
        if existing and existing.session_token:
            valid = await manager.validate_session(persona)
            if valid:
                self._cookies = {"dazzle_session": existing.session_token}
                if self._client is not None:
                    self._client.cookies.set("dazzle_session", existing.session_token)
                return
        session = await manager.create_session(persona)
        self._cookies = {"dazzle_session": session.session_token}
        if self._client is not None:
            self._client.cookies.set("dazzle_session", session.session_token)

    async def run(self, walk: SceneWalkSpec) -> WalkRunResult:
        """Run all scenes; stop on first scene failure."""
        result = WalkRunResult(
            walk_id=walk.walk_id or "walk",
            persona=walk.persona,
            ok=True,
            dry_run=self.dry_run,
            base_url=self.base_url,
        )
        try:
            if not self.dry_run:
                await self.authenticate(walk.persona)
        except Exception as e:
            result.ok = False
            result.error = f"auth failed for persona {walk.persona!r}: {e}"
            return result

        for scene in walk.scenes:
            scene_result = await self._run_scene(scene)
            result.scenes.append(scene_result)
            if not scene_result.ok:
                result.ok = False
                result.error = scene_result.error or f"scene {scene.id} failed"
                break
        return result

    async def _run_scene(self, scene: SceneSpec) -> SceneResult:
        sr = SceneResult(scene_id=scene.id, ok=True, story=scene.story)
        # Seed entry path into vars for navigate without explicit entry on action
        if scene.entry:
            self.vars.setdefault("entry", _render(scene.entry, self.vars))
        for action in scene.actions:
            ar = await self._run_action(action, scene)
            sr.actions.append(ar)
            if not ar.ok:
                sr.ok = False
                sr.error = ar.message
                break
        return sr

    async def _run_action(self, action: ActionSpec, scene: SceneSpec) -> ActionResult:
        if self.dry_run:
            return ActionResult(
                type=action.type.value,
                ok=True,
                message="dry-run skip",
                detail={"core": action.type in CORE_ACTION_TYPES},
            )

        if action.type not in CORE_ACTION_TYPES:
            return ActionResult(
                type=action.type.value,
                ok=False,
                message=(
                    f"extension action {action.type.value!r} not implemented in runner "
                    "(PR2 core set only; api_* land later)"
                ),
            )

        handlers = {
            WalkActionType.NAVIGATE: self._act_navigate,
            WalkActionType.ASSERT_NOT_LOGIN: self._act_assert_not_login,
            WalkActionType.ASSERT_HTTP_OK: self._act_assert_http_ok,
            WalkActionType.ASSERT_HTTP_OK_OR_EMPTY: self._act_assert_http_ok_or_empty,
            WalkActionType.ASSERT_HTTP_OK_OR_FORBIDDEN: self._act_assert_http_ok_or_forbidden,
            WalkActionType.ASSERT_NO_SERVER_ERROR: self._act_assert_no_server_error,
            WalkActionType.ASSERT_NO_ERROR_BANNER: self._act_assert_no_error_banner,
            WalkActionType.ASSERT_ANY_TEXT: self._act_assert_any_text,
            WalkActionType.ASSERT_HAS_DZ_OR_CONTENT: self._act_assert_has_content,
            WalkActionType.PLAYWRIGHT_CLICK: self._act_playwright_click,
            WalkActionType.PLAYWRIGHT_WAIT: self._act_playwright_wait,
        }
        handler = handlers.get(action.type)
        if handler is None:
            return ActionResult(action.type.value, False, "no handler")
        try:
            return await handler(action, scene)
        except Exception as e:
            return ActionResult(action.type.value, False, f"{type(e).__name__}: {e}")

    def _entry_for(self, action: ActionSpec, scene: SceneSpec) -> str:
        raw = action.entry or scene.entry or self.vars.get("entry") or "/"
        path = _render(raw, self.vars)
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return path

    async def _get(self, path: str) -> httpx.Response:
        assert self._client is not None
        resp = await self._client.get(path)
        self.last_status = resp.status_code
        self.last_url = str(resp.url)
        self.last_body = resp.text
        return resp

    async def _act_navigate(self, action: ActionSpec, scene: SceneSpec) -> ActionResult:
        path = self._entry_for(action, scene)
        resp = await self._get(path)
        return ActionResult(
            action.type.value,
            True,
            f"GET {path} → {resp.status_code}",
            {"status": resp.status_code, "url": str(resp.url)},
        )

    async def _act_assert_not_login(self, action: ActionSpec, scene: SceneSpec) -> ActionResult:
        path = urlparse(self.last_url or "").path or ""
        ok = path not in LOGIN_PATHS
        return ActionResult(
            action.type.value,
            ok,
            "not on login" if ok else f"still on login path {path!r}",
            {"path": path},
        )

    async def _act_assert_http_ok(self, action: ActionSpec, scene: SceneSpec) -> ActionResult:
        status = self.last_status
        ok = status is not None and 200 <= status < 300
        return ActionResult(
            action.type.value,
            ok,
            f"status={status}" if ok else f"expected 2xx, got {status}",
            {"status": status},
        )

    async def _act_assert_http_ok_or_empty(
        self, action: ActionSpec, scene: SceneSpec
    ) -> ActionResult:
        status = self.last_status
        body = (self.last_body or "").strip()
        ok = status is not None and (200 <= status < 300 or not body)
        return ActionResult(
            action.type.value,
            ok,
            f"status={status} empty={not body}",
            {"status": status, "empty": not body},
        )

    async def _act_assert_http_ok_or_forbidden(
        self, action: ActionSpec, scene: SceneSpec
    ) -> ActionResult:
        status = self.last_status
        ok = status is not None and (200 <= status < 300 or status == 403)
        return ActionResult(
            action.type.value,
            ok,
            f"status={status}",
            {"status": status},
        )

    async def _act_assert_no_server_error(
        self, action: ActionSpec, scene: SceneSpec
    ) -> ActionResult:
        status = self.last_status
        ok = status is not None and status < 500
        return ActionResult(
            action.type.value,
            ok,
            f"status={status}" if ok else f"server error {status}",
            {"status": status},
        )

    async def _act_assert_no_error_banner(
        self, action: ActionSpec, scene: SceneSpec
    ) -> ActionResult:
        body = self.last_body or ""
        # Lightweight product chrome heuristics — not a full DOM scan.
        patterns = (
            r'class="[^"]*error[^"]*"',
            r"data-error=",
            r"Internal Server Error",
            r"Traceback \(most recent call last\)",
        )
        hits = [p for p in patterns if re.search(p, body, re.I)]
        ok = not hits
        return ActionResult(
            action.type.value,
            ok,
            "no error banner" if ok else f"error markers: {hits}",
            {"hits": hits},
        )

    async def _act_assert_any_text(self, action: ActionSpec, scene: SceneSpec) -> ActionResult:
        texts = action.texts or []
        body = self.last_body or ""
        found = [t for t in texts if t and t in body]
        ok = bool(found)
        return ActionResult(
            action.type.value,
            ok,
            f"found {found!r}" if ok else f"none of {texts!r} in body",
            {"found": found, "wanted": texts},
        )

    async def _act_assert_has_content(self, action: ActionSpec, scene: SceneSpec) -> ActionResult:
        body = self.last_body or ""
        has_dz = "data-dz" in body or "dz-" in body
        has_text = len(body.strip()) > 80
        ok = has_dz or has_text
        return ActionResult(
            action.type.value,
            ok,
            "content present" if ok else "body looks empty",
            {"has_dz": has_dz, "len": len(body)},
        )

    async def _act_playwright_click(self, action: ActionSpec, scene: SceneSpec) -> ActionResult:
        if not self.use_playwright:
            return ActionResult(
                action.type.value,
                False,
                "playwright_click requires --playwright (and playwright installed)",
            )
        return await self._playwright_click(action)

    async def _act_playwright_wait(self, action: ActionSpec, scene: SceneSpec) -> ActionResult:
        if not self.use_playwright:
            return ActionResult(
                action.type.value,
                False,
                "playwright_wait requires --playwright (and playwright installed)",
            )
        wait_ms = action.wait_ms or 1000
        await asyncio.sleep(wait_ms / 1000.0)
        return ActionResult(action.type.value, True, f"waited {wait_ms}ms")

    async def _playwright_click(self, action: ActionSpec) -> ActionResult:
        """Click by role/name using Playwright async API."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return ActionResult(
                action.type.value,
                False,
                "playwright not installed (pip install playwright && playwright install chromium)",
            )

        role = action.role or "button"
        name = action.name or ""
        timeout_ms = action.wait_ms or 5000

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx = await browser.new_context(
                base_url=self.base_url,
                storage_state=None,
            )
            # Inject session cookie
            if self._cookies:
                await ctx.add_cookies(
                    [
                        {
                            "name": k,
                            "value": v,
                            "url": self.base_url,
                        }
                        for k, v in self._cookies.items()
                    ]
                )
            page = await ctx.new_page()
            try:
                target = self.last_url or self.base_url + "/"
                if not target.startswith("http"):
                    target = urljoin(self.base_url + "/", target.lstrip("/"))
                await page.goto(target, wait_until="networkidle", timeout=timeout_ms)
                if action.regex and name:
                    locator = page.get_by_role(role, name=re.compile(name))
                else:
                    locator = page.get_by_role(role, name=name, exact=True)
                await locator.first.click(timeout=timeout_ms)
                await page.wait_for_load_state("networkidle", timeout=timeout_ms)
                self.last_url = page.url
                self.last_body = await page.content()
                self.last_status = 200
                return ActionResult(
                    action.type.value,
                    True,
                    f"clicked {role}/{name!r}",
                    {"url": page.url},
                )
            finally:
                await ctx.close()
                await browser.close()


async def run_walk(
    walk: SceneWalkSpec,
    *,
    base_url: str,
    project_root: Path | None = None,
    dry_run: bool = False,
    use_playwright: bool = False,
    timeout_s: float = 30.0,
) -> WalkRunResult:
    """Convenience: open runner, authenticate, execute walk."""
    async with WalkRunner(
        base_url=base_url,
        project_root=project_root,
        dry_run=dry_run,
        use_playwright=use_playwright,
        timeout_s=timeout_s,
    ) as runner:
        return await runner.run(walk)


def run_walk_sync(
    walk: SceneWalkSpec,
    *,
    base_url: str,
    project_root: Path | None = None,
    dry_run: bool = False,
    use_playwright: bool = False,
    timeout_s: float = 30.0,
) -> WalkRunResult:
    """Sync wrapper for CLI."""
    return asyncio.run(
        run_walk(
            walk,
            base_url=base_url,
            project_root=project_root,
            dry_run=dry_run,
            use_playwright=use_playwright,
            timeout_s=timeout_s,
        )
    )
