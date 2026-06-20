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

from types import SimpleNamespace
from unittest.mock import MagicMock

from dazzle.http.runtime.page_routes import _inject_onboarding_step
from dazzle.page.runtime.template_renderer import _render_typed_body
from dazzle.render.context import FieldContext, FormContext, PageContext

# ---------------------------------------------------------------------------
# PageContext field
# ---------------------------------------------------------------------------


def test_page_context_active_guide_html_defaults_empty() -> None:
    ctx = PageContext(page_title="x")
    assert ctx.active_guide_html == ""


def test_page_context_active_guide_html_is_settable() -> None:
    ctx = PageContext(page_title="x", active_guide_html="<dz-onboarding-step/>")
    assert ctx.active_guide_html == "<dz-onboarding-step/>"


# ---------------------------------------------------------------------------
# _render_typed_body prepend behaviour
# ---------------------------------------------------------------------------


def test_render_typed_body_prepends_active_guide_html() -> None:
    form = FormContext(
        entity_name="Widget",
        title="Create Widget",
        fields=[FieldContext(name="title", label="Title", field_type="string")],
        action_url="/api/widgets",
        method="post",
        mode="create",
    )
    ctx = PageContext(
        page_title="Create",
        layout="single_column",
        form=form,
        active_guide_html='<dz-onboarding-step data-step="welcome"/>',
    )
    html = _render_typed_body(ctx)
    assert html.startswith('<dz-onboarding-step data-step="welcome"/>')
    assert "<form " in html  # form body still rendered


def test_render_typed_body_unchanged_when_overlay_empty() -> None:
    form = FormContext(
        entity_name="Widget",
        title="Create Widget",
        fields=[],
        action_url="/api/widgets",
        method="post",
        mode="create",
    )
    ctx = PageContext(page_title="x", layout="single_column", form=form)
    # No overlay set → body comes back un-prepended.
    html = _render_typed_body(ctx)
    assert html.startswith("<form ")


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


def test_inject_noops_when_no_guides() -> None:
    prc = _prc(guides=[])
    _inject_onboarding_step(prc)
    assert prc.ctx.active_guide_html == ""


def test_inject_noops_when_anonymous() -> None:
    prc = _prc(guides=[MagicMock()], is_authenticated=False)
    _inject_onboarding_step(prc)
    assert prc.ctx.active_guide_html == ""


def test_inject_noops_when_no_repo() -> None:
    prc = _prc(guides=[MagicMock()], repo=None)
    _inject_onboarding_step(prc)
    assert prc.ctx.active_guide_html == ""


def test_inject_noops_when_no_view_name() -> None:
    prc = _prc(guides=[MagicMock()], repo=MagicMock(), view_name="")
    _inject_onboarding_step(prc)
    assert prc.ctx.active_guide_html == ""


def test_inject_renders_popover_on_happy_path() -> None:
    """Real IR fixture + mocked repo → active_guide_html is populated."""
    from dazzle.core import ir

    step = ir.GuideStep(
        name="welcome",
        kind=ir.GuideStepKind.POPOVER,
        title="Welcome",
        body="Get started",
        target="surface.task_list",
        complete_on=ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK),
    )
    guide = ir.GuideSpec(
        name="workspace_setup",
        title="Setup",
        audience="persona = admin",
        steps=[step],
        step_order=["welcome"],
    )
    repo = MagicMock()
    repo.get = MagicMock(return_value=None)

    prc = _prc(
        guides=[guide],
        repo=repo,
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
    from dazzle.core import ir

    step = ir.GuideStep(
        name="welcome",
        kind=ir.GuideStepKind.POPOVER,
        title="Welcome",
        body="Get started",
        target="surface.task_list",
        complete_on=ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK),
    )
    # Audience matches admin only — a tester's resolve returns None.
    guide = ir.GuideSpec(
        name="workspace_setup",
        title="Setup",
        audience="persona = admin",
        steps=[step],
        step_order=["welcome"],
    )
    repo = MagicMock()
    repo.get = MagicMock(return_value=None)

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


def test_inject_skips_unsupported_kind(monkeypatch) -> None:
    """A guide with a kind the current Dazzle release doesn't render
    must NOT crash the page — overlay stays empty. v0.71.5 ships all
    eight defined kinds, so this test simulates a future kind by
    monkey-patching the has_builder check."""
    from dazzle.core import ir
    from dazzle.render.onboarding import renderer as renderer_module

    step = ir.GuideStep(
        name="future",
        kind=ir.GuideStepKind.POPOVER,  # real kind for IR validation
        title="x",
        body="y",
        target="surface.task_list",
        complete_on=ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK),
    )
    guide = ir.GuideSpec(
        name="g",
        title="g",
        audience="persona = admin",
        steps=[step],
        step_order=["future"],
    )
    repo = MagicMock()
    repo.get = MagicMock(return_value=None)

    # Pretend this kind isn't shipped — exercises the has_builder
    # bail-out branch in _inject_onboarding_step.
    monkeypatch.setattr(renderer_module, "_SUPPORTED_KINDS", frozenset())

    prc = _prc(guides=[guide], repo=repo, view_name="task_list")
    _inject_onboarding_step(prc)
    assert prc.ctx.active_guide_html == ""


def test_inject_swallows_repository_errors() -> None:
    from dazzle.core import ir

    step = ir.GuideStep(
        name="welcome",
        kind=ir.GuideStepKind.POPOVER,
        title="x",
        body="y",
        target="surface.task_list",
        complete_on=ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK),
    )
    guide = ir.GuideSpec(
        name="g",
        title="g",
        audience="persona = admin",
        steps=[step],
        step_order=["welcome"],
    )
    repo = MagicMock()
    repo.get = MagicMock(side_effect=RuntimeError("postgres down"))

    prc = _prc(guides=[guide], repo=repo, view_name="task_list")
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


def test_inject_logs_no_repo_branch(caplog) -> None:
    """The most likely production skip path — guides declared, user
    authenticated, but `app.state.onboarding_state` is None because
    AuthSubsystem.startup didn't wire it. Was silent before #1118."""
    caplog.set_level("INFO", logger="dazzle.http.runtime.page_routes")
    prc = _prc(guides=[MagicMock()], repo=None)
    _inject_onboarding_step(prc)
    msgs = _capture_logs(caplog)
    assert any("onboarding.inject:no-repo" in m for m in msgs), (
        f"expected 'onboarding.inject:no-repo' tag, got: {msgs}"
    )


def test_inject_logs_not_authenticated_branch(caplog) -> None:
    caplog.set_level("INFO", logger="dazzle.http.runtime.page_routes")
    prc = _prc(guides=[MagicMock()], is_authenticated=False)
    _inject_onboarding_step(prc)
    msgs = _capture_logs(caplog)
    assert any("onboarding.inject:not-authenticated" in m for m in msgs), (
        f"expected 'onboarding.inject:not-authenticated' tag, got: {msgs}"
    )


def test_inject_logs_no_surface_name_branch(caplog) -> None:
    caplog.set_level("INFO", logger="dazzle.http.runtime.page_routes")
    prc = _prc(guides=[MagicMock()], repo=MagicMock(), view_name="")
    _inject_onboarding_step(prc)
    msgs = _capture_logs(caplog)
    assert any("onboarding.inject:no-surface-name" in m for m in msgs), (
        f"expected 'onboarding.inject:no-surface-name' tag, got: {msgs}"
    )


def test_inject_logs_no_active_step_branch(caplog) -> None:
    """Most-likely-cause-once-no-repo-is-ruled-out: resolver returns
    None because the audience predicate doesn't match, or all steps
    are already completed/dismissed. Was silent before #1118."""
    from dazzle.core import ir

    step = ir.GuideStep(
        name="welcome",
        kind=ir.GuideStepKind.POPOVER,
        title="x",
        body="y",
        target="surface.task_list",
        complete_on=ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK),
    )
    guide = ir.GuideSpec(
        name="g",
        title="g",
        # Audience predicate intentionally mismatches the user's role
        # so the resolver returns None.
        audience="persona = manager",
        steps=[step],
        step_order=["welcome"],
    )
    repo = MagicMock()
    repo.get = MagicMock(return_value=None)

    caplog.set_level("INFO", logger="dazzle.http.runtime.page_routes")
    prc = _prc(guides=[guide], repo=repo, view_name="task_list", user_roles=["role_admin"])
    _inject_onboarding_step(prc)
    msgs = _capture_logs(caplog)
    assert any("onboarding.inject:no-active-step" in m for m in msgs), (
        f"expected 'onboarding.inject:no-active-step' tag, got: {msgs}"
    )


def test_inject_logs_resolve_failed_branch_at_info_level(caplog) -> None:
    """Repository errors are non-fatal but must surface at INFO so
    production can see them (was DEBUG, swallowed by default config)."""
    from dazzle.core import ir

    step = ir.GuideStep(
        name="welcome",
        kind=ir.GuideStepKind.POPOVER,
        title="x",
        body="y",
        target="surface.task_list",
        complete_on=ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK),
    )
    guide = ir.GuideSpec(
        name="g",
        title="g",
        audience="persona = admin",
        steps=[step],
        step_order=["welcome"],
    )
    repo = MagicMock()
    repo.get = MagicMock(side_effect=RuntimeError("postgres down"))

    caplog.set_level("INFO", logger="dazzle.http.runtime.page_routes")
    prc = _prc(guides=[guide], repo=repo, view_name="task_list")
    _inject_onboarding_step(prc)
    msgs = _capture_logs(caplog)
    assert any("onboarding.inject:resolve-failed" in m for m in msgs), (
        f"expected 'onboarding.inject:resolve-failed' tag, got: {msgs}"
    )


def test_inject_logs_rendered_on_happy_path(caplog) -> None:
    """Success path also emits a tagged log line — operators can grep
    for `onboarding.inject:rendered` to confirm the guide IS firing."""
    from dazzle.core import ir

    step = ir.GuideStep(
        name="welcome",
        kind=ir.GuideStepKind.POPOVER,
        title="Welcome",
        body="Get started",
        target="surface.task_list",
        complete_on=ir.GuideCompleteOn(kind=ir.GuideCompleteOnKind.CLICK),
    )
    guide = ir.GuideSpec(
        name="workspace_setup",
        title="Setup",
        audience="persona = admin",
        steps=[step],
        step_order=["welcome"],
    )
    repo = MagicMock()
    repo.get = MagicMock(return_value=None)

    caplog.set_level("INFO", logger="dazzle.http.runtime.page_routes")
    prc = _prc(guides=[guide], repo=repo, user_roles=["role_admin"], view_name="task_list")
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

from dazzle.core import ir  # noqa: E402
from dazzle.http.runtime import page_routes  # noqa: E402
from dazzle.http.runtime.page_routes import _suppress_inaccessible_cta  # noqa: E402


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


def test_cta_suppressed_when_persona_cannot_mutate(monkeypatch) -> None:
    monkeypatch.setattr(page_routes, "_user_can_mutate", lambda *a, **k: False)
    out = _suppress_inaccessible_cta(
        _cta_step("surface.system_create"),
        _prc_stub(),
        _appspec_with_surface("system_create", "create"),
    )
    assert out.cta_target is None
    assert out.cta_label is None


def test_cta_preserved_when_persona_can_mutate(monkeypatch) -> None:
    monkeypatch.setattr(page_routes, "_user_can_mutate", lambda *a, **k: True)
    out = _suppress_inaccessible_cta(
        _cta_step("surface.system_create"),
        _prc_stub(),
        _appspec_with_surface("system_create", "create"),
    )
    assert out.cta_target == "surface.system_create"


def test_read_cta_never_suppressed(monkeypatch) -> None:
    # A list/view CTA is not a mutation affordance — never gated, even if
    # _user_can_mutate would deny.
    monkeypatch.setattr(page_routes, "_user_can_mutate", lambda *a, **k: False)
    out = _suppress_inaccessible_cta(
        _cta_step("surface.alert_list"), _prc_stub(), _appspec_with_surface("alert_list", "list")
    )
    assert out.cta_target == "surface.alert_list"
