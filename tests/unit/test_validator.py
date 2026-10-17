"""Semantic validator contract: one table row per diagnostic.

Each row builds an AppSpec, runs one validator and asserts whether a message
on the named channel (``errors`` / ``warnings`` / ``all``) contains every
fragment. ``fragments=()`` with ``present=False`` means "the channel is empty"
— that is how the clean-spec rows are written.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from dazzle.core import ir
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import (
    extended_lint,
    validate_entities,
    validate_experiences,
    validate_foreign_models,
    validate_integrations,
    validate_nav_curation,
    validate_persona_nav_refs,
    validate_services,
    validate_surfaces,
    validate_ux_specs,
    validate_workspace_primary_actions,
    validate_workspace_region_actions,
)

K = ir.FieldTypeKind


# =============================================================================
# Builders
# =============================================================================


def _f(
    name: str, kind: ir.FieldTypeKind, *modifiers: ir.FieldModifier, **type_kw: Any
) -> ir.FieldSpec:
    return ir.FieldSpec(
        name=name, type=ir.FieldType(kind=kind, **type_kw), modifiers=list(modifiers)
    )


def _id() -> ir.FieldSpec:
    return _f("id", K.UUID, ir.FieldModifier.PK)


def _ref(name: str, entity: str) -> ir.FieldSpec:
    return _f(name, K.REF, ref_entity=entity)


def _entity(name: str = "Task", *fields: ir.FieldSpec, **kw: Any) -> ir.EntitySpec:
    kw.setdefault("title", "A task item")
    return ir.EntitySpec(name=name, fields=[_id(), *fields], **kw)


def _list_surface(
    name: str = "task_list", entity: str | None = "Task", **kw: Any
) -> ir.SurfaceSpec:
    kw.setdefault("mode", ir.SurfaceMode.LIST)
    kw.setdefault("sections", [])
    return ir.SurfaceSpec(name=name, title=name.title(), entity_ref=entity, **kw)


def _workspace(
    *regions: ir.WorkspaceRegion, name: str = "dashboard", **kw: Any
) -> ir.WorkspaceSpec:
    return ir.WorkspaceSpec(name=name, title=name.title(), regions=list(regions), **kw)


def _spec(*entities: ir.EntitySpec, **kw: Any) -> ir.AppSpec:
    return ir.AppSpec(name="Test", domain=ir.DomainSpec(entities=list(entities)), **kw)


def _permit_read() -> ir.AccessSpec:
    return ir.AccessSpec(
        permissions=[
            ir.PermissionRule(
                operation=ir.PermissionKind.READ, require_auth=True, effect=ir.PolicyEffect.PERMIT
            )
        ]
    )


def _api(spec_url: str | None, auth: ir.AuthKind = ir.AuthKind.API_KEY_HEADER) -> ir.APISpec:
    return ir.APISpec(
        name="github",
        title="GitHub API",
        spec_url=spec_url,
        spec_inline=None,
        auth_profile=ir.AuthProfile(kind=auth, options={}),
    )


def _foreign(key_fields: list[str], *names: str) -> ir.ForeignModelSpec:
    return ir.ForeignModelSpec(
        name="GitHubUser",
        title="GitHub User",
        api_ref="github",
        key_fields=key_fields,
        fields=[_f(n, K.INT) for n in names],
        constraints=[],
    )


def _step(name: str, surface: str | None, *next_steps: str) -> ir.ExperienceStep:
    return ir.ExperienceStep(
        name=name,
        kind=ir.StepKind.SURFACE,
        surface=surface,
        transitions=[
            ir.StepTransition(event=ir.TransitionEvent.SUCCESS, next_step=n) for n in next_steps
        ],
    )


def _experience(*steps: ir.ExperienceStep, start: str = "step1") -> ir.ExperienceSpec:
    return ir.ExperienceSpec(name="flow", title="Flow", start_step=start, steps=list(steps))


def _filter_region(source: str, field: str) -> ir.WorkspaceRegion:
    return ir.WorkspaceRegion(
        name="rows",
        source=source,
        filter=ir.ConditionExpr(
            comparison=ir.Comparison(
                field=field,
                operator=ir.ComparisonOperator.EQUALS,
                value=ir.ConditionValue(literal="x"),
            )
        ),
    )


def _fk_chain_spec(field: str) -> ir.AppSpec:
    """Version → mark_scheme → subject → department, plus Task(title: str)."""
    return _spec(
        _entity("Department"),
        _entity("Subject", _ref("department", "Department")),
        _entity("MarkScheme", _ref("subject", "Subject")),
        _entity("MarkSchemeVersion", _ref("mark_scheme", "MarkScheme")),
        _entity("Task", _f("title", K.STR)),
        workspaces=[_workspace(_filter_region("MarkSchemeVersion", field), name="hub")],
    )


def _primary_actions_spec(*actions: tuple[str, str]) -> ir.AppSpec:
    ws = ir.WorkspaceSpec(
        name="reports",
        primary_actions=[
            ir.WorkspacePrimaryActionSpec(label=t, target_kind=k, target=t) for k, t in actions
        ],
    )
    return _spec(
        surfaces=[
            ir.SurfaceSpec(name="create_invoice", mode=ir.SurfaceMode.CREATE, entity_ref="Invoice")
        ],
        workspaces=[ws, ir.WorkspaceSpec(name="ops_dashboard")],
    )


def _nav(name: str, *items: str, group_when: Any = None, item_when: Any = None) -> ir.NavSpec:
    return ir.NavSpec(
        name=name,
        groups=[
            ir.NavGroupSpec(
                label="Main",
                when=group_when,
                items=[ir.NavItemIR(entity=i, when=item_when) for i in items],
            )
        ],
    )


def _persona(nav_ref: str | None = None) -> ir.PersonaSpec:
    return ir.PersonaSpec(id="teacher", label="Teacher", nav_ref=nav_ref)


def _tenant_flag(key: str) -> ir.ConditionExpr:
    """A bare ``tenant_config.<key>`` flag, as parse_condition_expr emits it."""
    return ir.ConditionExpr(
        comparison=ir.Comparison(
            field=f"tenant_config.{key}",
            operator=ir.ComparisonOperator.EQUALS,
            value=ir.ConditionValue(literal=True),
        )
    )


def _nav_when_spec(declared: dict[str, str] | None, **when: Any) -> ir.AppSpec:
    return _spec(
        _entity("Task"),
        personas=[ir.PersonaSpec(id="member", label="Member", nav_ref="membernav")],
        navs=[_nav("membernav", "Task", **when)],
        tenancy=ir.TenancySpec(per_tenant_config=declared) if declared is not None else None,
    )


def _nav_groups_ws(name: str) -> ir.AppSpec:
    group = ir.NavGroupSpec(label="Main", items=[ir.NavItemIR(entity="Task")])
    return _spec(workspaces=[ir.WorkspaceSpec(name=name, nav_groups=[group])])


# =============================================================================
# Diagnostic table
# =============================================================================


def _case(
    validator: Callable[[ir.AppSpec], Any],
    build: Callable[[], ir.AppSpec],
    channel: str,
    fragments: tuple[str, ...],
    present: bool,
    id: str,
) -> Any:
    return pytest.param(validator, build, channel, fragments, present, id=id)


def _clean(validator: Callable[[ir.AppSpec], Any], build: Callable[[], ir.AppSpec], id: str) -> Any:
    return _case(validator, build, "errors", (), False, id)


VE, VS, VX = validate_entities, validate_surfaces, validate_experiences
LINT = extended_lint
NAV = validate_nav_curation
_DEAD = "Dead construct"

DIAGNOSTIC_CASES = [
    # --- entities ---------------------------------------------------------
    _case(VE, lambda: _spec(_entity("Task", _f("title", K.STR, max_length=200))), "all", (), False,
          "entity-valid-no-diagnostics"),
    _case(VE, lambda: _spec(ir.EntitySpec(name="Task", title="T", fields=[_f("title", K.STR, max_length=200)])),
          "errors", ("no primary key",), True, "entity-missing-pk"),
    _case(VE, lambda: _spec(_entity("Task", _f("status", K.ENUM, enum_values=[]))),
          "errors", ("enum type but no values",), True, "enum-without-values"),
    _case(VE, lambda: _spec(_entity("Task", _f("amount", K.DECIMAL))),
          "errors", ("missing precision/scale",), True, "decimal-without-precision"),
    _case(VE, lambda: _spec(_entity("Task", _f("amount", K.DECIMAL, precision=5, scale=10))),
          "errors", ("scale", "precision"), True, "decimal-scale-greater-than-precision"),
    _case(VE, lambda: _spec(_entity("Task", _f("title", K.STR))),
          "errors", ("no max_length",), True, "str-without-max-length"),
    _case(VE, lambda: _spec(_entity("Task", _f("description", K.STR, max_length=20000))),
          "warnings", ("Consider using 'text' type",), True, "str-very-large-max-length-suggests-text"),
    _case(VE, lambda: _spec(_entity("Task", _f("title", K.STR, max_length=200), _f("title", K.TEXT))),
          "errors", ("duplicate field names",), True, "duplicate-field-names"),
    _case(VE, lambda: _spec(_entity("Task", _f("title", K.STR, ir.FieldModifier.REQUIRED,
                                               ir.FieldModifier.OPTIONAL, max_length=200))),
          "errors", ("required", "optional"), True, "conflicting-required-optional"),
    _case(VE, lambda: _spec(_entity("Task", _f("counter", K.INT, ir.FieldModifier.AUTO_ADD))),
          "warnings", ("auto_add",), True, "auto-add-on-non-datetime"),
    _case(VE, lambda: _spec(_entity("Task", constraints=[
              ir.Constraint(kind=ir.ConstraintKind.UNIQUE, fields=["nonexistent_field"])])),
          "errors", ("nonexistent_field",), True, "constraint-on-unknown-field"),
    _case(VE, lambda: _spec(_entity("Select")),
          "warnings", ("SQL reserved word", "Select"), True, "sql-reserved-entity-name-warns"),
    _case(VE, lambda: _spec(_entity("Select")), "errors", (), False, "sql-reserved-name-is-not-an-error"),
    _case(VE, lambda: _spec(_entity("Task", _f("delete", K.INT))),
          "warnings", ("SQL reserved word", "delete"), True, "sql-reserved-field-name-warns"),
    _case(VE, lambda: _spec(_entity("Task", access=_permit_read())),
          "warnings", ("no scope: blocks",), True, "permit-without-scope-warns"),
    _case(VE, lambda: _spec(_entity("AIJob", patterns=["system", "audit"], access=_permit_read())),
          "warnings", ("no scope: blocks",), False, "system-entity-skips-scope-warning"),
    # --- surfaces ---------------------------------------------------------
    _clean(VS, lambda: _spec(_entity("Task", _f("title", K.STR, max_length=200)), surfaces=[
               _list_surface(sections=[ir.SurfaceSection(name="main", elements=[
                   ir.SurfaceElement(field_name="title", label="Title")])])]),
           "surface-valid"),
    _case(VS, lambda: _spec(_entity("Task"), surfaces=[
              _list_surface(sections=[ir.SurfaceSection(name="main", elements=[
                  ir.SurfaceElement(field_name="nonexistent_field", label="T")])])]),
          "errors", ("nonexistent_field",), True, "surface-unknown-field"),
    _case(VS, lambda: _spec(_entity("Task"), surfaces=[_list_surface()]),
          "warnings", ("no sections",), True, "surface-without-sections-warns"),
    _case(VS, lambda: _spec(surfaces=[_list_surface("task_create", None, mode=ir.SurfaceMode.CREATE)]),
          "warnings", ("create", "no entity reference"), True, "create-surface-without-entity-warns"),
    # --- experiences ------------------------------------------------------
    _clean(VX, lambda: _spec(experiences=[_experience(_step("step1", "welcome", "step2"),
                                                      _step("step2", "done"))]),
           "experience-valid"),
    _case(VX, lambda: _spec(experiences=[_experience(start="nowhere")]),
          "errors", ("no steps",), True, "experience-without-steps"),
    _case(VX, lambda: _spec(experiences=[_experience(_step("step1", None))]),
          "errors", ("no surface or entity target",), True, "surface-step-without-surface"),
    _case(VX, lambda: _spec(experiences=[_experience(_step("step1", "p1"), _step("step2", "p2"))]),
          "warnings", ("has unreachable steps", "step2"), True, "experience-unreachable-step-warns"),
    # --- services / foreign models / integrations -------------------------
    _clean(validate_services, lambda: _spec(apis=[_api("https://api.github.com/openapi.yaml")]),
           "service-valid"),
    _case(validate_services, lambda: _spec(apis=[_api(None)]),
          "errors", ("no spec",), True, "service-without-spec"),
    _case(validate_services, lambda: _spec(apis=[_api("not-a-valid-url")]),
          "warnings", ("invalid spec URL",), True, "service-invalid-spec-url-warns"),
    _case(validate_services, lambda: _spec(apis=[_api("https://x.test/o.yaml", ir.AuthKind.OAUTH2_PKCE)]),
          "warnings", ("scopes",), True, "oauth2-without-scopes-warns"),
    _clean(validate_foreign_models, lambda: _spec(foreign_models=[_foreign(["id"], "id", "login")]),
           "foreign-model-valid"),
    _case(validate_foreign_models, lambda: _spec(foreign_models=[_foreign([], "login")]),
          "errors", ("no key fields",), True, "foreign-model-without-key"),
    _case(validate_foreign_models, lambda: _spec(foreign_models=[_foreign(["nonexistent_id"], "login")]),
          "errors", ("nonexistent_id", "not defined"), True, "foreign-model-key-not-defined"),
    _case(validate_integrations, lambda: _spec(integrations=[ir.IntegrationSpec(name="s", title="S")]),
          "warnings", ("doesn't use any APIs",), True, "integration-without-apis-warns"),
    _case(validate_integrations,
          lambda: _spec(integrations=[ir.IntegrationSpec(name="s", title="S", api_refs=["github"])]),
          "warnings", ("no actions, syncs, or mappings",), True, "integration-without-actions-warns"),
    # --- extended lint: naming, titles ------------------------------------
    _case(LINT, lambda: _spec(_entity("task")), "warnings", ("PascalCase",), True,
          "entity-name-not-pascal-case-warns"),
    _case(LINT, lambda: _spec(_entity("Task", title=None)), "warnings", ("no title",), True,
          "entity-without-title-warns"),
    # --- extended lint: dead constructs -----------------------------------
    _case(LINT, lambda: _spec(_entity("Task"), _entity("Orphan"), surfaces=[_list_surface()]),
          "warnings", ("Dead construct: entity 'Orphan'",), True, "orphan-entity-is-dead"),
    _case(LINT, lambda: _spec(_entity("Task"), surfaces=[_list_surface("orphan_view")]),
          "warnings", ("Dead construct: surface 'orphan_view'",), True, "unreferenced-surface-is-dead"),
    _case(LINT, lambda: _spec(_entity("Orphan1"), _entity("Orphan2"),
                              surfaces=[_list_surface("dead_view", "Orphan1")]),
          "warnings", (_DEAD, "entity 'Orphan2'"), True, "several-dead-all-reported-entity"),
    _case(LINT, lambda: _spec(_entity("Orphan1"), _entity("Orphan2"),
                              surfaces=[_list_surface("dead_view", "Orphan1")]),
          "warnings", (_DEAD, "surface 'dead_view'"), True, "several-dead-all-reported-surface"),
    _case(LINT, lambda: _spec(_entity("Task"), surfaces=[_list_surface()]),
          "warnings", ("entity 'Task'",), False, "entity-used-by-surface-is-live"),
    _case(LINT, lambda: _spec(_entity("Task", _ref("assigned_to", "User")), _entity("User")),
          "warnings", ("entity 'User'",), False, "entity-used-by-ref-field-is-live"),
    _case(LINT, lambda: _spec(_entity("Alert"), workspaces=[
              _workspace(ir.WorkspaceRegion(name="alerts", source="Alert"))]),
          "warnings", ("entity 'Alert'",), False, "entity-used-by-workspace-source-is-live"),
    _case(LINT, lambda: _spec(_entity("Order"), processes=[ir.ProcessSpec(
              name="order_flow", steps=[], trigger=ir.ProcessTriggerSpec(
                  kind=ir.ProcessTriggerKind.ENTITY_EVENT, entity_name="Order", event_type="created"))]),
          "warnings", ("entity 'Order'",), False, "entity-used-by-process-trigger-is-live"),
    _case(LINT, lambda: _spec(_entity("Task"), surfaces=[_list_surface("task_edit")], workspaces=[
              _workspace(ir.WorkspaceRegion(name="tasks", source="Task", action="task_edit"))]),
          "warnings", ("surface 'task_edit'",), False, "surface-used-by-region-action-is-live"),
    _case(LINT, lambda: _spec(_entity("Task"), surfaces=[_list_surface("welcome")],
                              experiences=[_experience(_step("step1", "welcome"))]),
          "warnings", ("surface 'welcome'",), False, "surface-used-by-experience-step-is-live"),
    _case(LINT, lambda: _spec(_entity("Task"), surfaces=[_list_surface("approval_form")],
                              processes=[ir.ProcessSpec(name="approval_flow", steps=[ir.ProcessStepSpec(
                                  name="approve", kind=ir.ProcessStepKind.HUMAN_TASK,
                                  human_task=ir.HumanTaskSpec(surface="approval_form"))])]),
          "warnings", ("surface 'approval_form'",), False, "surface-used-by-human-task-is-live"),
    _case(LINT, lambda: _spec(_entity("Task"), surfaces=[_list_surface()], workspaces=[
              _workspace(ir.WorkspaceRegion(name="tasks", source="task_list"))]),
          "warnings", ("surface 'task_list'",), False, "surface-used-as-region-source-is-live"),
    # #1332: moving workspace nav_groups into per-persona `nav` defs keeps entities alive.
    *[
        _case(LINT, lambda: _spec(_entity("Beneficiary"),
                                  surfaces=[_list_surface("beneficiary_list", "Beneficiary")],
                                  navs=[_nav("advisor", "Beneficiary")]),
              "warnings", (_DEAD, name), False, f"nav-def-keeps-{name}-live-#1332")
        for name in ("Beneficiary", "beneficiary_list")
    ],
    # #1380: a child shown in a `related` block on a reachable detail page is live.
    *[
        _case(LINT, lambda: _spec(
                  _entity("Task"), _entity("Comment"),
                  surfaces=[
                      _list_surface("task_detail", mode=ir.SurfaceMode.VIEW, related_groups=[
                          ir.RelatedGroup(name="comments", show=["Comment"],
                                          display=ir.RelatedDisplayMode.TABLE)]),
                      _list_surface("comment_create", "Comment"),
                  ],
                  workspaces=[_workspace(ir.WorkspaceRegion(name="tasks", source="Task"))]),
              "warnings", (_DEAD, name), False, f"related-block-keeps-{label}-live-#1380")
        for name, label in (("'Comment'", "child-entity"), ("comment_create", "child-surface"))
    ],
    # #1333: `managed_by:` exempts the entity and its CRUD surfaces (opt-in;
    # an unmarked orphan stays dead — see orphan-entity-is-dead).
    *[
        _case(LINT, lambda: _spec(
                  _entity("OnboardingProgress", managed_by=ir.ManagedBy.ROUTE),
                  surfaces=[_list_surface("onboarding_progress_list", "OnboardingProgress")]),
              "warnings", (_DEAD, name), False, f"managed-by-exempts-{name}-#1333")
        for name in ("OnboardingProgress", "onboarding_progress_list")
    ],
    _case(LINT, lambda: _spec(
              _entity("Task", _ref("assigned_to", "User")), _entity("User"),
              surfaces=[_list_surface(), _list_surface("user_edit", "User")],
              workspaces=[_workspace(
                  ir.WorkspaceRegion(name="tasks", source="Task", action="task_list"),
                  ir.WorkspaceRegion(name="users", source="User", action="user_edit"))]),
          "warnings", (_DEAD,), False, "fully-connected-spec-has-no-dead-constructs"),
    # --- workspace region filter FK traversal (#419) ----------------------
    _clean(validate_ux_specs, lambda: _fk_chain_spec("mark_scheme"), "filter-direct-ref-field"),
    _clean(validate_ux_specs, lambda: _fk_chain_spec("mark_scheme.subject"), "filter-one-hop-#419"),
    _clean(validate_ux_specs, lambda: _fk_chain_spec("mark_scheme.subject.department"),
           "filter-two-hops-#419"),
    _case(validate_ux_specs, lambda: _fk_chain_spec("nonexistent.department"),
          "errors", ("nonexistent.department",), True, "filter-unknown-first-segment-#419"),
    _case(validate_ux_specs, lambda: _spec(_entity("Task", _f("title", K.STR)), workspaces=[
              _workspace(_filter_region("Task", "title.something"), name="hub")]),
          "errors", ("not a reference field",), True, "filter-traverses-non-ref-field-#419"),
    _case(validate_ux_specs, lambda: _fk_chain_spec("bogus_field"),
          "errors", ("bogus_field",), True, "filter-unknown-direct-field"),
    # --- persona `uses nav` resolution (#1324) ----------------------------
    _case(validate_persona_nav_refs, lambda: _spec(personas=[_persona("nonexistent")]),
          "errors", ("teacher", "nonexistent"), True, "persona-nav-ref-unresolved"),
    _clean(validate_persona_nav_refs,
           lambda: _spec(personas=[_persona("teaching")], navs=[ir.NavSpec(name="teaching", groups=[])]),
           "persona-nav-ref-resolved"),
    _clean(validate_persona_nav_refs, lambda: _spec(personas=[_persona()]), "persona-without-nav-ref"),
    # --- workspace primary_actions targets (#1324 FR-5) -------------------
    _case(validate_workspace_primary_actions, lambda: _primary_actions_spec(("surface", "nope")),
          "errors", ("reports", "nope", "surface"), True, "primary-action-unknown-surface"),
    _case(validate_workspace_primary_actions, lambda: _primary_actions_spec(("workspace", "missing_ws")),
          "errors", ("reports", "missing_ws", "workspace"), True, "primary-action-unknown-workspace"),
    _clean(validate_workspace_primary_actions,
           lambda: _primary_actions_spec(("surface", "create_invoice"), ("workspace", "ops_dashboard")),
           "primary-action-valid-targets"),
    _clean(validate_workspace_primary_actions, _primary_actions_spec, "primary-actions-absent"),
    # --- nav curation (#1324 FR-6, warnings only) -------------------------
    _clean(NAV, lambda: _spec(personas=[_persona()]), "nav-curation-never-errors"),
    _case(NAV, lambda: _spec(personas=[_persona()]),
          "warnings", ("teacher", "auto-discovered", "uses nav"), True, "persona-without-nav-warns"),
    _case(NAV, lambda: _spec(personas=[_persona("teaching")], navs=[ir.NavSpec(name="teaching", groups=[])]),
          "warnings", ("teacher", "auto-discovered"), False, "persona-with-nav-no-auto-discovery-warning"),
    _case(NAV, lambda: _spec(personas=[ir.PersonaSpec(id="m", label="M", nav_ref="membernav")],
                             navs=[_nav("membernav", "Bogus")]),
          "warnings", ("membernav", "Bogus", "does not match"), True, "nav-item-matching-nothing-warns"),
    _case(NAV, lambda: _spec(navs=[_nav("orphan", "Bogus")]),
          "warnings", ("orphan", "not used by any persona"), True, "nav-without-persona-warns"),
    _case(NAV, lambda: _spec(navs=[_nav("orphan", "Bogus")]),
          "warnings", ("Bogus",), False, "nav-without-persona-skips-item-checks"),
    _case(NAV, lambda: _nav_groups_ws("dashboard"),
          "warnings", ("dashboard", "nav_groups", "ignored"), True, "author-workspace-nav-groups-warns"),
    _case(NAV, lambda: _nav_groups_ws("_platform_admin"),
          "warnings", ("_platform_admin", "ignored"), False, "framework-workspace-nav-groups-silent"),
    # undeclared tenant_config keys in nav `when:` (#1324 FR-4)
    _case(NAV, lambda: _nav_when_spec({"locale": "str"}, group_when=_tenant_flag("mis_connected")),
          "warnings", ("membernav", "tenant_config", "mis_connected"), True,
          "group-when-undeclared-tenant-config-warns"),
    _case(NAV, lambda: _nav_when_spec({"locale": "str"}, item_when=_tenant_flag("beta_features")),
          "warnings", ("membernav", "tenant_config", "beta_features"), True,
          "item-when-undeclared-tenant-config-warns"),
    _case(NAV, lambda: _nav_when_spec(None, group_when=_tenant_flag("mis_connected")),
          "warnings", ("membernav", "tenant_config", "mis_connected"), True,
          "no-tenancy-block-tenant-config-ref-warns"),
    _case(NAV, lambda: _nav_when_spec({"mis_connected": "bool"}, group_when=_tenant_flag("mis_connected")),
          "warnings", ("tenant_config",), False, "declared-tenant-config-key-silent"),
    _case(NAV, lambda: _nav_when_spec({"locale": "str"}),
          "warnings", ("tenant_config",), False, "no-when-no-tenant-config-warning"),
]  # fmt: skip


def _channel(result: Any, channel: str) -> list[str]:
    errors, warnings = ([], result) if isinstance(result, list) else result[:2]
    return {"errors": errors, "warnings": warnings, "all": [*errors, *warnings]}[channel]


@pytest.mark.parametrize(
    ("validator", "build", "channel", "fragments", "present"), DIAGNOSTIC_CASES
)
def test_diagnostic(
    validator: Callable[[ir.AppSpec], Any],
    build: Callable[[], ir.AppSpec],
    channel: str,
    fragments: tuple[str, ...],
    present: bool,
) -> None:
    messages = _channel(validator(build()), channel)
    assert any(all(f in m for f in fragments) for m in messages) is present, messages


# =============================================================================
# DSL → parse → link → validate (pipeline wiring)
# =============================================================================


def _appspec(dsl: str, tmp_path: Path) -> ir.AppSpec:
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text('module t\napp T "T"\n\n' + dsl)
    return build_appspec(parse_modules([dsl_dir / "app.dsl"]), "t")


def _lint(appspec: ir.AppSpec) -> Any:
    return lint_appspec(appspec, extended=False)


_ROLE_GATED = (
    "  permit:\n    list: role(admin) or role({who})\n    read: role(admin) or role({who})\n"
    "    create: role(admin)\n    update: role(admin)\n    delete: role(admin)\n\n"
    'nav membernav:\n  group "Main":\n    {entity}\n\n'
    'persona member "Member":\n  uses nav membernav\n'
)

_TILE_DSL = (
    'entity Doc "Doc":\n  id: uuid pk\n  title: str(100)\n\n'
    'surface doc_list "Docs":\n  uses entity Doc\n  mode: list\n'
    '  section main:\n    field title "Title"\n\n'
    'surface doc_detail "Doc":\n  uses entity Doc\n  mode: view\n'
    '  section main:\n    field title "Title"\n\n'
    'workspace review_queue "Queue":\n  docs:\n    source: Doc\n    display: list\n\n'
    'workspace board "Board":\n  pulse:\n    source: Doc\n    display: metrics\n'
    "    action: {target}\n    aggregate:\n      awaiting: count(Doc)\n"
)

PIPELINE_CASES = [
    pytest.param(
        NAV,
        'entity Secret "Secret":\n  id: uuid pk\n'
        + _ROLE_GATED.format(who="manager", entity="Secret"),
        "warnings",
        ("membernav", "Secret", "dead link"),
        True,
        id="curated-item-persona-cannot-list-is-dead-link-#1324",
    ),
    pytest.param(
        NAV,
        'entity Task "Task":\n  id: uuid pk\n' + _ROLE_GATED.format(who="member", entity="Task"),
        "warnings",
        ("dead link",),
        False,
        id="curated-item-persona-can-list-is-live",
    ),
    pytest.param(
        _lint,
        'entity Invoice "Invoice":\n  id: uuid pk\n\nworkspace reports "Reports":\n'
        '  primary_actions:\n    action "Go" -> surface does_not_exist\n'
        "  metrics:\n    source: Invoice\n",
        "errors",
        ("does_not_exist",),
        True,
        id="primary-action-check-wired-into-lint-#1324",
    ),
    pytest.param(
        _lint,
        'persona teacher "Teacher":\n  uses nav missing\n',
        "errors",
        ("teacher", "missing"),
        True,
        id="unresolved-persona-nav-fails-lint",
    ),
    pytest.param(
        validate_workspace_region_actions,
        'entity Doc "Doc":\n  id: uuid pk\n  title: str(100)\n\nworkspace board "Board":\n'
        "  docs:\n    source: Doc\n    display: list\n    action: nonexistent_surface\n",
        "errors",
        ("nonexistent_surface",),
        True,
        # Used to be silently ignored, shipping a row-click to a dead URL (fuzz sweep).
        id="region-action-undefined-surface-#1412",
    ),
    # #1798 — `action: <workspace>` (a runtime feature since #916) used to fail
    # lint with the #1412 "no surface named" error; on a metrics tile the target
    # must be a set (workspace / list / create), never a row-id surface.
    pytest.param(
        validate_workspace_region_actions,
        _TILE_DSL.format(target="review_queue"),
        "errors",
        ("review_queue",),
        False,
        id="region-action-workspace-target-passes-#1798",
    ),
    pytest.param(
        validate_workspace_region_actions,
        _TILE_DSL.format(target="doc_list"),
        "errors",
        ("doc_list",),
        False,
        id="metrics-action-list-surface-passes-#1798",
    ),
    pytest.param(
        validate_workspace_region_actions,
        _TILE_DSL.format(target="doc_detail"),
        "errors",
        ("doc_detail", "a metric tile has no row id"),
        True,
        id="metrics-action-view-surface-fails-#1798",
    ),
]


@pytest.mark.parametrize(("validator", "dsl", "channel", "fragments", "present"), PIPELINE_CASES)
def test_pipeline_diagnostic(
    validator: Callable[[ir.AppSpec], Any],
    dsl: str,
    channel: str,
    fragments: tuple[str, ...],
    present: bool,
    tmp_path: Path,
) -> None:
    messages = _channel(validator(_appspec(dsl, tmp_path)), channel)
    assert any(all(f in m for f in fragments) for m in messages) is present, messages


def test_resolved_persona_nav_passes_lint_and_is_linked(tmp_path: Path) -> None:
    appspec = _appspec(
        'nav teaching:\n  group "Marking":\n    Assignment\n\n'
        'persona teacher "Teacher":\n  uses nav teaching\n',
        tmp_path,
    )
    errors, _warnings, _relevance = lint_appspec(appspec, suggest=False)
    assert not any("uses nav" in e and "teaching" in e for e in errors), errors
    assert [n.name for n in appspec.navs] == ["teaching"]
