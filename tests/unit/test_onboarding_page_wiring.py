"""Tests for the page-routes onboarding wiring (v0.71.3).

Three layers to pin:

1. ``PageContext.active_guide_html`` exists as a settable field.
2. ``_render_typed_body`` prepends ``active_guide_html`` to the
   rendered surface body. Empty string = unchanged output.
3. ``_inject_onboarding_step`` no-ops cleanly under each of the
   skip conditions (no guides / anonymous / no repo / no
   resolver match / unsupported kind) and populates the field on
   the happy path.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dazzle.core import ir
from dazzle.http.runtime import page_routes
from dazzle.http.runtime.page_routes import (
    _inject_onboarding_step,
    _suppress_inaccessible_cta,
)
from dazzle.page.runtime.template_renderer import _render_typed_body
from dazzle.render.context import PageContext

# ---------------------------------------------------------------------------
# PageContext field
# ---------------------------------------------------------------------------


# One contract: ``active_guide_html`` is a PageContext field that defaults
# to "" and accepts a constructor value.
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        pytest.param({}, "", id="defaults-empty"),
        pytest.param(
            {"active_guide_html": "<dz-onboarding-step/>"},
            "<dz-onboarding-step/>",
            id="settable-via-constructor",
        ),
    ],
)
def test_page_context_active_guide_html(kwargs: dict[str, str], expected: str) -> None:
    ctx = PageContext(page_title="x", **kwargs)
    assert ctx.active_guide_html == expected


# ---------------------------------------------------------------------------
# _render_typed_body prepend behaviour
# ---------------------------------------------------------------------------


# ADR-0049 Phase 3b: list/detail/form bodies render via the substrate dispatch
# now (where the guide overlay is prepended by `_maybe_dispatch_inner_html`'s
# `_compose`). `_render_typed_body` raises for those modes, so these tests
# exercise its overlay-prepend on an empty-body ctx — the prepend is plain
# `overlay + body` concatenation, independent of the body's mode. One
# contract: with an empty body the output is exactly the overlay ("" =
# unchanged output).
@pytest.mark.parametrize(
    "overlay",
    [
        pytest.param('<dz-onboarding-step data-step="welcome"/>', id="prepends-overlay"),
        pytest.param("", id="unchanged-when-overlay-empty"),
    ],
)
def test_render_typed_body_overlay_prepend(overlay: str) -> None:
    ctx = PageContext(page_title="x", layout="single_column", active_guide_html=overlay)
    assert _render_typed_body(ctx) == overlay


# ---------------------------------------------------------------------------
# _inject_onboarding_step skip conditions
# ---------------------------------------------------------------------------


def _prc(
    *,
    guides: list = None,
    is_authenticated: bool = True,
    user_id: str | None = "u1",
    user_roles: list[str] = None,
    view_name: str = "task_list",
    repo: object | None = None,
):
    """Build a _PageRequestContext-shaped namespace for the helper to read."""
    user = SimpleNamespace(
        id=user_id, email="u@x", username="u", roles=user_roles or ["role_admin"]
    )
    auth_ctx = SimpleNamespace(is_authenticated=is_authenticated, user=user)
    deps = SimpleNamespace(appspec=SimpleNamespace(guides=guides or []))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    if repo is not None:
        request.app.state.onboarding_state = repo
    ctx = PageContext(page_title="x", view_name=view_name)
    return SimpleNamespace(deps=deps, auth_ctx=auth_ctx, request=request, ctx=ctx)


def _welcome_guide(
    *,
    name: str = "g",
    audience: str = "persona = admin",
    step_name: str = "welcome",
) -> ir.GuideSpec:
    """A real one-popover-step IR guide targeting surface.task_list."""
    step = ir.GuideStep(
        name=step_name,
        kind=ir.GuideStepKind.POPOVER,
        title="Welcome",
        body="Get started",
        target="surface.task_list",
        complete_on=ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK),
    )
    return ir.GuideSpec(
        name=name,
        title=name,
        audience=audience,
        steps=[step],
        step_order=[step_name],
    )


def _repo(*, error: bool = False) -> MagicMock:
    """Onboarding-state repo stub: no progress rows, or a raising ``get()``."""
    repo = MagicMock()
    repo.get = MagicMock(
        side_effect=RuntimeError("postgres down") if error else None,
        return_value=None,
    )
    return repo


# One contract: under every skip condition the injector no-ops cleanly and
# the overlay stays empty.
@pytest.mark.parametrize(
    "prc_kwargs",
    [
        pytest.param({"guides": []}, id="no-guides"),
        pytest.param({"guides": [MagicMock()], "is_authenticated": False}, id="anonymous"),
        pytest.param({"guides": [MagicMock()], "repo": None}, id="no-repo"),
        pytest.param(
            {"guides": [MagicMock()], "repo": MagicMock(), "view_name": ""},
            id="no-view-name",
        ),
    ],
)
def test_inject_noops_under_skip_condition(prc_kwargs: dict) -> None:
    prc = _prc(**prc_kwargs)
    _inject_onboarding_step(prc)
    assert prc.ctx.active_guide_html == ""


def test_inject_renders_popover_on_happy_path() -> None:
    """Real IR fixture + mocked repo → active_guide_html is populated."""
    prc = _prc(
        guides=[_welcome_guide(name="workspace_setup")],
        repo=_repo(),
        user_roles=["role_admin"],
        view_name="task_list",
    )
    _inject_onboarding_step(prc)
    assert "<dz-onboarding-step" in prc.ctx.active_guide_html
    assert 'data-guide="workspace_setup"' in prc.ctx.active_guide_html
    assert 'data-step="welcome"' in prc.ctx.active_guide_html


def test_inject_resets_stale_overlay_across_personas() -> None:
    """#1293: the page ctx is captured once per route in
    ``_make_page_handler``'s closure and shared across requests. An overlay
    set for one persona must NOT persist into the next persona's request —
    else an engineer's "Register Device" empty-state CTA bleeds onto a tester
    who can't create Devices (the fieldtest_hub ``rbac:Device:tester:create``
    contract failure). The injector must reset the overlay every request,
    like ``_apply_anon_nav`` does for ``nav_items``."""
    # Audience matches admin only — a tester's resolve returns None.
    guide = _welcome_guide(name="workspace_setup", audience="persona = admin")
    repo = _repo()

    # Request 1 — admin: guide resolves, overlay is populated on the ctx.
    prc_admin = _prc(guides=[guide], repo=repo, user_roles=["role_admin"], view_name="task_list")
    _inject_onboarding_step(prc_admin)
    assert "<dz-onboarding-step" in prc_admin.ctx.active_guide_html

    # Request 2 — a DIFFERENT persona hitting the SAME shared ctx object
    # (the closure-captured per-route ctx). The guide's audience doesn't
    # match, so resolve returns None. Pre-fix the admin overlay persisted on
    # the shared ctx and rendered for this user; the reset must clear it.
    prc_tester = _prc(guides=[guide], repo=repo, user_roles=["role_tester"], view_name="task_list")
    prc_tester.ctx = prc_admin.ctx  # simulate the shared per-route ctx
    _inject_onboarding_step(prc_tester)
    assert prc_tester.ctx.active_guide_html == "", (
        "stale overlay from the admin request bled into the tester request "
        "via the shared per-route ctx (#1293)"
    )


def test_inject_skips_unsupported_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    """A guide with a kind the current Dazzle release doesn't render
    must NOT crash the page — overlay stays empty. v0.71.5 ships all
    eight defined kinds, so this test simulates a future kind by
    monkey-patching the has_builder check."""
    from dazzle.render.onboarding import renderer as renderer_module

    # Pretend this kind isn't shipped — exercises the has_builder
    # bail-out branch in _inject_onboarding_step.
    monkeypatch.setattr(renderer_module, "_SUPPORTED_KINDS", frozenset())

    prc = _prc(guides=[_welcome_guide(step_name="future")], repo=_repo(), view_name="task_list")
    _inject_onboarding_step(prc)
    assert prc.ctx.active_guide_html == ""


def test_inject_swallows_repository_errors() -> None:
    prc = _prc(guides=[_welcome_guide()], repo=_repo(error=True), view_name="task_list")
    _inject_onboarding_step(prc)  # must not raise
    assert prc.ctx.active_guide_html == ""


# ---------------------------------------------------------------------------
# #1118 — tagged INFO logs at every skip branch. Each `onboarding.inject:`
# tag must be emitted by exactly the branch it names so production-log
# `grep onboarding.inject:` answers "why didn't my guide render?"
# without needing source-level debugging.
# ---------------------------------------------------------------------------


def _capture_logs(caplog, level: str = "INFO") -> list[str]:
    """Return the messages emitted to the page_routes logger at or above
    the given level."""
    caplog.set_level(level, logger="dazzle.http.runtime.page_routes")
    return [r.getMessage() for r in caplog.records if r.name == "dazzle.http.runtime.page_routes"]


# One contract: each skip branch emits exactly the tag that names it.
@pytest.mark.parametrize(
    ("make_prc", "tag"),
    [
        # The most likely production skip path — guides declared, user
        # authenticated, but `app.state.onboarding_state` is None because
        # AuthSubsystem.startup didn't wire it. Was silent before #1118.
        pytest.param(
            lambda: _prc(guides=[MagicMock()], repo=None),
            "onboarding.inject:no-repo",
            id="no-repo",
        ),
        pytest.param(
            lambda: _prc(guides=[MagicMock()], is_authenticated=False),
            "onboarding.inject:not-authenticated",
            id="not-authenticated",
        ),
        pytest.param(
            lambda: _prc(guides=[MagicMock()], repo=MagicMock(), view_name=""),
            "onboarding.inject:no-surface-name",
            id="no-surface-name",
        ),
        # Most-likely-cause-once-no-repo-is-ruled-out: resolver returns
        # None because the audience predicate doesn't match, or all steps
        # are already completed/dismissed. Was silent before #1118.
        pytest.param(
            lambda: _prc(
                guides=[_welcome_guide(audience="persona = manager")],
                repo=_repo(),
                view_name="task_list",
                user_roles=["role_admin"],
            ),
            "onboarding.inject:no-active-step",
            id="no-active-step",
        ),
        # Repository errors are non-fatal but must surface at INFO so
        # production can see them (was DEBUG, swallowed by default config).
        pytest.param(
            lambda: _prc(guides=[_welcome_guide()], repo=_repo(error=True), view_name="task_list"),
            "onboarding.inject:resolve-failed",
            id="resolve-failed",
        ),
    ],
)
def test_inject_logs_tagged_skip_branches(
    make_prc: Callable[[], SimpleNamespace], tag: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="dazzle.http.runtime.page_routes")
    prc = make_prc()
    _inject_onboarding_step(prc)
    msgs = _capture_logs(caplog)
    assert any(tag in m for m in msgs), f"expected {tag!r} tag, got: {msgs}"


def test_inject_logs_rendered_on_happy_path(caplog: pytest.LogCaptureFixture) -> None:
    """Success path also emits a tagged log line — operators can grep
    for `onboarding.inject:rendered` to confirm the guide IS firing."""
    caplog.set_level("INFO", logger="dazzle.http.runtime.page_routes")
    prc = _prc(
        guides=[_welcome_guide(name="workspace_setup")],
        repo=_repo(),
        user_roles=["role_admin"],
        view_name="task_list",
    )
    _inject_onboarding_step(prc)
    msgs = _capture_logs(caplog)
    assert any("onboarding.inject:rendered" in m for m in msgs), (
        f"expected 'onboarding.inject:rendered' tag on happy path, got: {msgs}"
    )
    assert any("guide=workspace_setup" in m for m in msgs)
    assert any("step=welcome" in m for m in msgs)


# ---------------------------------------------------------------------------
# #1292 — runtime CTA suppression backstop (_suppress_inaccessible_cta)
# ---------------------------------------------------------------------------


def _cta_step(cta_target: str) -> ir.GuideStep:
    return ir.GuideStep(
        name="register_system",
        kind=ir.GuideStepKind.EMPTY_STATE,
        title="t",
        body="b",
        target="surface.system_list",
        complete_on=ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK),
        cta_label="Register System",
        cta_target=cta_target,
    )


def _appspec_with_surface(name: str, mode: str):
    return SimpleNamespace(surfaces=[SimpleNamespace(name=name, mode=mode, entity_ref="System")])


def _prc_stub():
    return SimpleNamespace(deps=SimpleNamespace(), auth_ctx=SimpleNamespace())


# One contract: a CTA pointing at a mutation surface is stripped when the
# persona can't mutate; otherwise it passes through untouched — including a
# list/view CTA, which is not a mutation affordance and is never gated even
# if _user_can_mutate would deny.
@pytest.mark.parametrize(
    ("can_mutate", "cta_target", "surface_name", "mode", "expected_target"),
    [
        pytest.param(
            False,
            "surface.system_create",
            "system_create",
            "create",
            None,
            id="suppressed-when-persona-cannot-mutate",
        ),
        pytest.param(
            True,
            "surface.system_create",
            "system_create",
            "create",
            "surface.system_create",
            id="preserved-when-persona-can-mutate",
        ),
        pytest.param(
            False,
            "surface.alert_list",
            "alert_list",
            "list",
            "surface.alert_list",
            id="read-cta-never-suppressed",
        ),
    ],
)
def test_cta_suppression(
    monkeypatch: pytest.MonkeyPatch,
    can_mutate: bool,
    cta_target: str,
    surface_name: str,
    mode: str,
    expected_target: str | None,
) -> None:
    monkeypatch.setattr(page_routes, "_user_can_mutate", lambda *a, **k: can_mutate)
    out = _suppress_inaccessible_cta(
        _cta_step(cta_target), _prc_stub(), _appspec_with_surface(surface_name, mode)
    )
    assert out.cta_target == expected_target
    if expected_target is None:
        assert out.cta_label is None
