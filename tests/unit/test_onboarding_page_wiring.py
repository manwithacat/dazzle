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

from dazzle.render.context import FieldContext, FormContext, PageContext
from dazzle.ui.runtime.page_routes import _inject_onboarding_step
from dazzle.ui.runtime.template_renderer import _render_typed_body

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
