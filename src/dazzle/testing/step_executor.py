"""Step execution for the agent-E2E harness TestRunner (#1446).

Extracted from the TestRunner god class: the ~28 ``_execute_*_step`` handlers, their
dispatch (``_get_step_handler`` / ``execute_step`` / ``_scan_unknown_actions``), and the
step-only helpers (``_resolve_surface_url`` / ``_build_surface_url_map`` /
``_track_post_cleanup`` / ``_resolve_credential`` / ``_resolve_refs``). ``StepExecutor``
holds the ``TestRunner`` and reads its transport via the ``client`` / ``project_path``
properties, so the handlers moved here verbatim; ``TestRunner.execute_step`` delegates.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.core.ir import SurfaceMode
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.strings import entity_slug
from dazzle.testing.data_generator import DataGenerator
from dazzle.testing.test_runner import StepResult, TestResult

if TYPE_CHECKING:
    from dazzle.testing.test_runner import DazzleClient, TestRunner

logger = logging.getLogger(__name__)


class StepExecutor:
    """Executes individual test steps on behalf of a :class:`TestRunner`."""

    def __init__(self, runner: TestRunner):
        self._runner = runner
        self._surface_url_map: dict[str, str] | None = None

    @property
    def client(self) -> DazzleClient | None:
        return self._runner.client

    @property
    def project_path(self) -> Path:
        return self._runner.project_path

    def _execute_login_as_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        success = self.client.authenticate(target)
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.SKIPPED,
            message="" if success else "Auth not required or failed",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _resolve_surface_url(self, name: str) -> str | None:
        """#1224: resolve a surface/workspace name to its URL path.

        Returns ``None`` for unknown names or for kinds that need a
        record id (view / edit) — callers should fall through to a
        clear error rather than constructing a wrong URL.

        Pre-#1224, the test runner hardcoded ``/app/workspaces/{name}``
        for every surface kind, causing 17 TD-* tests to 404 on
        v0.71.161 because list / create surfaces have different URL
        templates that the route generator already knows but the
        runner did not.
        """
        if self._surface_url_map is None:
            self._surface_url_map = self._build_surface_url_map()
        return self._surface_url_map.get(name)

    def _build_surface_url_map(self) -> dict[str, str]:
        """Parse the project's DSL and build a surface-name → URL map (#1224).

        Templates mirror ``template_compiler.py``'s authoritative ``route_map``
        (``/app/{entity_slug}`` for LIST, ``/app/{entity_slug}/create`` for
        CREATE) — #1230 fixed a v0.71.x divergence where the resolver picked
        ``/{plural}`` (which Dazzle does not mount for UI surfaces, only the
        JSON API), producing 404s on CREATE walks and wrong-content checks on
        LIST walks.
        """
        out: dict[str, str] = {}
        dsl_dir = self.project_path / "dsl"
        if not dsl_dir.is_dir():
            return out
        try:
            modules = parse_modules(sorted(dsl_dir.glob("*.dsl")))
            if not modules:
                return out
            # build_appspec needs the *module* name (e.g. 'tinyapp.core'),
            # not the project directory name. Pick the first module —
            # dazzle apps conventionally have one root module per project.
            appspec = build_appspec(modules, modules[0].name)
        except Exception:  # noqa: BLE001 — best-effort URL resolution
            return out

        for ws in getattr(appspec, "workspaces", None) or []:
            out[ws.name] = f"/app/workspaces/{ws.name}"

        for surface in getattr(appspec, "surfaces", None) or []:
            entity = getattr(surface, "entity_ref", None)
            if entity is None:
                continue
            slug = entity_slug(entity)
            mode = getattr(surface, "mode", None)
            if mode == SurfaceMode.LIST:
                out[surface.name] = f"/app/{slug}"
            elif mode == SurfaceMode.CREATE:
                out[surface.name] = f"/app/{slug}/create"
            # view / edit need a record id — skip; callers see None and
            # fall through to a clear error rather than a wrong URL.
        return out

    def _execute_navigate_to_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1135: stash the resolved route into the step context so a
        subsequent ``assert_visible`` actually checks the navigated
        workspace, not the bare ``ui_url``.

        Pre-#1135 this was a no-op stub — comment said "navigation is
        conceptual in API tests" — but the test design **does** carry
        the workspace route in ``data.route`` and the operator expects
        the next ``assert_visible`` to inspect that page. The no-op
        meant every ``WS_*_NAV`` test smoke-tested the same base URL
        with different cookies; failures couldn't be diagnosed because
        the message didn't say which URL was checked.
        """
        from urllib.parse import urljoin

        assert self.client is not None
        route = resolved_data.get("route") if resolved_data else None
        if not route:
            # #1224: when data.route is missing, resolve from the step's
            # target (surface or workspace name) via the route generator
            # templates. Previously the design's route was the only path
            # into _current_ui_url; assert_visible then fell back to a
            # hardcoded /app/workspaces/{surfaces[0]} template that 404'd
            # for any list/create surface or wrong-position dashboard.
            stripped_target = target.split(":", 1)[-1] if target else ""
            if stripped_target:
                route = self._resolve_surface_url(stripped_target)
        if route:
            # Resolve relative to the client's ui_url. urljoin handles
            # both absolute (``http://...``) and relative (``/app/x``)
            # forms; ``ui_url + "/"`` ensures the base is treated as a
            # directory so ``/app/x`` overrides cleanly.
            context["_current_ui_url"] = urljoin(self.client.ui_url + "/", route.lstrip("/"))
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_create_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        entity_name = target.replace("entity:", "")
        entity_data = DataGenerator(self.client).generate(entity_name, resolved_data)
        result = self.client.entities.create_entity(entity_name, entity_data)
        success = result is not None
        if success and store_result and result:
            context[store_result] = result
        if success:
            # #1139: stash the actually-sent payload so a following
            # create_expect_error step can reproduce the unique-field
            # collision. generate_entity_data regenerates unique fields
            # whose literal values from the test design would otherwise
            # diverge between the two POSTs.
            context[f"_last_created_data:{entity_name}"] = entity_data
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message="" if success else f"Create failed for {entity_name}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_update_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="Update requires entity ID context",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_visible_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1135 / #1149: include URL + HTTP status + body excerpt in
        the failure message, plus a fix hint when the failure shape
        matches a known design omission (missing login_as or
        navigate_to).

        Pre-#1135 the message was the literal "UI check failed" —
        no URL, no status, no body. #1135 added the URL + status +
        excerpt. #1149 adds the fix hint: when the check hit the
        base UI URL (no preceding ``navigate_to``) AND got a 30x
        redirect, the design almost certainly needs ``login_as`` +
        ``navigate_to`` before this step. Rather than make the
        operator guess, the failure message names the missing
        steps explicitly.
        """
        assert self.client is not None
        # The preceding navigate_to step stashes the workspace URL in
        # context; fall back to the client's base ui_url when no
        # navigate happened.
        check_url = context.get("_current_ui_url")
        if not check_url:
            # #1211 fallback (revised in #1224): synthesise URL from the
            # design's first surface when no navigate_to has stashed
            # one. #1224 fix: dispatch by SurfaceKind via the route
            # generator's actual templates, not the hardcoded
            # /app/workspaces/{name} template that 404'd for every
            # list/create surface. surfaces[0] is still the source —
            # tests that emit bare assert_visible against multi-surface
            # designs are themselves ambiguous; the design author should
            # add an explicit navigate_to.
            surfaces = context.get("_design_surfaces") or []
            if surfaces:
                from urllib.parse import urljoin

                first = surfaces[0]
                first_name = first if isinstance(first, str) else first.get("name", "")
                resolved = self._resolve_surface_url(first_name) if first_name else None
                if resolved:
                    check_url = urljoin(self.client.ui_url + "/", resolved.lstrip("/"))
                    context["_current_ui_url"] = check_url
        result = self.client.check_ui_loads(url=check_url)
        # #1149: synthesise a fix hint from the failure shape.
        hint = ""
        if not result.ok:
            had_navigate = check_url is not None
            had_login = self.client._auth_token is not None or bool(
                self.client.client.cookies.get("dazzle_session")
            )
            hints: list[str] = []
            if result.status in (301, 302, 303, 307, 308) and not had_login:
                hints.append(
                    "GET → 3xx + no auth session: design is probably missing a "
                    "`login_as <persona>` step before this `assert_visible`."
                )
            if not had_navigate:
                hints.append(
                    "No preceding `navigate_to` — check hit the base UI url, not a "
                    "specific surface. Add `{action: navigate_to, target: workspace:<name>, "
                    "data: {route: '/app/...'}}` before this step."
                )
            if hints:
                hint = " | hint: " + " ".join(hints)
        message = (
            ""
            if result.ok
            else f"UI check failed: GET {result.url} → {result.status} | {result.excerpt!r}{hint}"
        )
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if result.ok else TestResult.FAILED,
            message=message,
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_count_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        data: dict[str, Any],
    ) -> StepResult:
        assert self.client is not None
        entity_name = target.replace("entity:", "")
        if entity_name.endswith("-card"):
            entity_name = entity_name[:-5]
        elif entity_name.endswith("-row"):
            entity_name = entity_name[:-4]
        entity_mapping = {
            "overdue-task": "Task",
            "task-card": "Task",
            "task-row": "Task",
            "user-row": "User",
            "device-row": "Device",
        }
        if entity_name in entity_mapping:
            entity_name = entity_mapping[entity_name]
        elif "-" in entity_name:
            entity_name = entity_name.replace("-", " ").title().replace(" ", "")
        elif entity_name.islower():
            entity_name = entity_name.capitalize()
        entities = self.client.entities.get_entities(entity_name)
        min_count = data.get("min", 0)
        success = len(entities) >= min_count
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message=f"Found {len(entities)} {entity_name} (min: {min_count})",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_ui_only_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="UI action skipped in API test",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_ui_assertion_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="UI assertion skipped",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_check_route_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        data: dict[str, Any],
    ) -> StepResult:
        assert self.client is not None
        if not target.startswith("workspace:"):
            return StepResult(
                action=action,
                target=target,
                result=TestResult.SKIPPED,
                message="Non-workspace route check skipped",
                duration_ms=(time.time() - start_time) * 1000,
            )
        workspace_name = target.replace("workspace:", "")
        route = data.get("route", f"/app/workspaces/{workspace_name}")
        try:
            resp = self.client._request(
                "GET", f"{self.client.ui_url}{route}", follow_redirects=True
            )
            if resp.status_code in (200, 304, 401):
                msg = f"Workspace '{workspace_name}' route exists"
                if resp.status_code == 401:
                    msg += " (protected)"
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.PASSED,
                    message=msg,
                    duration_ms=(time.time() - start_time) * 1000,
                )
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message=f"Route {route} returned {resp.status_code}",
                duration_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message=f"Route check failed: {e}",
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _execute_e2e_only_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="E2E action skipped in API test",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_read_list_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        entity_name = target.replace("entity:", "")
        entities = self.client.entities.get_entities(entity_name)
        context["last_response"] = type(
            "Response",
            (),
            {
                "status_code": 200,
                "cookies": {},
                "headers": {},
                "json": lambda: entities,
            },
        )()
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            message=f"Retrieved {len(entities)} {entity_name} entities",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _track_post_cleanup(self, resp: Any, step: dict[str, Any] | None) -> None:
        """#1210: explicit-opt-in cleanup tracking for ``post`` / ``post_json``.

        If the step spec carries ``cleanup_entity: <EntityName>`` AND the
        response is 2xx with a JSON body containing an ``id``, track
        ``(EntityName, id)`` on the client's CleanupManager so the
        end-of-run ``--cleanup`` phase deletes it.

        Absent the hint, no tracking happens — this preserves existing
        behaviour for transition / auth / form POSTs that don't create
        entities (and would 404 on DELETE).
        """
        if step is None or self.client is None:
            return
        cleanup_entity = step.get("cleanup_entity")
        if not cleanup_entity:
            return
        status_code = getattr(resp, "status_code", None)
        if status_code is None or not (200 <= int(status_code) < 300):
            return
        try:
            body = resp.json()
        except Exception:
            logger.debug("post cleanup_entity: response body not JSON", exc_info=True)
            return
        if not isinstance(body, dict):
            return
        entity_id = body.get("id")
        if entity_id is None:
            return
        self.client.cleanup.track(str(cleanup_entity), str(entity_id))

    def _execute_post_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        url = f"{self.client.ui_url}{target}"
        resp = self.client._request("POST", url, data=resolved_data, follow_redirects=False)
        context["last_response"] = resp
        self._track_post_cleanup(resp, _kw.get("step"))
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            message=f"POST {target} → {resp.status_code}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_post_json_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        url = f"{self.client.api_url}{target}"
        resp = self.client._request("POST", url, json=resolved_data, follow_redirects=False)
        context["last_response"] = resp
        self._track_post_cleanup(resp, _kw.get("step"))
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            message=f"POST(json) {target} → {resp.status_code}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_clear_cookies_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        self.client.client.cookies.clear()
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            message="Cookies cleared",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_get_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        url = f"{self.client.ui_url}{target}"
        follow = resolved_data.get("follow_redirects", False)
        resp = self.client._request("GET", url, follow_redirects=follow)
        context["last_response"] = resp
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            message=f"GET {target} → {resp.status_code}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_get_with_cookie_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        cookie_name = resolved_data.get("cookie", "dazzle_session")
        cookie_value = resolved_data.get("value", "invalid-token")
        follow = resolved_data.get("follow_redirects", False)
        url = f"{self.client.ui_url}{target}"
        resp = self.client._request(
            "GET",
            url,
            cookies={cookie_name: cookie_value},
            follow_redirects=follow,
        )
        context["last_response"] = resp
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED,
            message=f"GET {target} with {cookie_name}={cookie_value} → {resp.status_code}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_status_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        last_resp = context.get("last_response")
        if last_resp is None:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message="No previous response to check",
                duration_ms=(time.time() - start_time) * 1000,
            )
        expected = resolved_data.get("status", 200)
        actual = last_resp.status_code
        success = actual == expected
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message=f"Expected {expected}, got {actual}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_cookie_set_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        last_resp = context.get("last_response")
        cookie_name = resolved_data.get("cookie", "dazzle_session")
        has_cookie = (last_resp is not None and cookie_name in last_resp.cookies) or bool(
            self.client.client.cookies.get(cookie_name)
        )
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if has_cookie else TestResult.FAILED,
            message=f"Cookie '{cookie_name}' {'present' if has_cookie else 'missing'}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_no_cookie_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        last_resp = context.get("last_response")
        cookie_name = resolved_data.get("cookie", "dazzle_session")
        has_cookie = False
        if last_resp is not None and cookie_name in last_resp.cookies:
            cookie_val = last_resp.cookies.get(cookie_name)
            # Empty value or Max-Age=0 means the server is clearing, not setting
            if cookie_val and cookie_val != "":
                has_cookie = True
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if not has_cookie else TestResult.FAILED,
            message=f"Cookie '{cookie_name}' {'absent (good)' if not has_cookie else 'unexpectedly present'}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_cookie_cleared_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        assert self.client is not None
        last_resp = context.get("last_response")
        cookie_name = resolved_data.get("cookie", "dazzle_session")
        cleared = False
        if last_resp is not None:
            set_cookie_hdr = last_resp.headers.get("set-cookie", "")
            if cookie_name in set_cookie_hdr and "Max-Age=0" in set_cookie_hdr:
                cleared = True
            cookie_val = last_resp.cookies.get(cookie_name)
            if cookie_val is not None and (cookie_val == "" or cookie_val == '""'):
                cleared = True
        if not cleared:
            jar_val = self.client.client.cookies.get(cookie_name)
            if not jar_val or jar_val == "":
                cleared = True
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if cleared else TestResult.FAILED,
            message=f"Cookie '{cookie_name}' {'cleared' if cleared else 'still set'}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_redirect_url_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        last_resp = context.get("last_response")
        if last_resp is None:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message="No previous response to check",
                duration_ms=(time.time() - start_time) * 1000,
            )
        expected_url = resolved_data.get("redirect_url", "/app")
        actual_url = last_resp.headers.get("location", "")
        if not actual_url:
            try:
                body = last_resp.json()
                actual_url = body.get("redirect_url", body.get("redirect", ""))
            except Exception:
                actual_url = ""
        if not actual_url:
            actual_url = last_resp.headers.get("hx-redirect", "")
        success = actual_url.rstrip("/").startswith(expected_url.rstrip("/"))
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message=f"Expected redirect to '{expected_url}', got '{actual_url}'",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_unauthenticated_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        last_resp = context.get("last_response")
        if last_resp is None:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message="No previous response to check",
                duration_ms=(time.time() - start_time) * 1000,
            )
        # 403 is included because workspace RBAC returns 403 for
        # unauthenticated users who lack the required persona role.
        expected_codes = resolved_data.get("expect", [401, 302, 403])
        actual = last_resp.status_code
        success = actual in expected_codes
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message=f"Status {actual} {'matches' if success else 'not in'} {expected_codes}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_trigger_transition_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="Transition requires entity context",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_state_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1138: SM_* state-machine assertion.

        Today the runner can't reliably resolve "which entity id" to
        re-fetch without a stable cross-step entity-context contract
        (see #1138 follow-up). Skipping cleanly here is strictly
        better than the pre-fix "Unknown test action — step skipped"
        warning + opaque downstream failure: a SKIP doesn't move the
        FAIL pile and surfaces a clear message in the run log.
        """
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="assert_state requires entity-id context (not yet wired)",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_authenticated_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1138 / #1142: assert the current session is authenticated.

        The canonical ACL test pattern emitted by ``dsl_test_generator``
        is ``login_as`` immediately followed by ``assert_authenticated``,
        so we cannot rely on ``context['last_response']`` — login_as
        doesn't populate it. Self-bootstrap with ``GET /auth/me``
        instead: a 2xx response with the auth headers in force means
        the session is valid; 401/403 means the server rejected it.
        Stash the response in ``context['last_response']`` so any
        following ``assert_error``-style step can introspect it too.

        Falls back to inspecting a pre-existing ``last_response`` when
        present, which keeps the alternative "login_as → probe → assert"
        pattern working.
        """
        assert self.client is not None
        last_resp = context.get("last_response")
        if last_resp is None:
            try:
                last_resp = self.client._request(
                    "GET",
                    f"{self.client.api_url}/auth/me",
                    headers=self.client._auth_headers(),
                )
            except Exception as e:
                return StepResult(
                    action=action,
                    target=target,
                    result=TestResult.FAILED,
                    message=f"/auth/me probe failed: {e}",
                    duration_ms=(time.time() - start_time) * 1000,
                )
            context["last_response"] = last_resp
        expected_codes = resolved_data.get("expect", list(range(200, 300)))
        actual = last_resp.status_code
        success = actual in expected_codes
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message=f"Status {actual} {'matches' if success else 'not in'} {expected_codes}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_transition_expect_error_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1138: sibling of ``create_expect_error`` for invalid state
        transitions. Currently SKIP — like ``trigger_transition``,
        the entity-id context contract isn't standardised yet, so a
        real PATCH-and-expect-4xx implementation would have a
        higher-than-acceptable false-fail rate. Stub clears the
        unknown-action warning."""
        return StepResult(
            action=action,
            target=target,
            result=TestResult.SKIPPED,
            message="transition_expect_error requires entity-id context (not yet wired)",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_create_expect_error_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1133: POST to the entity create endpoint expecting a 4xx response.

        Validation tests emit this action to assert that an entity
        creation request with missing/invalid data is rejected. The
        complementary ``assert_error`` step then introspects
        ``context['last_response']`` to verify the error shape.

        Stores the response in ``context['last_response']`` regardless
        of outcome so downstream steps can introspect it. PASSES iff
        the server returns 4xx; FAILS on 2xx/3xx (a request that
        succeeded was supposed to be rejected) and on 5xx (a server
        crash is not the same as a validation error).
        """
        assert self.client is not None
        entity_name = target.replace("entity:", "")
        endpoint = self.client.entities._entity_endpoint(entity_name)
        # #1139: prefer the payload actually sent by the preceding
        # create step (which has post-generation unique-field values)
        # over the raw resolved_data literal — otherwise a "duplicate
        # email" scenario sends two different emails and never trips
        # the unique constraint.
        payload = context.get(f"_last_created_data:{entity_name}", resolved_data)
        try:
            resp = self.client._request(
                "POST",
                f"{self.client.api_url}{endpoint}",
                json=payload,
                headers=self.client._auth_headers(),
            )
        except Exception as e:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message=f"Request failed: {e}",
                duration_ms=(time.time() - start_time) * 1000,
            )
        context["last_response"] = resp
        is_client_error = 400 <= resp.status_code < 500
        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if is_client_error else TestResult.FAILED,
            message=f"Expected 4xx, got {resp.status_code}",
            duration_ms=(time.time() - start_time) * 1000,
        )

    def _execute_assert_error_step(
        self,
        action: str,
        target: str,
        resolved_data: dict[str, Any],
        context: dict[str, Any],
        store_result: str | None,
        start_time: float,
        **_kw: Any,
    ) -> StepResult:
        """#1133: assert the previous response carries an error indicator.

        Accepts either a 4xx status OR a JSON body containing a
        ``detail`` / ``errors`` / ``error`` field — the union of
        FastAPI's default validation-error shape (`{detail: [...]}`)
        and common project-side custom error payloads.

        When ``resolved_data`` contains ``field``, the body is also
        checked for a reference to that field name (matches the
        FastAPI ``detail[].loc`` convention).
        """
        last_resp = context.get("last_response")
        if last_resp is None:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.FAILED,
                message="No previous response to inspect for error",
                duration_ms=(time.time() - start_time) * 1000,
            )
        is_client_error = 400 <= last_resp.status_code < 500
        body_has_error_key = False
        body_repr = ""
        try:
            body = last_resp.json()
            if isinstance(body, dict):
                body_has_error_key = any(k in body for k in ("detail", "errors", "error"))
                body_repr = json.dumps(body)[:200]
        except Exception:
            body_repr = (last_resp.text or "")[:200]

        success = is_client_error or body_has_error_key
        expected_field = resolved_data.get("field")
        if success and expected_field:
            success = expected_field in body_repr

        return StepResult(
            action=action,
            target=target,
            result=TestResult.PASSED if success else TestResult.FAILED,
            message=(
                f"status={last_resp.status_code} has_error_key={body_has_error_key} "
                f"body={body_repr!r}"
            ),
            duration_ms=(time.time() - start_time) * 1000,
        )

    # Dispatch table mapping action names to handler methods.
    # Multi-action entries (tuples) are expanded in _get_step_handler().
    _STEP_DISPATCH_SINGLE: dict[str, str] = {
        "login_as": "_execute_login_as_step",
        "navigate_to": "_execute_navigate_to_step",
        "create": "_execute_create_step",
        "update": "_execute_update_step",
        "assert_visible": "_execute_assert_visible_step",
        "assert_count": "_execute_assert_count_step",
        "trigger_transition": "_execute_trigger_transition_step",
        # #1138: alias — designs emit `transition` as the shorter form of
        # `trigger_transition`. Routes to the same SKIP stub.
        "transition": "_execute_trigger_transition_step",
        "transition_expect_error": "_execute_transition_expect_error_step",
        "assert_state": "_execute_assert_state_step",
        "assert_authenticated": "_execute_assert_authenticated_step",
        "check_route": "_execute_check_route_step",
        "read_list": "_execute_read_list_step",
        "post": "_execute_post_step",
        "post_json": "_execute_post_json_step",
        "clear_cookies": "_execute_clear_cookies_step",
        "get": "_execute_get_step",
        "get_with_cookie": "_execute_get_with_cookie_step",
        "assert_status": "_execute_assert_status_step",
        "assert_cookie_set": "_execute_assert_cookie_set_step",
        "assert_no_cookie": "_execute_assert_no_cookie_step",
        "assert_cookie_cleared": "_execute_assert_cookie_cleared_step",
        "assert_redirect_url": "_execute_assert_redirect_url_step",
        "assert_unauthenticated": "_execute_assert_unauthenticated_step",
        # #1133: validation-test actions emitted by ValidationTestBuilder.
        # Previously fell through to the "Unknown test action" warning
        # branch and skipped silently — the most common cause of TD-*
        # tests failing with "UI check failed" and no further detail.
        "create_expect_error": "_execute_create_expect_error_step",
        "assert_error": "_execute_assert_error_step",
    }
    _STEP_DISPATCH_MULTI: dict[str, str] = {
        "click": "_execute_ui_only_step",
        "fill": "_execute_ui_only_step",
        "select": "_execute_ui_only_step",
        "wait_for": "_execute_ui_only_step",
        # #1133: UI-only form actions emitted by user-authored / LLM-generated
        # designs. They require a browser; in API-only test mode they skip
        # cleanly rather than emitting an "Unknown test action" warning.
        "fill_form": "_execute_ui_only_step",
        "submit_form": "_execute_ui_only_step",
        # #1138: persona goal recipes are inherently multi-step UI flows;
        # API-only mode SKIPs cleanly rather than emitting "Unknown
        # test action".
        "achieve_goal": "_execute_ui_only_step",
        "assert_not_visible": "_execute_ui_assertion_step",
        "assert_text": "_execute_ui_assertion_step",
        "wait_for_load": "_execute_e2e_only_step",
        "assert_no_errors": "_execute_e2e_only_step",
    }

    def _get_step_handler(self, action: str) -> Callable[..., StepResult] | None:
        """Look up the handler for an action name."""
        method_name = self._STEP_DISPATCH_SINGLE.get(action) or self._STEP_DISPATCH_MULTI.get(
            action
        )
        if method_name is None:
            return None
        handler: Callable[..., StepResult] = getattr(self, method_name)
        return handler

    def _scan_unknown_actions(self, designs: list[dict[str, Any]]) -> set[str]:
        """#1133: collect every action name referenced by ``designs`` that
        has no entry in ``_STEP_DISPATCH_SINGLE`` / ``_STEP_DISPATCH_MULTI``.

        Pure introspection — no side effects. The runner's main entry
        point uses this to log one ERROR-level line up front instead
        of per-step WARNING-level skip noise.
        """
        known = set(self._STEP_DISPATCH_SINGLE) | set(self._STEP_DISPATCH_MULTI)
        unknown: set[str] = set()
        for design in designs:
            for step in design.get("steps", []) or []:
                action = step.get("action")
                if action and action not in known:
                    unknown.add(action)
        return unknown

    def execute_step(
        self, step: dict[str, Any], design: dict[str, Any], context: dict[str, Any] | None = None
    ) -> StepResult:
        """Execute a single test step.

        Args:
            step: The step definition from the test design
            design: The full test design (for context)
            context: Shared context for storing step results (e.g., created entity IDs)
        """
        assert self.client is not None
        action = step.get("action", "unknown")
        target = step.get("target", "")
        data = step.get("data", {}) or {}
        store_result = step.get("store_result")

        if context is None:
            context = {}

        resolved_data = self._resolve_refs(data, context)
        start_time = time.time()

        kwargs: dict[str, Any] = {
            "action": action,
            "target": target,
            "resolved_data": resolved_data,
            "context": context,
            "store_result": store_result,
            "start_time": start_time,
            "data": data,
            # #1210: pass the raw step so handlers can read optional
            # fields like ``cleanup_entity`` without widening the kwargs
            # contract for every existing handler.
            "step": step,
        }

        try:
            handler = self._get_step_handler(action)
            if handler is not None:
                return handler(**kwargs)

            logger.warning("Unknown test action '%s' — step skipped", action)
            return StepResult(
                action=action,
                target=target,
                result=TestResult.SKIPPED,
                message=f"Unknown action: {action}",
                duration_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            return StepResult(
                action=action,
                target=target,
                result=TestResult.ERROR,
                message=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _resolve_credential(self, persona: str, field: str) -> str:
        """Resolve a persona credential (email or password) from test config.

        Looks up credentials from (in priority order):
        1. DAZZLE_TEST_EMAIL / DAZZLE_TEST_PASSWORD env vars (admin only)
        2. .dazzle/test_credentials.json personas.<persona> section
        3. .dazzle/test_credentials.json top-level (admin fallback)
        """
        # Admin: prefer env vars
        if persona == "admin" and field == "email":
            val = os.environ.get("DAZZLE_TEST_EMAIL")
            if val:
                return val
        if persona == "admin" and field == "password":
            val = os.environ.get("DAZZLE_TEST_PASSWORD")
            if val:
                return val

        # Credentials file — resolved against the project root, not the CWD
        # (non-admin personas reach this line; a CWD-relative path silently
        # missed the file and returned the unresolved marker, #1513).
        creds_path = self.project_path / ".dazzle" / "test_credentials.json"
        if creds_path.exists():
            try:
                creds = json.loads(creds_path.read_text(encoding="utf-8"))
                personas = creds.get("personas", {})
                persona_creds = personas.get(persona, {})
                val = persona_creds.get(field)
                if val:
                    return str(val)
                # Admin fallback to top-level
                if persona == "admin":
                    val = creds.get(field)
                    if val:
                        return str(val)
            except Exception:
                logger.warning(
                    "Failed to read test auth field '%s' for persona '%s'",
                    field,
                    persona,
                    exc_info=True,
                )

        return f"__PERSONA_{field.upper()}__"  # unresolved

    def _resolve_refs(self, data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Resolve $ref: placeholders and __PERSONA_*__ markers in data.

        Placeholders have the format: $ref:stored_name.field_name
        For example: $ref:parent_task.id -> context["parent_task"]["id"]

        Credential markers: __PERSONA_EMAIL__ and __PERSONA_PASSWORD__
        are resolved from test_credentials.json using the test's persona.

        Args:
            data: Dictionary potentially containing $ref: placeholders
            context: Dictionary of stored step results

        Returns:
            New dictionary with placeholders resolved
        """

        resolved = {}
        ref_pattern = re.compile(r"^\$ref:(\w+)\.(\w+)$")
        persona = context.get("_persona", "admin")

        for key, value in data.items():
            if isinstance(value, str) and value.startswith("$ref:"):
                match = ref_pattern.match(value)
                if match:
                    stored_name = match.group(1)
                    field_name = match.group(2)
                    if stored_name in context:
                        stored_data = context[stored_name]
                        if isinstance(stored_data, dict) and field_name in stored_data:
                            resolved[key] = stored_data[field_name]
                        else:
                            # Couldn't resolve, keep original
                            resolved[key] = value
                    else:
                        # Stored name not found, keep original
                        resolved[key] = value
                else:
                    # Pattern didn't match, keep original
                    resolved[key] = value
            elif isinstance(value, str) and value == "__PERSONA_EMAIL__":
                resolved[key] = self._resolve_credential(persona, "email")
            elif isinstance(value, str) and value == "__PERSONA_PASSWORD__":
                resolved[key] = self._resolve_credential(persona, "password")
            elif isinstance(value, dict):
                # Recursively resolve nested dicts
                resolved[key] = self._resolve_refs(value, context)
            else:
                resolved[key] = value

        return resolved
