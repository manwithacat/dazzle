"""Surface ``title:`` templates and ``ux: breadcrumb:`` trails (#1815, #1810).

- ``title:`` belongs to ``mode: view`` surfaces (the only page with a record
  to interpolate) — ``E_SURFACE_TITLE_MODE`` elsewhere.
- Every placeholder names an entity field or a one-hop ``ref.field`` path
  (``E_TEMPLATE_UNKNOWN_FIELD`` / ``E_TEMPLATE_PATH_NOT_REF`` /
  ``E_TEMPLATE_NO_ENTITY``).
- Breadcrumb labels interpolate only on view surfaces
  (``E_BREADCRUMB_PLACEHOLDER_MODE``); a ``-> target`` names a declared surface
  or workspace (``E_BREADCRUMB_DEAD_TARGET``) whose page needs no record id
  (``E_BREADCRUMB_TARGET_NEEDS_ROW``); the last crumb is the current page and
  takes no target (``E_BREADCRUMB_LEAF_LINK``).
- ``breadcrumb:`` is a surface directive (``E_BREADCRUMB_WORKSPACE``).
"""

from .. import ir

_REF_KINDS = (ir.FieldTypeKind.REF, ir.FieldTypeKind.BELONGS_TO)
_ROW_MODES = (ir.SurfaceMode.VIEW, ir.SurfaceMode.EDIT)


def _placeholder_error(
    where: str, ph: ir.TemplatePlaceholder, entity: ir.EntitySpec, appspec: ir.AppSpec
) -> str | None:
    dotted = ".".join(ph.path)
    head = next((f for f in entity.fields if f.name == ph.path[0]), None)
    if head is None:
        return (
            f"E_TEMPLATE_UNKNOWN_FIELD: {where}: `{{{dotted}}}` — entity '{entity.name}' "
            f"has no field '{ph.path[0]}'."
        )
    if len(ph.path) == 1:
        return None
    if head.type.kind not in _REF_KINDS or not head.type.ref_entity:
        return (
            f"E_TEMPLATE_PATH_NOT_REF: {where}: `{{{dotted}}}` — '{entity.name}.{ph.path[0]}' "
            f"is not a ref field, so it has no '.{ph.path[1]}'."
        )
    target = appspec.domain.get_entity(head.type.ref_entity)
    if target is not None and not any(f.name == ph.path[1] for f in target.fields):
        return (
            f"E_TEMPLATE_UNKNOWN_FIELD: {where}: `{{{dotted}}}` — entity '{target.name}' "
            f"has no field '{ph.path[1]}'."
        )
    return None


def _template_errors(
    where: str, template: ir.TextTemplate, entity: ir.EntitySpec | None, appspec: ir.AppSpec
) -> list[str]:
    if template.is_static:
        return []
    if entity is None:
        return [
            f"E_TEMPLATE_NO_ENTITY: {where} interpolates {template.source!r} but the "
            f"surface has no `uses entity`."
        ]
    found = (_placeholder_error(where, ph, entity, appspec) for ph in template.placeholders)
    return [e for e in found if e is not None]


def _title_errors(
    surface: ir.SurfaceSpec, entity: ir.EntitySpec | None, appspec: ir.AppSpec
) -> list[str]:
    template = surface.title_template
    if template is None:
        return []
    if surface.mode != ir.SurfaceMode.VIEW:
        return [
            f"E_SURFACE_TITLE_MODE: surface '{surface.name}' declares `title:` but is "
            f"mode: {surface.mode.value}; a record-interpolating title is for mode: view "
            f"surfaces. Put a static title in the header string."
        ]
    return _template_errors(f"surface '{surface.name}' title", template, entity, appspec)


def _crumb_target_error(where: str, target: str, appspec: ir.AppSpec) -> str | None:
    surface = next((s for s in appspec.surfaces if s.name == target), None)
    if surface is None:
        if any(w.name == target for w in appspec.workspaces):
            return None
        return (
            f"E_BREADCRUMB_DEAD_TARGET: {where} links to '{target}', which is not a "
            f"declared surface or workspace."
        )
    if surface.mode in _ROW_MODES:
        return (
            f"E_BREADCRUMB_TARGET_NEEDS_ROW: {where} links to '{target}' (mode: "
            f"{surface.mode.value}), whose page needs a record id. Link a list surface "
            f"or a workspace."
        )
    return None


def _breadcrumb_errors(
    surface: ir.SurfaceSpec, entity: ir.EntitySpec | None, appspec: ir.AppSpec
) -> list[str]:
    trail = surface.ux.breadcrumb if surface.ux is not None else None
    if trail is None or trail.off:
        return []
    errors: list[str] = []
    last = len(trail.crumbs) - 1
    for i, crumb in enumerate(trail.crumbs):
        where = f"surface '{surface.name}' breadcrumb crumb {crumb.label.source!r}"
        if crumb.label.is_static or surface.mode == ir.SurfaceMode.VIEW:
            errors.extend(_template_errors(where, crumb.label, entity, appspec))
        else:
            errors.append(
                f"E_BREADCRUMB_PLACEHOLDER_MODE: {where} interpolates, but only mode: view "
                f"surfaces have a record to interpolate."
            )
        if crumb.target is None:
            continue
        if i == last:
            errors.append(
                f"E_BREADCRUMB_LEAF_LINK: {where} is the current page and cannot link "
                f"(-> {crumb.target}). Drop the target or add a crumb after it."
            )
            continue
        target_error = _crumb_target_error(where, crumb.target, appspec)
        if target_error is not None:
            errors.append(target_error)
    return errors


def validate_surface_titles_and_breadcrumbs(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Check surface ``title:`` templates and ``ux: breadcrumb:`` trails (module doc).

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    for surface in appspec.surfaces:
        entity = appspec.domain.get_entity(surface.entity_ref) if surface.entity_ref else None
        errors.extend(_title_errors(surface, entity, appspec))
        errors.extend(_breadcrumb_errors(surface, entity, appspec))
    errors.extend(
        f"E_BREADCRUMB_WORKSPACE: workspace '{w.name}' declares `ux: breadcrumb:`, which "
        f"is a surface directive."
        for w in appspec.workspaces
        if w.ux is not None and w.ux.breadcrumb is not None
    )
    return errors, []
