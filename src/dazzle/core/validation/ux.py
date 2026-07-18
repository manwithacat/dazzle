"""UX-spec, navigation, and workspace-action validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from dazzle.core.scope_filter_or import warn_unsupported_region_or

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
                    # #1630: OR that cannot lower to same-field __in is fail-closed
                    or_warn = warn_unsupported_region_or(region.filter, workspace.name, region_id)
                    if or_warn:
                        warnings.append(or_warn)

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


_NUMERIC_FIELD_KINDS = frozenset(
    {
        ir.FieldTypeKind.INT,
        ir.FieldTypeKind.DECIMAL,
        ir.FieldTypeKind.FLOAT,
        ir.FieldTypeKind.MONEY,
    }
)


def _validate_comparison_rank_by(
    region: ir.WorkspaceRegion,
    entity: ir.EntitySpec | None,
    label: str,
) -> list[str]:
    """Check `rank_by` is present and resolves for the region's mode (#1470)."""
    if not region.rank_by:
        return [
            f"E_COMPARISON_RANK_BY_REQUIRED: {label} uses `display: comparison` but "
            f"has no `rank_by:` — name the aggregate (group mode) or numeric field "
            f"(entity-row mode) to rank by."
        ]
    if region.group_by is not None or region.group_by_dims:
        # Group mode: rank_by must name a declared aggregate.
        if region.rank_by not in region.aggregates:
            known = ", ".join(sorted(region.aggregates)) or "(none)"
            return [
                f"E_COMPARISON_RANK_BY_UNKNOWN: {label} `rank_by: {region.rank_by}` "
                f"is not a declared aggregate. Known aggregates: {known}."
            ]
        return []
    # Entity-row mode: rank_by must name a numeric field on the source.
    field = None
    if entity is not None:
        field = next((f for f in entity.fields if f.name == region.rank_by), None)
    if field is None or field.type.kind not in _NUMERIC_FIELD_KINDS:
        return [
            f"E_COMPARISON_METRIC_NOT_NUMERIC: {label} `rank_by: {region.rank_by}` "
            f"must name a numeric field (int/decimal/float/money) on the source "
            f"entity, or use `group_by` + an aggregate."
        ]
    return []


def _validate_comparison_outlier(outlier: ir.ComparisonOutlierSpec, label: str) -> list[str]:
    """Check outlier params are well-formed (#1470)."""
    if outlier.method == "sigma" and outlier.sigma_k is not None and outlier.sigma_k <= 0:
        return [
            f"E_COMPARISON_OUTLIER_INVALID: {label} sigma outlier needs a positive "
            f"`sigma_k` (got {outlier.sigma_k})."
        ]
    if (
        outlier.method == "threshold"
        and outlier.threshold_low is None
        and outlier.threshold_high is None
    ):
        return [
            f"E_COMPARISON_OUTLIER_INVALID: {label} threshold outlier needs at "
            f"least one of `low`/`high`."
        ]
    return []


def _validate_comparison_region(
    region: ir.WorkspaceRegion,
    entity: ir.EntitySpec | None,
    label: str,
) -> list[str]:
    """Pure rule check for one ``display: comparison`` region (#1470).

    ``label`` prefixes each message (e.g. ``Workspace 'w' region 'league'``).
    Group mode (``group_by`` set) ranks an aggregate; entity-row mode ranks a
    numeric source field. Returns a list of ``E_COMPARISON_*`` error strings.
    """
    errors = _validate_comparison_rank_by(region, entity, label)
    if region.order not in ("asc", "desc"):
        errors.append(
            f"E_COMPARISON_ORDER_INVALID: {label} `order: {region.order}` must be 'asc' or 'desc'."
        )
    if region.outlier is not None:
        errors.extend(_validate_comparison_outlier(region.outlier, label))
    return errors


def validate_comparison_regions(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate every ``display: comparison`` region across all workspaces (#1470)."""
    errors: list[str] = []
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.display != ir.DisplayMode.COMPARISON:
                continue
            source_name = (
                region.source.split(".")[0]
                if region.source and "." in region.source
                else region.source
            )
            entity = appspec.get_entity(source_name) if source_name else None
            label = f"Workspace '{workspace.name}' region '{region.name or region.source}'"
            errors.extend(_validate_comparison_region(region, entity, label))
    return errors, []


def validate_outlier_decorators(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate ``outlier_on`` statistical decorators on list regions (#1470)."""
    errors: list[str] = []
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if not region.outlier_on:
                continue
            label = f"Workspace '{workspace.name}' region '{region.name or region.source}'"
            if region.display != ir.DisplayMode.LIST:
                errors.append(
                    f"E_OUTLIER_DISPLAY: {label} `outlier_on` requires `display: list` "
                    f"(got {region.display.value})."
                )
            source_name = (
                region.source.split(".")[0]
                if region.source and "." in region.source
                else region.source
            )
            entity = appspec.get_entity(source_name) if source_name else None
            field = None
            if entity is not None:
                field = next((f for f in entity.fields if f.name == region.outlier_on), None)
            if field is None or field.type.kind not in _NUMERIC_FIELD_KINDS:
                errors.append(
                    f"E_OUTLIER_NOT_NUMERIC: {label} `outlier_on: {region.outlier_on}` must "
                    f"name a numeric field (int/decimal/float/money) on the source entity."
                )
            if region.outlier is not None:
                errors.extend(_validate_comparison_outlier(region.outlier, label))
    return errors, []


def validate_rag_decorators(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate `rag_on` fixed-band RAG decorators on list regions (#1470)."""
    errors: list[str] = []
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if not region.rag_on:
                continue
            label = f"Workspace '{workspace.name}' region '{region.name or region.source}'"
            if region.display != ir.DisplayMode.LIST:
                errors.append(
                    f"E_RAG_DISPLAY: {label} `rag_on` requires `display: list` "
                    f"(got {region.display.value})."
                )
            source_name = (
                region.source.split(".")[0]
                if region.source and "." in region.source
                else region.source
            )
            entity = appspec.get_entity(source_name) if source_name else None
            field = None
            if entity is not None:
                field = next((f for f in entity.fields if f.name == region.rag_on), None)
            if field is None or field.type.kind not in _NUMERIC_FIELD_KINDS:
                errors.append(
                    f"E_RAG_NOT_NUMERIC: {label} `rag_on: {region.rag_on}` must name a numeric "
                    f"field (int/decimal/float/money) on the source entity."
                )
            if not region.tone_bands:
                errors.append(
                    f"E_RAG_BANDS_REQUIRED: {label} `rag_on` requires a non-empty `tone_bands`."
                )
    return errors, []


def validate_insight_summaries(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate `display: insight_summary` regions (#1470 Slice 1)."""
    errors: list[str] = []
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.display != ir.DisplayMode.INSIGHT_SUMMARY:
                continue
            label = f"Workspace '{workspace.name}' region '{region.name or region.source}'"
            if region.group_by_dims:
                errors.append(
                    f"E_INSIGHT_SINGLE_DIM_ONLY: {label} `display: insight_summary` supports a "
                    f"single `group_by` only (got a multi-dimension list)."
                )
            elif region.group_by is None:
                errors.append(
                    f"E_INSIGHT_GROUP_BY_REQUIRED: {label} `display: insight_summary` requires "
                    f"a `group_by`."
                )
            if not region.aggregates:
                errors.append(
                    f"E_INSIGHT_AGGREGATE_REQUIRED: {label} `display: insight_summary` requires "
                    f"at least one `aggregate`."
                )
    return errors, []


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


def validate_enum_semantics(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate `semantic:` tone bindings on enums (#1493, UX-maturity 1b).

    Each declared tone must resolve to a canonical tone (the 5-tone palette, with
    `positive`→`success`). Value membership is enforced at parse time
    (E_SEMANTIC_VALUE_UNKNOWN); here we gate the tone vocabulary
    (E_SEMANTIC_TONE_UNKNOWN). Covers both shared `enum` blocks
    (EnumValueSpec.semantic) and inline `enum[...]` fields (FieldType.enum_semantics).
    """
    from ..ir.tones import CANONICAL_TONES, normalize_tone

    errors: list[str] = []
    warnings: list[str] = []
    palette = ", ".join(CANONICAL_TONES)

    for enum in appspec.enums:
        for value in enum.values:
            if value.semantic is not None and normalize_tone(value.semantic) is None:
                errors.append(
                    f"E_SEMANTIC_TONE_UNKNOWN: enum '{enum.name}' value '{value.name}' "
                    f"binds unknown tone '{value.semantic}'. Allowed: {palette} "
                    f"(or alias `positive`→`success`)."
                )

    for entity in appspec.domain.entities:
        for field in entity.fields:
            ft = getattr(field, "type", None)
            semantics = getattr(ft, "enum_semantics", None) if ft else None
            if not semantics:
                continue
            for value_name, tone in semantics.items():
                if normalize_tone(tone) is None:
                    errors.append(
                        f"E_SEMANTIC_TONE_UNKNOWN: {entity.name}.{field.name} value "
                        f"'{value_name}' binds unknown tone '{tone}'. Allowed: {palette} "
                        f"(or alias `positive`→`success`)."
                    )

    return errors, warnings
