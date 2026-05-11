"""Issue #1036 (v0.67.23): regression test that workspace routes
render zero Jinja templates when `app.state.fragment_chrome=True`.

Pre-fix the workspace full-page handler unconditionally called
`render_fragment("workspace/workspace.html", ...)` even with
fragment_chrome on, blocking Jinja retirement for chrome=on apps.

Mirrors `test_simple_task_no_jinja_when_chrome_on.py`'s
`_JinjaSpy` shape — pin the typed-Fragment workspace-render path
so any regression to the legacy Jinja chrome fires a clear test
failure.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jinja2 import Template

from dazzle.core.appspec_loader import load_project_appspec

pytest.importorskip("dazzle_ui.runtime.page_routes")
from dazzle_ui.runtime.page_routes import create_page_routes  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EXAMPLES = _REPO_ROOT / "examples"


class _JinjaSpy:
    """Records every `Template.render` call inside a `with` block."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._original = Template.render

    def __enter__(self) -> _JinjaSpy:
        spy = self
        original = self._original

        def tracked(self_template: Template, *args: object, **kwargs: object) -> str:
            name = getattr(self_template, "name", None) or "<inline>"
            spy.calls.append(name)
            return original(self_template, *args, **kwargs)

        self._patch = patch.object(Template, "render", tracked)
        self._patch.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._patch.stop()


def _client_for(example: str, *, chrome: bool) -> tuple[TestClient, FastAPI]:
    from dazzle_back.runtime.renderers.init import register_default_renderers
    from dazzle_back.runtime.services import RuntimeServices

    appspec = load_project_appspec(_EXAMPLES / example)
    fastapi_app = FastAPI()
    services = RuntimeServices()
    register_default_renderers(services)
    fastapi_app.state.services = services
    fastapi_app.state.fragment_chrome = chrome
    fastapi_app.include_router(create_page_routes(appspec, backend_url="http://127.0.0.1:9999"))
    return TestClient(fastapi_app), fastapi_app


def _workspace_routes(app: FastAPI) -> list[str]:
    """Return the GET workspace routes from the registered app
    (the routes under `/app/workspaces/...` or however the example
    declares them — workspace prefix is convention-dependent)."""
    out: list[str] = []
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        methods = getattr(route, "methods", None) or set()
        if "GET" not in methods:
            continue
        # workspace_renderer registers under /app/workspaces/* OR the
        # workspace's nav route — both shapes count.
        if "workspace" in path or "/app/" in path:
            out.append(path)
    return out


def test_workspace_full_page_renders_zero_jinja_when_chrome_on() -> None:
    """The full-page workspace render path (no `HX-Request` header)
    must produce zero Jinja Template.render() invocations under
    chrome=on. Closes the gap from #1036."""
    client, app = _client_for("simple_task", chrome=True)
    workspace_paths = _workspace_routes(app)
    if not workspace_paths:
        pytest.skip("simple_task has no workspace routes registered in this build")

    failures: list[tuple[str, list[str]]] = []
    for path in workspace_paths:
        with _JinjaSpy() as spy:
            resp = client.get(path, follow_redirects=False)
        # Any 200 must come from the typed substrate; auth redirects
        # / 404s are acceptable (no template render attempted).
        if resp.status_code == 200 and spy.calls:
            failures.append((path, sorted(set(spy.calls))))
    assert not failures, (
        "Jinja templates rendered for workspace routes under chrome=on:\n"
        + "\n".join(f"  {p}: {tmpls!r}" for p, tmpls in failures)
    )


def test_workspace_htmx_partial_renders_zero_jinja_when_chrome_on() -> None:
    """htmx wants_fragment requests against workspace routes also
    flip to the typed substrate when chrome=on. Pre-fix this path
    was gated on `DAZZLE_TYPED_RENDER=1`; #1036 unifies the signal
    on `app.state.fragment_chrome`."""
    client, app = _client_for("simple_task", chrome=True)
    workspace_paths = _workspace_routes(app)
    if not workspace_paths:
        pytest.skip("simple_task has no workspace routes registered in this build")

    failures: list[tuple[str, list[str]]] = []
    for path in workspace_paths:
        with _JinjaSpy() as spy:
            resp = client.get(path, headers={"HX-Request": "true"}, follow_redirects=False)
        if resp.status_code == 200 and spy.calls:
            failures.append((path, sorted(set(spy.calls))))
    assert not failures, (
        "Jinja templates rendered for workspace HTMX partials under chrome=on:\n"
        + "\n".join(f"  {p}: {tmpls!r}" for p, tmpls in failures)
    )


def test_workspace_full_page_uses_dispatch_render_page_when_chrome_on() -> None:
    """Direct seam check: the workspace handler should call
    `dispatch_render_page` (the typed-substrate seam).

    Phase 4 app-shell migration (v0.67.44): the chrome flag is no
    longer consulted. The handler unconditionally routes through
    dispatch_render_page — there is no Jinja workspace.html fallback
    anymore. The test now just pins the typed seam is present.
    """
    from dazzle_ui.runtime import page_routes as pr_mod

    handler_src = (Path(pr_mod.__file__)).read_text(encoding="utf-8")
    assert "dispatch_render_page" in handler_src, (
        "page_routes.py no longer references dispatch_render_page — the "
        "typed workspace chrome path may have been removed."
    )
    # The legacy `workspace/workspace.html` template was retired with
    # the chrome-flag removal; assert no reference creeps back in.
    assert "workspace/workspace.html" not in handler_src, (
        "page_routes.py reintroduced workspace/workspace.html — that "
        "template was retired in Phase 4 (v0.67.44). The typed-Fragment "
        "workspace render is the only path now."
    )
    # Phase 4 (v0.67.44): the workspace handler no longer reads
    # `app.state.fragment_chrome` for the typed-vs-Jinja decision;
    # typed-Fragment is the only path. Asset / theme overrides still
    # thread through `app.state.fragment_chrome_*` state attributes
    # (per-deployment branding, not a render-mode toggle).
