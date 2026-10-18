"""Surface ``title:`` templates and ``ux: breadcrumb:`` trails (#1815, #1810).

- ``title:`` belongs to ``mode: view`` surfaces (the only page with a record
  to interpolate) — ``E_SURFACE_TITLE_MODE`` elsewhere.
- Every placeholder names an entity field or a ``ref.field`` /
  ``ref.ref.field`` path whose every hop is a ref (#1825;
  ``E_TEMPLATE_UNKNOWN_FIELD`` / ``E_TEMPLATE_PATH_NOT_REF`` /
  ``E_TEMPLATE_NO_ENTITY``); ``|label`` takes an enum field
  (``E_TEMPLATE_LABEL_NOT_ENUM``).
- Breadcrumb labels interpolate only on view surfaces
  (``E_BREADCRUMB_PLACEHOLDER_MODE``); a ``-> target`` names a declared surface
  or workspace (``E_BREADCRUMB_DEAD_TARGET``). A target whose page needs a
  record id (view / edit) takes a row-bound path, ``-> x_detail({ref.ref})``
  (#1825), ending in a ref to that surface's entity
  (``E_BREADCRUMB_TARGET_NEEDS_ROW`` without one, ``E_BREADCRUMB_ROW_ENTITY``
  for the wrong entity, ``E_BREADCRUMB_TARGET_TAKES_NO_ROW`` on a list surface
  or workspace); the last crumb is the current page and takes no target
  (``E_BREADCRUMB_LEAF_LINK``).
- ``breadcrumb:`` is a surface directive (``E_BREADCRUMB_WORKSPACE``).
"""

from .. import ir

_REF_KINDS = (ir.FieldTypeKind.REF, ir.FieldTypeKind.BELONGS_TO)
_ROW_MODES = (ir.SurfaceMode.VIEW, ir.SurfaceMode.EDIT)


def _resolve_path(
    where: str, dotted: str, path: tuple[str, ...], entity: ir.EntitySpec, appspec: ir.AppSpec
) -> tuple[str | None, ir.FieldSpec | None]:
    """Walk ``path`` from ``entity``: every segment but the last must be a ref.

    Returns ``(error, last_field)``; ``last_field`` is ``None`` when the walk
    left the known entities (a ref to an undeclared entity is the linker's
    concern, not this check's).
    """
    current: ir.EntitySpec | None = entity
    last: ir.FieldSpec | None = None
    for i, name in enumerate(path):
        if current is None:
            return None, None
        last = next((f for f in current.fields if f.name == name), None)
        if last is None:
            return (
                f"E_TEMPLATE_UNKNOWN_FIELD: {where}: `{{{dotted}}}` — entity "
                f"'{current.name}' has no field '{name}'."
            ), None
        if i == len(path) - 1:
            break
        if last.type.kind not in _REF_KINDS or not last.type.ref_entity:
            return (
                f"E_TEMPLATE_PATH_NOT_REF: {where}: `{{{dotted}}}` — "
                f"'{current.name}.{name}' is not a ref field, so it has no "
                f"'.{path[i + 1]}'."
            ), None
        current = appspec.domain.get_entity(last.type.ref_entity)
    return None, last


def _placeholder_error(
    where: str, ph: ir.TemplatePlaceholder, entity: ir.EntitySpec, appspec: ir.AppSpec
) -> str | None:
    dotted = ".".join(ph.path)
    error, last = _resolve_path(where, dotted, ph.path, entity, appspec)
    if error is not None:
        return error
    if "label" in ph.filters and last is not None and last.type.kind != ir.FieldTypeKind.ENUM:
        return (
            f"E_TEMPLATE_LABEL_NOT_ENUM: {where}: `{{{dotted}|label}}` — '{last.name}' is "
            f"{last.type.kind.value}, not an enum; `|label` prints an enum value's label."
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


def _crumb_target_error(
    where: str,
    crumb: ir.BreadcrumbCrumbSpec,
    entity: ir.EntitySpec | None,
    appspec: ir.AppSpec,
) -> str | None:
    target = crumb.target
    surface = next((s for s in appspec.surfaces if s.name == target), None)
    if surface is None:
        if any(w.name == target for w in appspec.workspaces):
            return _row_arg_unwanted(where, crumb)
        return (
            f"E_BREADCRUMB_DEAD_TARGET: {where} links to '{target}', which is not a "
            f"declared surface or workspace."
        )
    if surface.mode not in _ROW_MODES:
        return _row_arg_unwanted(where, crumb)
    if crumb.target_row is None:
        return (
            f"E_BREADCRUMB_TARGET_NEEDS_ROW: {where} links to '{target}' (mode: "
            f"{surface.mode.value}), whose page needs a record id. Bind the row with "
            f"`-> {target}({{ref_field}})`, or link a list surface or a workspace."
        )
    return _row_arg_error(where, crumb.target_row, surface, entity, appspec)


def _row_arg_unwanted(where: str, crumb: ir.BreadcrumbCrumbSpec) -> str | None:
    if crumb.target_row is None:
        return None
    return (
        f"E_BREADCRUMB_TARGET_TAKES_NO_ROW: {where} binds a row "
        f"({{{'.'.join(crumb.target_row)}}}) to '{crumb.target}', whose page takes no "
        f"record id. Drop the `(...)`."
    )


def _row_arg_error(
    where: str,
    path: tuple[str, ...],
    target: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
    appspec: ir.AppSpec,
) -> str | None:
    """A row-bound link's path is a chain of refs ending at the target's entity (#1825)."""
    dotted = ".".join(path)
    if entity is None:
        return (
            f"E_TEMPLATE_NO_ENTITY: {where} binds a row ({{{dotted}}}) but the surface "
            f"has no `uses entity`."
        )
    error, last = _resolve_path(where, dotted, path, entity, appspec)
    if error is not None or last is None:
        return error
    expected = target.entity_ref
    if last.type.kind not in _REF_KINDS or last.type.ref_entity != expected:
        actual = last.type.ref_entity if last.type.kind in _REF_KINDS else last.type.kind.value
        return (
            f"E_BREADCRUMB_ROW_ENTITY: {where} binds `{{{dotted}}}` to '{target.name}', "
            f"which shows {expected}; the path must end in a ref to {expected} "
            f"(it ends in {actual})."
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
        if crumb.target_row is not None and surface.mode != ir.SurfaceMode.VIEW:
            errors.append(
                f"E_BREADCRUMB_PLACEHOLDER_MODE: {where} binds a row "
                f"({{{'.'.join(crumb.target_row)}}}), but only mode: view surfaces have a "
                f"record to bind."
            )
            continue
        if crumb.target is None:
            continue
        if i == last:
            errors.append(
                f"E_BREADCRUMB_LEAF_LINK: {where} is the current page and cannot link "
                f"(-> {crumb.target}). Drop the target or add a crumb after it."
            )
            continue
        target_error = _crumb_target_error(where, crumb, entity, appspec)
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
