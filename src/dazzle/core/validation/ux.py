"""UX-spec, navigation, and workspace-action validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from .. import ir
from ..access import workspace_allowed_personas
from .conditions import _validate_condition_fields
from .extended import _is_framework_synthetic_name


def validate_ux_specs(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate UX semantic layer specifications.

    Checks:
    - UX show fields exist in referenced entity
    - UX sort fields exist in referenced entity
    - UX filter fields exist in referenced entity
    - UX search fields exist in referenced entity
    - Attention signal conditions reference valid fields
    - Persona variants have valid configurations
    - Workspace regions reference valid sources

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    for surface in appspec.surfaces:
        if not surface.ux:
            continue

        entity = None
        if surface.entity_ref:
            entity = appspec.get_entity(surface.entity_ref)

        ux = surface.ux

        # Validate show fields
        if ux.show and entity:
            entity_field_names = {f.name for f in entity.fields}
            for field_name in ux.show:
                if field_name not in entity_field_names:
                    errors.append(
                        f"Surface '{surface.name}' UX show references non-existent "
                        f"field '{field_name}' from entity '{entity.name}'"
                    )

        # Validate sort fields
        if ux.sort and entity:
            entity_field_names = {f.name for f in entity.fields}
            for sort_spec in ux.sort:
                if sort_spec.field not in entity_field_names:
                    errors.append(
                        f"Surface '{surface.name}' UX sort references non-existent "
                        f"field '{sort_spec.field}' from entity '{entity.name}'"
                    )

        # Validate filter fields
        if ux.filter and entity:
            entity_field_names = {f.name for f in entity.fields}
            for field_name in ux.filter:
                if field_name not in entity_field_names:
                    errors.append(
                        f"Surface '{surface.name}' UX filter references non-existent "
                        f"field '{field_name}' from entity '{entity.name}'"
                    )

        # Validate search fields
        if ux.search and entity:
            entity_field_names = {f.name for f in entity.fields}
            for field_name in ux.search:
                if field_name not in entity_field_names:
                    errors.append(
                        f"Surface '{surface.name}' UX search references non-existent "
                        f"field '{field_name}' from entity '{entity.name}'"
                    )

        # Validate attention signals
        for signal in ux.attention_signals:
            field_errors = _validate_condition_fields(
                signal.condition,
                entity,
                f"Surface '{surface.name}' attention signal",
                appspec=appspec,
            )
            errors.extend(field_errors)

            # Warn if attention signal has no message
            if not signal.message:
                warnings.append(
                    f"Surface '{surface.name}' attention signal at level "
                    f"'{signal.level.value}' has no message"
                )

        # Validate persona variants
        for variant in ux.persona_variants:
            # Validate scope condition fields
            if variant.scope:
                field_errors = _validate_condition_fields(
                    variant.scope,
                    entity,
                    f"Surface '{surface.name}' persona '{variant.persona}' scope",
                    appspec=appspec,
                )
                errors.extend(field_errors)

            # Validate show/hide fields
            if entity:
                entity_field_names = {f.name for f in entity.fields}
                for field_name in variant.show:
                    if field_name not in entity_field_names:
                        errors.append(
                            f"Surface '{surface.name}' persona '{variant.persona}' "
                            f"show references non-existent field '{field_name}'"
                        )
                for field_name in variant.hide:
                    if field_name not in entity_field_names:
                        errors.append(
                            f"Surface '{surface.name}' persona '{variant.persona}' "
                            f"hide references non-existent field '{field_name}'"
                        )

    # Validate workspaces
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            # Skip source validation for aggregate-only regions
            if region.source is None:
                continue

            # Check that source references a valid entity
            source_entity_name = (
                region.source.split(".")[0] if "." in region.source else region.source
            )
            entity = appspec.get_entity(source_entity_name)
            if not entity:
                errors.append(
                    f"Workspace '{workspace.name}' region '{region.name or region.source}' "
                    f"references non-existent entity '{source_entity_name}'"
                )
            else:
                # Validate filter conditions
                if region.filter:
                    region_id = region.name or region.source
                    ctx = f"Workspace '{workspace.name}' region '{region_id}' filter"
                    field_errors = _validate_condition_fields(
                        region.filter,
                        entity,
                        ctx,
                        appspec=appspec,
                    )
                    errors.extend(field_errors)

                # Validate sort fields
                if region.sort:
                    entity_field_names = {f.name for f in entity.fields}
                    for sort_spec in region.sort:
                        if sort_spec.field not in entity_field_names:
                            errors.append(
                                f"Workspace '{workspace.name}' region "
                                f"'{region.name or region.source}' sort references "
                                f"non-existent field '{sort_spec.field}'"
                            )

    return errors, warnings


def validate_persona_nav_refs(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate that each persona's `uses nav <name>` resolves (#1324).

    A persona binds a single sidebar via ``uses nav <name>`` (parsed into
    ``PersonaSpec.nav_ref``). The referenced name MUST match a declared
    top-level ``nav <name>:`` block (collected into ``AppSpec.navs``).
    An unresolved reference is a validation ERROR.

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    declared_navs = {nav.name for nav in appspec.navs}
    for persona in appspec.personas:
        if persona.nav_ref is None:
            continue
        if persona.nav_ref not in declared_navs:
            errors.append(
                f"persona '{persona.id}' uses nav '{persona.nav_ref}', but no "
                f"`nav {persona.nav_ref}:` is declared"
            )

    return errors, warnings


def validate_workspace_primary_actions(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate that each workspace `primary_actions:` target resolves (#1324 FR-5).

    An authored heading-CTA action references a declared SURFACE or WORKSPACE
    by name (parsed into ``WorkspaceSpec.primary_actions``). When
    ``target_kind == "surface"`` the target MUST match a declared surface
    name (``appspec.surfaces``); when ``"workspace"``, a declared workspace
    name (``appspec.workspaces``). An unresolved target is a validation ERROR.

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    declared_surfaces = {s.name for s in appspec.surfaces}
    declared_workspaces = {ws.name for ws in appspec.workspaces}

    for ws in appspec.workspaces:
        for action in ws.primary_actions:
            if action.target_kind == "surface":
                if action.target not in declared_surfaces:
                    errors.append(
                        f"workspace '{ws.name}' primary action \"{action.label}\" "
                        f"targets surface '{action.target}', but no such surface "
                        f"is declared"
                    )
            elif action.target_kind == "workspace":
                if action.target not in declared_workspaces:
                    errors.append(
                        f"workspace '{ws.name}' primary action \"{action.label}\" "
                        f"targets workspace '{action.target}', but no such workspace "
                        f"is declared"
                    )

    return errors, warnings


def validate_emits_targets(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """#1392 item 3: every surface ``emits:`` target must resolve to a declared surface.

    The custom-mode analogue of ``validate_workspace_primary_actions`` — a custom
    (``render:`` / ``mode: custom``) surface declares the surfaces it links to; an
    ``emits:`` naming a surface the AppSpec doesn't declare is a build ERROR
    (``E_DEAD_EMIT_TARGET``), so a renamed / deleted / typo'd target fails the build
    instead of shipping a dead link. Surfaces with no ``emits:`` are unconstrained
    (opt-in).

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    declared_surfaces = {s.name for s in appspec.surfaces}

    for surface in appspec.surfaces:
        for target in surface.emits:
            if target not in declared_surfaces:
                errors.append(
                    f"E_DEAD_EMIT_TARGET: surface '{surface.name}' emits: '{target}', "
                    f"which is not a declared surface. Fix the name or remove it from "
                    f"`emits:`."
                )

    return errors, []


_TENANT_CONFIG_PREFIX = "tenant_config."


def _collect_tenant_config_refs(condition: ir.ConditionExpr | None) -> list[str]:
    """Walk a ConditionExpr and collect the ``<key>`` of every
    ``tenant_config.<key>`` field reference (#1324 FR-4).

    Recurses through compound (AND/OR/NOT) nodes and reads the LHS ``field``
    of each leaf comparison. A bare flag (``tenant_config.mis_connected``)
    parses to an implicit ``= true`` comparison whose ``field`` carries the
    full dotted path, so reading ``comparison.field`` covers both the bare and
    the explicit (``tenant_config.tier = "pro"``) forms. Role/grant/via leaves
    have no ``tenant_config`` field and contribute nothing.
    """
    if condition is None:
        return []
    keys: list[str] = []
    # Compound node: recurse both sides.
    if condition.left is not None:
        keys.extend(_collect_tenant_config_refs(condition.left))
    if condition.right is not None:
        keys.extend(_collect_tenant_config_refs(condition.right))
    # Leaf comparison.
    if condition.comparison is not None and condition.comparison.field:
        field = condition.comparison.field
        if field.startswith(_TENANT_CONFIG_PREFIX):
            keys.append(field[len(_TENANT_CONFIG_PREFIX) :])
    return keys


def validate_nav_curation(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Lint per-persona-global navigation curation (#1324 FR-6).

    All three diagnostics are WARNINGS (the errors list is always empty):

    1. **Auto-discovery reliance** — a persona with no ``uses nav`` binding
       gets an auto-discovered sidebar; warn so the author can make it
       explicit.
    2. **Dead curated nav item** — a ``nav`` lists an entity/workspace that
       NO persona bound to that nav can reach (entity: matrix LIST denied for
       all bound personas; workspace: not allowed for any bound persona), so
       the runtime access-filter drops it (dead link). Also warns when an
       item resolves to neither an entity nor a workspace, and once when a
       declared nav has no bound persona at all (then skips its item checks).
    3. **Ignored workspace nav_groups** — author-declared (non ``_``-prefixed)
       workspace ``nav_groups`` are framework-internal now and ignored for the
       author-facing sidebar.

    Returns:
        Tuple of (errors, warnings) — errors is always empty.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- Diagnostic 1: auto-discovery reliance -------------------------------
    for persona in appspec.personas:
        if persona.nav_ref is None:
            warnings.append(
                f"persona '{persona.id}' has no explicit nav (uses nav) — its "
                f"sidebar is auto-discovered; bind one with `uses nav <name>` "
                f"to make navigation explicit."
            )

    # --- Diagnostic 2: dead curated nav item ---------------------------------
    # Compute the RBAC matrix once (reused exactly as the other validators do).
    matrix = None
    try:
        from dazzle.rbac.matrix import PolicyDecision, generate_access_matrix

        matrix = generate_access_matrix(appspec)
    except ImportError:
        matrix = None
    except Exception:
        # Matrix generation can fail on incomplete AppSpecs during early
        # development; degrade gracefully rather than blocking lint.
        matrix = None

    entity_names = {e.name for e in appspec.domain.entities}
    workspaces_by_name = {ws.name: ws for ws in appspec.workspaces}

    for nav in appspec.navs:
        bound = [p for p in appspec.personas if p.nav_ref == nav.name]
        if not bound:
            warnings.append(
                f"nav '{nav.name}' is not used by any persona (no `uses nav {nav.name}`)."
            )
            continue

        bound_ids = ", ".join(p.id for p in bound)
        for group in nav.groups:
            for item in group.items:
                target = item.entity
                if target in entity_names:
                    # Dead if NO bound persona can LIST the entity.
                    if matrix is not None and all(
                        matrix.get(p.effective_role, target, "list") == PolicyDecision.DENY
                        for p in bound
                    ):
                        warnings.append(
                            f"nav '{nav.name}' lists entity '{target}', but no "
                            f"persona using it ({bound_ids}) can LIST it — it "
                            f"will be filtered out (dead link)."
                        )
                elif target in workspaces_by_name:
                    ws = workspaces_by_name[target]
                    allowed = workspace_allowed_personas(ws, appspec.personas)
                    # None means "everyone allowed". Dead if no bound persona
                    # is in the allowed set.
                    if allowed is not None and not any(p.id in allowed for p in bound):
                        warnings.append(
                            f"nav '{nav.name}' lists workspace '{target}', but no "
                            f"persona using it ({bound_ids}) can reach it — it "
                            f"will be filtered out (dead link)."
                        )
                else:
                    warnings.append(
                        f"nav '{nav.name}' item '{target}' does not match any entity or workspace."
                    )

    # --- Diagnostic 4: nav `when` references undeclared tenant_config (#1324 FR-4) ---
    # A nav group/item may carry a render-time VISIBILITY `when` condition. When
    # that condition references `tenant_config.<key>`, the key must be declared
    # in `tenancy.per_tenant_config` (a key→type map); otherwise the runtime has
    # nothing to resolve and the group/item silently never shows. WARN per
    # undeclared key. Only tenant_config refs are checked here — role/grant refs
    # are validated by the access-control validators, not nav curation.
    declared_config_keys: set[str] = set()
    if appspec.tenancy is not None:
        declared_config_keys = set(appspec.tenancy.per_tenant_config.keys())

    for nav in appspec.navs:
        for group in nav.groups:
            for key in _collect_tenant_config_refs(group.when):
                if key not in declared_config_keys:
                    warnings.append(
                        f"nav '{nav.name}' group '{group.label}' `when` condition "
                        f"references tenant_config.{key!r}, which is not declared in "
                        f"tenancy.per_tenant_config."
                    )
            for item in group.items:
                for key in _collect_tenant_config_refs(item.when):
                    if key not in declared_config_keys:
                        warnings.append(
                            f"nav '{nav.name}' item '{item.entity}' `when` condition "
                            f"references tenant_config.{key!r}, which is not declared in "
                            f"tenancy.per_tenant_config."
                        )

    # --- Diagnostic 3: ignored author-declared workspace nav_groups ----------
    # Discriminator: framework admin-platform workspaces are named with a
    # leading underscore (`_platform_admin`, `_tenant_admin` — built by
    # core/admin_builder._build_admin_workspaces). This is the same #824
    # reserved-name convention every other workspace lint rule uses, so reuse
    # `_is_framework_synthetic_name`. Author workspaces have no such prefix;
    # their nav_groups are framework-internal now and ignored for the sidebar.
    for ws in appspec.workspaces:
        if ws.nav_groups and not _is_framework_synthetic_name(ws.name):
            warnings.append(
                f"workspace '{ws.name}' declares nav_groups, but author-facing "
                f"navigation is per-persona now (`persona X: uses nav Y`); these "
                f"nav_groups are ignored for the sidebar. (Workspace nav_groups "
                f"are framework-internal.)"
            )

    return errors, warnings


def validate_workspace_region_actions(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Error when a region `action:` on a cross-entity surface has no valid FK path (#861).

    When a region sourced from entity A declares `action: some_surface` and
    `some_surface` is bound to a different entity B, the runtime looks for a
    single FK field on A that references B to thread the row ID through to
    the action URL. If zero or multiple FK candidates exist, the action URL
    silently misfires at runtime. Flag both conditions at validate time.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not appspec.workspaces:
        return errors, warnings

    surfaces_by_name: dict[str, ir.SurfaceSpec] = {s.name: s for s in appspec.surfaces}
    entities_by_name: dict[str, ir.EntitySpec] = {e.name: e for e in appspec.domain.entities}

    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if not region.action:
                continue
            action_surface = surfaces_by_name.get(region.action)
            if action_surface is None:
                # #1412: an `action:` referencing a non-existent surface was
                # silently ignored (the old comment claimed it was "caught
                # elsewhere" — it wasn't, so a typo'd ref shipped a runtime
                # row-click to a dead URL). A path-style action (an action_grid
                # CTA, which starts with "/") is legitimately not a surface
                # name, so only flag identifier-shaped dangling refs.
                if "/" not in region.action:
                    region_label = getattr(region, "name", None) or region.source or "?"
                    errors.append(
                        f"Workspace '{workspace.name}' region '{region_label}' declares "
                        f"`action: {region.action}` but no surface named "
                        f"'{region.action}' exists — the row-click action would "
                        f"navigate to a non-existent surface at runtime."
                    )
                continue
            if not region.source:
                continue  # FK-threading check below requires a source entity
            target_entity = action_surface.entity_ref
            if not target_entity or target_entity == region.source:
                continue  # same-entity action — no FK needed
            source_entity = entities_by_name.get(region.source)
            if source_entity is None:
                continue  # region sourced from a surface, not an entity
            fk_candidates: list[str] = []
            for f in source_entity.fields:
                kind = getattr(f.type, "kind", None)
                kind_val = kind.value if hasattr(kind, "value") else str(kind)  # type: ignore[union-attr]
                if kind_val in ("ref", "belongs_to"):
                    ref_target = getattr(f.type, "ref_entity", None)
                    if ref_target == target_entity:
                        fk_candidates.append(f.name)
            if len(fk_candidates) == 0:
                errors.append(
                    f"Workspace '{workspace.name}' region '{region.name}' declares "
                    f"`action: {region.action}` targeting entity '{target_entity}', "
                    f"but source entity '{region.source}' has no FK field referencing "
                    f"'{target_entity}'. Add a `ref {target_entity}` field or change "
                    f"the action to a surface on '{region.source}'."
                )
            elif len(fk_candidates) > 1:
                errors.append(
                    f"Workspace '{workspace.name}' region '{region.name}' declares "
                    f"`action: {region.action}` targeting entity '{target_entity}', "
                    f"but source entity '{region.source}' has multiple FK fields "
                    f"referencing '{target_entity}' ({', '.join(fk_candidates)}). "
                    f"Ambiguous FK — the runtime cannot pick one automatically."
                )
    return errors, warnings
