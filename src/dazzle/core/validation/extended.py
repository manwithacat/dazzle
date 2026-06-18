"""Extended lint checks (dead constructs, naming, anti-patterns, suggestions).

Split verbatim from dazzle.core.validator per #1361.
"""

from .. import ir


def _detect_dead_constructs(appspec: ir.AppSpec) -> list[str]:
    """Detect unreferenced surfaces, orphan entities, and unreachable experiences.

    Builds a reachability graph from entry points (workspaces, experiences,
    processes) through surfaces to entities. Reports constructs that are
    defined but never referenced from any entry point.
    """
    warnings: list[str] = []

    # --- Collect all defined constructs ---
    all_entities = {e.name for e in appspec.domain.entities}
    entity_locs = {e.name: e.source for e in appspec.domain.entities}
    # Framework-synthetic platform entities (SystemMetric, SystemHealth,
    # AIJob, FeedbackReport, etc. — `domain == "platform"`) are injected by
    # the framework and may be gated off in MINIMAL security profile,
    # leaving them unreferenced by app code. They aren't dead code — they
    # come back the moment security.profile flips to STANDARD. They remain
    # in `all_entities` so surface-reachability cascades still see them,
    # but they're excluded from the dead-entity warning below.
    platform_entities = {
        e.name for e in appspec.domain.entities if getattr(e, "domain", None) == "platform"
    }
    # Entities whose lifecycle is owned outside the nav graph (#1333):
    # `managed_by: route|pipeline|wizard|external`. They are reachable only
    # via a custom route/pipeline/wizard/external system, so they (and their
    # CRUD surfaces) are intentionally absent from workspace/nav references —
    # not dead code. Orthogonal to `domain: platform`: the entity keeps its
    # real business domain and is NOT framework-injected.
    managed_entities = {
        e.name for e in appspec.domain.entities if getattr(e, "managed_by", None) is not None
    }
    all_surfaces = {s.name for s in appspec.surfaces}
    surface_locs = {s.name: s.source for s in appspec.surfaces}
    # --- Collect all entity references ---
    used_entities: set[str] = set()

    # Entities referenced by other entities (field refs)
    for entity in appspec.domain.entities:
        for field in entity.fields:
            if field.type.kind == ir.FieldTypeKind.REF and field.type.ref_entity:
                used_entities.add(field.type.ref_entity)

    # Entities referenced by surfaces
    for surface in appspec.surfaces:
        if surface.entity_ref:
            used_entities.add(surface.entity_ref)

    # #1380: entities surfaced via a `related ...: show: <Entity>` block on a
    # detail/view surface are reachable — the parent detail page renders them,
    # and they're navigable from there. Without this walk, a child entity that
    # lives only inside a related block (and its CRUD surfaces) was falsely
    # flagged "dead". Reused below to keep those child surfaces alive too.
    related_entities: set[str] = set()
    for surface in appspec.surfaces:
        for group in getattr(surface, "related_groups", None) or []:
            for shown in getattr(group, "show", None) or []:
                if shown in all_entities:
                    related_entities.add(shown)
    used_entities |= related_entities

    # Entities referenced by workspace regions (source field)
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.source and region.source in all_entities:
                used_entities.add(region.source)

    # Entities referenced by process triggers
    for process in appspec.processes:
        if process.trigger and process.trigger.entity_name:
            used_entities.add(process.trigger.entity_name)

    # Entities referenced by integration mappings
    for integration in appspec.integrations:
        for mapping in integration.mappings:
            if mapping.entity_ref:
                used_entities.add(mapping.entity_ref)

    # Entities referenced by per-persona nav defs (#1324, #1332). A `nav <name>:`
    # block bound via `persona X: uses nav Y` links to entity nav routes exactly
    # like workspace nav_groups, so an entity living only in a nav def is reachable.
    for nav in appspec.navs:
        for group in nav.groups:
            for nav_item in group.items:
                if nav_item.entity in all_entities:
                    used_entities.add(nav_item.entity)

    unused_entities = all_entities - used_entities - platform_entities - managed_entities
    if unused_entities:
        for name in sorted(unused_entities):
            loc = entity_locs.get(name)
            loc_suffix = f" (defined at {loc})" if loc else ""
            warnings.append(f"Dead construct: entity '{name}' is never referenced{loc_suffix}")

    # --- Collect all surface references ---
    used_surfaces: set[str] = set()

    # Surfaces referenced by workspace regions (action field)
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.action and region.action in all_surfaces:
                used_surfaces.add(region.action)
            # source can also be a surface name
            if region.source and region.source in all_surfaces:
                used_surfaces.add(region.source)

    # Surfaces referenced by experience steps
    for experience in appspec.experiences:
        for step in experience.steps:
            if step.surface:
                used_surfaces.add(step.surface)

    # Surfaces referenced by process human_task steps
    for process in appspec.processes:
        for proc_step in process.steps:
            if proc_step.human_task and proc_step.human_task.surface:
                used_surfaces.add(proc_step.human_task.surface)

    # Surfaces included via subtype_panel branches (#1411): a surface
    # referenced only through `subtype_panel: when ... include surface X` is
    # alive. Without this walk, _detect_dead_constructs false-flags such a
    # surface as dead (caught by the fuzz sweep on fixtures/asset_registry).
    for surface in appspec.surfaces:
        for section in surface.sections:
            panel = section.subtype_panel
            if panel is None:
                continue
            for branch in panel.branches:
                if branch.include_surface:
                    used_surfaces.add(branch.include_surface)

    # Surfaces belonging to entities used in workspace regions are implicitly
    # alive — entity CRUD surfaces are navigable from workspace detail pages
    # even when not explicitly wired to a workspace action.
    # Entities listed in nav_groups are also navigable via entity nav routes
    # (e.g. /app/trust, /app/trust/create) even without a workspace region.
    workspace_entities: set[str] = set()
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.source and region.source in all_entities:
                workspace_entities.add(region.source)
            for src in region.sources:
                if src in all_entities:
                    workspace_entities.add(src)
        for nav_group in workspace.nav_groups:
            for nav_item in nav_group.items:
                if nav_item.entity in all_entities:
                    workspace_entities.add(nav_item.entity)
    # Per-persona nav defs (#1324, #1332): entities living only in a top-level
    # `nav <name>:` block (bound via `persona X: uses nav Y`) are navigable via
    # their entity nav routes exactly like workspace nav_groups items. Without
    # this, migrating workspace nav_groups → nav defs (which the nav-curation
    # lint recommends) flags every such entity's CRUD surfaces as dead.
    for nav in appspec.navs:
        for nav_group in nav.groups:
            for nav_item in nav_group.items:
                if nav_item.entity in all_entities:
                    workspace_entities.add(nav_item.entity)
    # Lifecycle-owned-outside-the-graph entities (#1333): their CRUD surfaces
    # are reached via the custom route/pipeline/wizard/external mechanism, so
    # they are alive even without a workspace/nav reference.
    workspace_entities |= managed_entities
    # #1380: child entities shown via a `related` block are reachable from the
    # parent detail page, so their CRUD surfaces are alive (not dead).
    workspace_entities |= related_entities
    for surface in appspec.surfaces:
        if surface.entity_ref and surface.entity_ref in workspace_entities:
            used_surfaces.add(surface.name)

    unused_surfaces = all_surfaces - used_surfaces
    if unused_surfaces:
        for name in sorted(unused_surfaces):
            loc = surface_locs.get(name)
            loc_suffix = f" (defined at {loc})" if loc else ""
            warnings.append(
                f"Dead construct: surface '{name}' is not referenced by any "
                f"workspace, experience, or process{loc_suffix}"
            )

    # --- Collect all experience references ---
    # Experiences are entry points themselves, but check if any are completely
    # disconnected (no workspace or navigation references them).
    # For now, experiences are considered used if they exist — they are
    # top-level entry points like workspaces.

    return warnings


def _lint_naming_conventions(appspec: ir.AppSpec) -> list[str]:
    """Check entity PascalCase and field snake_case naming."""
    warnings: list[str] = []
    for entity in appspec.domain.entities:
        if not entity.name[0].isupper():
            warnings.append(f"Entity '{entity.name}' should use PascalCase naming")
        for field in entity.fields:
            if field.name != field.name.lower():
                if "_" in field.name or not any(c.isupper() for c in field.name[1:]):
                    continue  # It's snake_case or lowercase, ok
                warnings.append(
                    f"Entity '{entity.name}' field '{field.name}' should use snake_case naming"
                )
    return warnings


def _lint_missing_titles(appspec: ir.AppSpec) -> list[str]:
    """Check for entities and surfaces without titles."""
    warnings: list[str] = []
    for entity in appspec.domain.entities:
        if not entity.title:
            warnings.append(f"Entity '{entity.name}' has no title")
    for surface in appspec.surfaces:
        if not surface.title:
            warnings.append(f"Surface '{surface.name}' has no title")
    return warnings


def _validate_persona_backed_by(appspec: ir.AppSpec) -> list[str]:
    """Validate ``backed_by`` / ``link_via`` on persona declarations.

    Cycle 248 (closes EX-045). When a persona declares ``backed_by: Entity``,
    the linker verifies:

    1. The named entity exists in ``appspec.domain.entities``.
    2. The entity has a field matching ``link_via`` (default ``"email"``).
    3. No two personas claim the same ``backed_by`` entity (ambiguous).

    Returns a list of error strings (not warnings — a misconfigured
    ``backed_by`` is a hard error that will break scope-rule evaluation
    at runtime if left undetected).
    """
    errors: list[str] = []
    entity_names = {e.name for e in appspec.domain.entities}
    entity_fields: dict[str, set[str]] = {}
    for e in appspec.domain.entities:
        entity_fields[e.name] = {f.name for f in e.fields}

    seen_backed: dict[str, str] = {}  # entity_name → persona_id
    for persona in appspec.personas:
        if not persona.backed_by:
            continue

        ent_name = persona.backed_by
        link_field = persona.link_via

        # Check 1: entity exists
        if ent_name not in entity_names:
            errors.append(
                f"Persona '{persona.id}' declares backed_by: {ent_name} "
                f"but entity '{ent_name}' does not exist."
            )
            continue

        # Check 2: link_via field exists on the entity
        if link_field not in entity_fields.get(ent_name, set()):
            errors.append(
                f"Persona '{persona.id}' declares backed_by: {ent_name} "
                f"with link_via: {link_field}, but entity '{ent_name}' "
                f"has no field named '{link_field}'."
            )

        # Check 3: no duplicate backed_by
        if ent_name in seen_backed:
            errors.append(
                f"Persona '{persona.id}' declares backed_by: {ent_name} "
                f"but persona '{seen_backed[ent_name]}' already claims it. "
                f"Each entity can back at most one persona."
            )
        else:
            seen_backed[ent_name] = persona.id

    return errors


def _is_framework_synthetic_name(name: str) -> bool:
    """Reserved-name convention (#824): entries whose name begins with
    an underscore are framework-synthesised (admin workspace and its
    surfaces, internal platform constructs). Adopters can't fix lint
    warnings about them from their own DSL, so every workspace/surface
    lint rule skips these names."""
    return name.startswith("_")


def _lint_workspace_personas(appspec: ir.AppSpec) -> list[str]:
    """Check for workspaces without associated personas.

    Skips framework-synthesised workspaces (names starting with `_`)
    which are auto-generated with correct access specs; see #824.
    """
    if not appspec.workspaces:
        return []

    warnings: list[str] = []
    persona_ids = {p.id for p in appspec.personas}

    workspaces_with_personas: set[str] = set()
    for workspace in appspec.workspaces:
        if workspace.ux and workspace.ux.persona_variants:
            for variant in workspace.ux.persona_variants:
                if variant.persona in persona_ids:
                    workspaces_with_personas.add(workspace.name)
                    break

        # `access: persona(admin, manager)` is a first-class persona
        # binding — no need to also require a default_workspace entry
        # or ux.persona_variants block to silence this lint.
        access = getattr(workspace, "access", None)
        allow_personas = getattr(access, "allow_personas", None) if access else None
        if allow_personas:
            if any(p in persona_ids for p in allow_personas):
                workspaces_with_personas.add(workspace.name)

    for persona in appspec.personas:
        if persona.default_workspace:
            for ws in appspec.workspaces:
                if ws.name == persona.default_workspace:
                    workspaces_with_personas.add(ws.name)

    for workspace in appspec.workspaces:
        if _is_framework_synthetic_name(workspace.name):
            continue
        if workspace.name not in workspaces_with_personas:
            warnings.append(
                f"Workspace '{workspace.name}' has no associated persona. "
                f"Consider adding a persona for role-based access control."
            )
    return warnings


def _lint_workspace_routing(appspec: ir.AppSpec) -> list[str]:
    """Check for workspaces with no routable content."""
    if not appspec.workspaces:
        return []

    warnings: list[str] = []
    surface_entities = {s.entity_ref for s in appspec.surfaces if s.entity_ref}
    for workspace in appspec.workspaces:
        region_sources = {r.source for r in workspace.regions if r.source}
        if not region_sources:
            warnings.append(
                f"Workspace '{workspace.name}' has no regions with entity sources. "
                f"It will not generate any routes or render content."
            )
        elif not region_sources & surface_entities:
            warnings.append(
                f"Workspace '{workspace.name}' references entities "
                f"({', '.join(sorted(region_sources))}) that have no surfaces. "
                f"It will not generate any routes."
            )
    return warnings


def _lint_workspace_access_declarations(appspec: ir.AppSpec) -> list[str]:
    """Warn when a workspace has no access: declaration and personas are defined.

    When personas exist but a workspace carries no explicit ``access:`` block,
    all authenticated users can reach that workspace regardless of their role.
    This is almost never intentional, so we surface it as a lint warning.

    A workspace is considered *declared* if it has an explicit ``access:``
    block with at least one ``allow_personas`` entry, OR if at least one
    persona lists it as its ``default_workspace`` (in which case the runtime
    infers the restriction automatically).
    """
    if not appspec.workspaces or not appspec.personas:
        return []

    # Workspaces claimed by at least one persona's default_workspace
    claimed_by_default: set[str] = {
        p.default_workspace for p in appspec.personas if p.default_workspace
    }

    warnings: list[str] = []
    for workspace in appspec.workspaces:
        if _is_framework_synthetic_name(workspace.name):
            # Framework-synthesised workspace (#824) — auto-generated
            # with correct access spec. Adopters can't add `access:` to
            # something they don't declare, so skip this lint.
            continue
        ws_access = getattr(workspace, "access", None)
        has_explicit_access = bool(ws_access and ws_access.allow_personas)
        if not has_explicit_access and workspace.name not in claimed_by_default:
            warnings.append(
                f"Workspace '{workspace.name}' has no access: declaration and no persona "
                f"lists it as default_workspace. All authenticated users can access it. "
                f"Add 'access: allow_personas [<persona_id>]' or set default_workspace "
                f"on the relevant persona(s)."
            )
    return warnings


def _lint_list_surface_ux(appspec: ir.AppSpec) -> list[str]:
    """Check list surfaces for sort/filter/search/empty completeness.

    Skips framework-synthesised surfaces (names starting with `_`) —
    adopters can't fix missing-ux warnings on surfaces they don't
    declare. See #824.
    """
    warnings: list[str] = []
    for surface in appspec.surfaces:
        if surface.mode != ir.SurfaceMode.LIST:
            continue
        if _is_framework_synthetic_name(surface.name):
            continue
        if not surface.ux:
            hints: list[str] = []
            surf_entity = appspec.get_entity(surface.entity_ref) if surface.entity_ref else None
            if surf_entity:
                filterable = [
                    f.name
                    for f in surf_entity.fields
                    if f.type
                    and f.type.kind in (ir.FieldTypeKind.ENUM, ir.FieldTypeKind.BOOL)
                    and not f.is_primary_key
                ]
                if surf_entity.state_machine:
                    sm_field = surf_entity.state_machine.status_field
                    if sm_field not in filterable:
                        filterable.insert(0, sm_field)
                searchable = [
                    f.name
                    for f in surf_entity.fields
                    if f.type
                    and f.type.kind in (ir.FieldTypeKind.STR, ir.FieldTypeKind.TEXT)
                    and not f.is_primary_key
                ]
                if filterable:
                    hints.append(f"filter: {', '.join(filterable)}")
                if searchable:
                    hints.append(f"search: {', '.join(searchable)}")
            hints.insert(0, "sort: (e.g. created_at desc)")
            hints.append('empty: "No items yet."')
            warnings.append(
                f"Surface '{surface.name}' (mode: list) has no ux block. "
                f"Consider adding: {'; '.join(hints)}"
            )
        else:
            ux = surface.ux
            missing = []
            if not ux.sort:
                missing.append("sort")
            if not ux.filter:
                missing.append("filter")
            if not ux.search:
                missing.append("search")
            if not ux.empty_message:
                missing.append("empty")
            if missing:
                warnings.append(
                    f"Surface '{surface.name}' ux block is missing: "
                    f"{', '.join(missing)}. These enhance DataTable UX."
                )
    return warnings


_INTEGRATION_KEYWORDS = frozenset(
    {
        "api",
        "hmrc",
        "xero",
        "sync",
        "webhook",
        "stripe",
        "twilio",
        "sendgrid",
        "mailgun",
        "slack",
        "zapier",
        "salesforce",
    }
)


def _lint_integration_bindings(appspec: ir.AppSpec) -> list[str]:
    """Check if stories reference integrations without matching service declarations."""
    stories = list(appspec.stories) if appspec.stories else []
    if not stories:
        return []

    warnings: list[str] = []
    declared_integrations = {i.name.lower() for i in appspec.integrations}
    declared_services = {s.name.lower() for s in appspec.domain_services}
    declared_bindings = declared_integrations | declared_services

    for story in stories:
        title_words = set(story.title.lower().split())
        integration_hits = title_words & _INTEGRATION_KEYWORDS

        if integration_hits and not declared_bindings:
            warnings.append(
                f"Story '{story.story_id}' ({story.title}) references integration "
                f"keywords ({', '.join(integration_hits)}) but no integrations or "
                f"services are declared in the DSL."
            )
        elif integration_hits:
            scope_entities = {s.lower() for s in story.scope}
            has_matching_binding = (
                any(
                    any(entity in binding for entity in scope_entities)
                    for binding in declared_bindings
                )
                if scope_entities
                else bool(declared_bindings)
            )

            if not has_matching_binding and scope_entities:
                warnings.append(
                    f"Story '{story.story_id}' references integrations but no "
                    f"service/integration binds to scope entities "
                    f"({', '.join(story.scope)})."
                )
    return warnings


def _lint_process_effects(appspec: ir.AppSpec) -> list[str]:
    """Check process step effects reference valid entities and fields."""
    warnings: list[str] = []
    entity_names = {e.name for e in appspec.domain.entities}

    for process in appspec.processes:
        for step in process.steps:
            for effect in step.effects:
                # Check entity reference
                if effect.entity_name not in entity_names:
                    warnings.append(
                        f"Process '{process.name}' step '{step.name}' effect "
                        f"references non-existent entity '{effect.entity_name}'"
                    )
                    continue

                # Check assignment field paths
                entity = appspec.get_entity(effect.entity_name)
                if entity:
                    entity_field_names = {f.name for f in entity.fields}
                    for assignment in effect.assignments:
                        # Strip entity prefix (e.g. "Task.title" -> "title")
                        field_name = assignment.field_path
                        if "." in field_name:
                            field_name = field_name.split(".", 1)[1]
                        if field_name not in entity_field_names:
                            warnings.append(
                                f"Process '{process.name}' step '{step.name}' effect "
                                f"assignment references non-existent field "
                                f"'{field_name}' on entity '{effect.entity_name}'"
                            )

                # Warn about update without where clause
                if effect.action.value == "update" and not effect.where:
                    warnings.append(
                        f"Process '{process.name}' step '{step.name}' has "
                        f"update effect on '{effect.entity_name}' without "
                        f"a 'where' clause — needs entity ID from context"
                    )

    return warnings


_GOD_ENTITY_FIELD_THRESHOLD = 15


_SOFT_DELETE_NAMES = frozenset({"is_deleted", "deleted", "deleted_at", "archived_at"})


def _lint_modeling_anti_patterns(appspec: ir.AppSpec) -> list[str]:
    """Detect common modeling anti-patterns and emit warnings."""
    warnings: list[str] = []
    entity_names = {e.name.lower() for e in appspec.domain.entities}
    entity_map = {e.name: e for e in appspec.domain.entities}

    for entity in appspec.domain.entities:
        # Framework-synthetic platform entities (FeedbackReport, AIJob, etc.)
        # are code-generated and cannot be decomposed by the app author.
        # Skip modeling anti-pattern warnings on them.
        if getattr(entity, "domain", None) == "platform":
            continue
        field_map = {f.name: f for f in entity.fields}

        # 1. Polymorphic key pairs: *_type (enum) + *_id (uuid)
        for field in entity.fields:
            if field.name.endswith("_type") and field.type.kind == ir.FieldTypeKind.ENUM:
                prefix = field.name.removesuffix("_type")
                sibling_name = f"{prefix}_id"
                sibling = field_map.get(sibling_name)
                if sibling and sibling.type.kind == ir.FieldTypeKind.UUID:
                    # Diagnostic code is the first token so downstream
                    # tooling can grep by code. Alternatives ordered by
                    # cost: separate refs first (cheap, common case),
                    # subtype_of: second (heavier, only when truly IS-A).
                    warnings.append(
                        f"W_LOOKS_POLYMORPHIC: Entity '{entity.name}': fields "
                        f"'{field.name}' + '{sibling_name}' look like a "
                        f"polymorphic key pair. Prefer (in order): "
                        f"1. Separate nullable refs — `post: ref Post` + "
                        f"`photo: ref Photo` — when the set is small + closed. "
                        f"2. subtype_of: — declare a base entity + subtypes "
                        f"if these really form an IS-A hierarchy. "
                        f"Polymorphic key pairs break referential integrity "
                        f"and linker validation."
                    )

        # 1b. Subtype overreach (#1217 Phase 3e.vi): child entity declares
        # subtype_of: but adds <=1 specific field. That shape is almost
        # always cheaper as a flat entity with a discriminator enum.
        # Polymorphism is the escape hatch, not the default — see ADR-0026.
        if entity.subtype_of is not None:
            specific_count = sum(
                1
                for f in entity.fields
                if f.name != "id" and ir.FieldModifier.PK not in (f.modifiers or [])
            )
            if specific_count <= 1:
                warnings.append(
                    f"W_SUBTYPE_OF_OVERREACH: Entity '{entity.name}' subtypes "
                    f"'{entity.subtype_of}' but only adds {specific_count} "
                    f"field(s). Consider modelling as a flat entity with a "
                    f"discriminator enum instead."
                )

        # 2. God entities: too many fields
        meaningful_fields = [
            f
            for f in entity.fields
            if f.name not in ("id", "created_at", "updated_at")
            and ir.FieldModifier.PK not in (f.modifiers or [])
        ]
        if len(meaningful_fields) > _GOD_ENTITY_FIELD_THRESHOLD:
            warnings.append(
                f"Entity '{entity.name}' has {len(meaningful_fields)} fields "
                f"— consider decomposing into smaller entities connected by refs."
            )

        # 3. Soft-delete flags without state machine
        if entity.state_machine is None:
            for field in entity.fields:
                if field.name in _SOFT_DELETE_NAMES:
                    warnings.append(
                        f"Entity '{entity.name}': field '{field.name}' is a soft-delete "
                        f"flag. Prefer a state machine with a terminal state "
                        f"(e.g., 'archived')."
                    )

        # 4. Stringly-typed refs: <entity>_name or <entity>_email
        for field in entity.fields:
            if field.type.kind not in (ir.FieldTypeKind.STR, ir.FieldTypeKind.EMAIL):
                continue
            for suffix in ("_name", "_email"):
                if field.name.endswith(suffix):
                    prefix = field.name.removesuffix(suffix)
                    if prefix.lower() in entity_names and prefix.lower() != entity.name.lower():
                        target = next(
                            (
                                e.name
                                for e in appspec.domain.entities
                                if e.name.lower() == prefix.lower()
                            ),
                            prefix,
                        )
                        warnings.append(
                            f"Entity '{entity.name}': field '{field.name}' looks like "
                            f"a string copy of {target}.{suffix.lstrip('_')}. "
                            f"Use 'ref {target}' instead — the runtime auto-includes related data."
                        )

        # 5. Duplicated ref fields: ref X + x_<field> where <field> exists on X
        for field in entity.fields:
            if field.type.kind != ir.FieldTypeKind.REF or not field.type.ref_entity:
                continue
            target_entity = entity_map.get(field.type.ref_entity)
            if target_entity is None:
                continue  # ref target not found — skip silently
            target_field_names = {f.name for f in target_entity.fields if f.name != "id"}
            ref_lower = field.name.lower()
            for sibling in entity.fields:
                if sibling is field:
                    continue
                if sibling.name.startswith(f"{ref_lower}_"):
                    attr = sibling.name[len(ref_lower) + 1 :]
                    if attr in target_field_names:
                        warnings.append(
                            f"Entity '{entity.name}': field '{sibling.name}' may "
                            f"duplicate {field.type.ref_entity}.{attr} — the ref "
                            f"already provides access via auto-include."
                        )

    return warnings


_GRAPH_EDGE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "source",
        "target",
        "from",
        "to",
        "parent",
        "child",
        "start",
        "end",
        "predecessor",
        "successor",
    }
)


# Audit-metadata token vocabulary (#823). A field that contains any of
# these tokens is almost always a who-did-what audit record — NOT a
# graph-edge endpoint. Fields with BOTH an edge token AND an audit token
# (e.g. `assigned_to`, `reported_from`) are resolved as audit fields and
# excluded from edge candidacy. This catches the false-positive class
# observed by AegisMark where mixed-vocabulary field names — and in
# particular `assigned_to`, `sent_to`, `returned_from` — were flagged as
# graph edges despite being workflow/routing metadata.
_AUDIT_METADATA_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "created",
        "updated",
        "deleted",
        "modified",
        "reviewed",
        "reported",
        "approved",
        "rejected",
        "closed",
        "assigned",
        "reopened",
        "sent",
        "returned",
        "archived",
        "published",
        "signed",
        "acknowledged",
    }
)


def _lint_graph_edge_suggestions(appspec: ir.AppSpec) -> list[str]:
    """Suggest graph_edge: for entities that pair two graph-edge-shaped refs
    to the same target entity.

    Entities with creator + assignee / requester + approver / parent + owner
    are NOT graph edges — those are domain fields that happen to share a
    ref target. Only flag when the field names match the graph-edge
    vocabulary (source/target, from/to, parent/child, ...) AND do not
    overlap with the audit-metadata vocabulary (created, updated, assigned,
    reported, ...) — fields like `assigned_to` that have both an edge token
    and an audit token resolve as audit metadata and are excluded (#823).
    """
    warnings: list[str] = []
    for entity in appspec.domain.entities:
        if entity.graph_edge is not None:
            continue
        # Group ref fields by target entity, and remember which fields
        # landed under each target.
        ref_fields_by_target: dict[str, list[str]] = {}
        for field in entity.fields:
            if field.type.kind == ir.FieldTypeKind.REF and field.type.ref_entity:
                ref_fields_by_target.setdefault(field.type.ref_entity, []).append(field.name)
        for target, field_names in ref_fields_by_target.items():
            if len(field_names) < 2:
                continue

            # A field matches the graph-edge vocabulary if any of its
            # underscore-delimited tokens is a recognised edge term
            # (source_node, target_id, from_station, parent_node, ...)
            # AND none of its tokens is an audit-metadata term (#823:
            # `assigned_to`, `sent_to`, `reported_from` all resolve as
            # audit fields despite carrying an edge token).
            def _is_edge_field(name: str) -> bool:
                tokens = name.lower().split("_")
                has_edge = any(tok in _GRAPH_EDGE_FIELD_NAMES for tok in tokens)
                has_audit = any(tok in _AUDIT_METADATA_FIELD_NAMES for tok in tokens)
                return has_edge and not has_audit

            matches = [n for n in field_names if _is_edge_field(n)]
            if len(matches) >= 2:
                warnings.append(
                    f"Entity '{entity.name}' looks like a graph edge — "
                    f"has {len(field_names)} ref fields to '{target}' "
                    f"({', '.join(sorted(field_names))}). "
                    f"Consider adding graph_edge:"
                )
                break
    return warnings


def _lint_graph_node_suggestions(appspec: ir.AppSpec) -> list[str]:
    """Suggest graph_node: for entities targeted by graph_edge: declarations."""
    warnings: list[str] = []
    entity_map = {e.name: e for e in appspec.domain.entities}
    # Track which entities we've already warned about
    warned: set[str] = set()
    for entity in appspec.domain.entities:
        if entity.graph_edge is None:
            continue
        field_map = {f.name: f for f in entity.fields}
        for field_name in (entity.graph_edge.source, entity.graph_edge.target):
            field = field_map.get(field_name)
            if field and field.type.ref_entity:
                target_ent = entity_map.get(field.type.ref_entity)
                if target_ent and target_ent.graph_node is None and target_ent.name not in warned:
                    warnings.append(
                        f"'{entity.name}' targets '{target_ent.name}' — "
                        f"consider adding graph_node: for discoverability"
                    )
                    warned.add(target_ent.name)
    return warnings


def _lint_fk_targets_missing_display_field(appspec: ir.AppSpec) -> list[str]:
    """Warn when FK-target entities lack display_field (#652).

    Entities referenced by ``ref`` fields on other entities should declare
    ``display_field:`` so that FK references render as human-readable text
    instead of raw UUIDs. Junction entities (2+ required ref fields, no
    str/text fields) are skipped since they rarely have a meaningful name.
    """
    warnings: list[str] = []
    entities_by_name: dict[str, ir.EntitySpec] = {e.name: e for e in appspec.domain.entities}

    # Build map: entity_name → list of "Entity.field" references
    fk_refs: dict[str, list[str]] = {}
    for entity in appspec.domain.entities:
        for field in entity.fields:
            kind = getattr(field.type, "kind", None)
            kind_val = kind.value if hasattr(kind, "value") else str(kind)  # type: ignore[union-attr]
            ref_target = getattr(field.type, "ref_entity", None)
            if kind_val in ("ref", "belongs_to") and ref_target:
                fk_refs.setdefault(ref_target, []).append(f"{entity.name}.{field.name}")

    for target_name, refs in sorted(fk_refs.items()):
        target = entities_by_name.get(target_name)
        if target is None:
            continue
        if target.display_field:
            continue

        # Skip junction entities: 2+ required ref fields, no str/text fields
        ref_count = 0
        has_text_field = False
        for f in target.fields:
            fk = getattr(f.type, "kind", None)
            fk_val = fk.value if hasattr(fk, "value") else str(fk)  # type: ignore[union-attr]
            if fk_val in ("ref", "belongs_to") and f.is_required:
                ref_count += 1
            scalar = getattr(f.type, "scalar_type", None)
            if scalar and str(scalar) in ("str", "text", "ScalarType.STR", "ScalarType.TEXT"):
                has_text_field = True
        if ref_count >= 2 and not has_text_field:
            continue

        # Suggest a candidate field
        candidate = None
        for name in ("name", "title", "label"):
            if any(f.name == name for f in target.fields):
                candidate = name
                break
        if candidate is None:
            for f in target.fields:
                scalar = getattr(f.type, "scalar_type", None)
                if scalar and str(scalar) in ("str", "ScalarType.STR"):
                    candidate = f.name
                    break

        ref_list = ", ".join(refs[:5])
        if len(refs) > 5:
            ref_list += f", ... ({len(refs)} total)"
        msg = (
            f"Entity '{target_name}' is referenced as FK by {len(refs)} field(s) "
            f"but has no display_field."
        )
        if candidate:
            msg += f"\n  Suggested: display_field: {candidate}"
        msg += f"\n  FK references: {ref_list}"
        warnings.append(msg)

    return warnings


def _lint_nav_group_icon_consistency(appspec: ir.AppSpec) -> list[str]:
    """Warn when a nav_group mixes items with and without `icon:`.

    A nav_group with some items that declare `icon:` and some that don't
    renders as a visually inconsistent list — iconed items have a flush
    icon + label, iconless items have a blank gutter where the icon
    would be. Pick one: either every item in the group carries an
    icon, or none do. Asked for in issue #796.
    """
    warnings: list[str] = []
    for workspace in appspec.workspaces:
        for group in workspace.nav_groups:
            if not group.items:
                continue
            iconed = [it for it in group.items if it.icon]
            iconless = [it for it in group.items if not it.icon]
            if iconed and iconless:
                iconless_names = ", ".join(it.entity for it in iconless)
                warnings.append(
                    f"Workspace '{workspace.name}' nav_group '{group.label}' "
                    f"mixes iconed and iconless items — {iconless_names} "
                    f"have no icon while siblings do. Add `icon:` to all items "
                    f"in the group, or remove it from all, for consistent "
                    f"sidebar alignment."
                )
    return warnings


def extended_lint(appspec: ir.AppSpec) -> list[str]:
    """Extended lint rules for code quality.

    Dispatches to focused checkers for naming, titles, workspace
    personas, routing, list-surface UX, and integration bindings.
    Dead-construct detection is handled by :func:`_detect_dead_constructs`.
    """
    warnings: list[str] = []
    warnings.extend(_lint_naming_conventions(appspec))
    warnings.extend(_detect_dead_constructs(appspec))
    warnings.extend(_lint_missing_titles(appspec))
    warnings.extend(_validate_persona_backed_by(appspec))
    warnings.extend(_lint_workspace_personas(appspec))
    warnings.extend(_lint_workspace_routing(appspec))
    warnings.extend(_lint_workspace_access_declarations(appspec))
    warnings.extend(_lint_list_surface_ux(appspec))
    warnings.extend(_lint_nav_group_icon_consistency(appspec))
    warnings.extend(_lint_integration_bindings(appspec))
    warnings.extend(_lint_process_effects(appspec))
    warnings.extend(_lint_modeling_anti_patterns(appspec))
    warnings.extend(_lint_graph_edge_suggestions(appspec))
    warnings.extend(_lint_graph_node_suggestions(appspec))
    warnings.extend(_lint_fk_targets_missing_display_field(appspec))
    return warnings
