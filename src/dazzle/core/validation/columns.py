"""List-column validation: region `columns:` / `page_size:` and surface hints (#1792)."""

from .. import ir

# #1792: region displays that project their rows through `columns:`.
_COLUMN_DISPLAYS = frozenset(
    {
        ir.DisplayMode.LIST,
        ir.DisplayMode.AUTO,
        ir.DisplayMode.QUEUE,
        ir.DisplayMode.GRID,
        ir.DisplayMode.KANBAN,
        ir.DisplayMode.TIMELINE,
    }
)
# ... and the ones that lay them out as a table (width / truncate apply).
_TABLE_DISPLAYS = frozenset({ir.DisplayMode.LIST, ir.DisplayMode.AUTO})


def _region_source_entity(appspec: ir.AppSpec, source: str | None) -> ir.EntitySpec | None:
    """The entity a region lists — its `source:` entity, or a source surface's entity."""
    if not source:
        return None
    entity = appspec.get_entity(source)
    if entity is not None:
        return entity
    surface = next((s for s in appspec.surfaces if s.name == source), None)
    if surface is not None and surface.entity_ref:
        return appspec.get_entity(surface.entity_ref)
    return None


def _validate_region_columns(
    appspec: ir.AppSpec, region: ir.WorkspaceRegion, label: str
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for col in region.columns:
        if col.field in seen:
            errors.append(
                f"E_COLUMNS_DUPLICATE: {label} `columns:` names '{col.field}' more than once."
            )
        seen.add(col.field)
    if region.sources:
        warnings.append(
            f"{label} `columns:` is ignored on a multi-source region — each tab "
            "keeps its own source's columns."
        )
        return errors, warnings
    entity = _region_source_entity(appspec, region.source)
    if entity is None:
        errors.append(
            f"E_COLUMNS_NO_ENTITY: {label} `columns:` needs a `source:` entity "
            "(or a source surface bound to one) to name fields from."
        )
        return errors, warnings
    field_names = {f.name for f in entity.fields}
    for col in region.columns:
        if col.field not in field_names:
            errors.append(
                f"E_COLUMNS_UNKNOWN_FIELD: {label} `columns:` names '{col.field}', which is "
                f"not a field on {entity.name} (fields: {', '.join(sorted(field_names))}). "
                "Dotted paths are not supported; a ref field shows the related "
                "record's display name."
            )
    if region.display not in _COLUMN_DISPLAYS:
        warnings.append(
            f"{label} `columns:` is ignored by `display: {region.display.value}` — only "
            "list, queue, grid, kanban and timeline project their rows through columns."
        )
    elif region.display not in _TABLE_DISPLAYS and any(c.has_hints for c in region.columns):
        warnings.append(
            f"{label} column `width:` / `truncate` hints only apply to `display: list`; "
            f"`display: {region.display.value}` ignores them."
        )
    return errors, warnings


def validate_list_columns(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate region `columns:` / `page_size:` and surface column hints (#1792)."""
    errors: list[str] = []
    warnings: list[str] = []
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            label = f"Workspace '{workspace.name}' region '{region.name or region.source}'"
            if region.page_size is not None and region.limit is not None:
                errors.append(
                    f"E_REGION_PAGE_SIZE_LIMIT: {label} sets both `limit:` and `page_size:`. "
                    "`limit:` caps the rows with no pager; `page_size:` pages through every "
                    "matching row. Pick one."
                )
            if region.page_size is not None and region.display not in _TABLE_DISPLAYS:
                warnings.append(
                    f"{label} `page_size:` only pages `display: list`; "
                    f"`display: {region.display.value}` fetches that many rows with no pager."
                )
            if region.columns:
                errs, warns = _validate_region_columns(appspec, region, label)
                errors.extend(errs)
                warnings.extend(warns)
    for surface in appspec.surfaces:
        if surface.mode == ir.SurfaceMode.LIST:
            continue
        label = f"Surface '{surface.name}'"
        if surface.page_size is not None:
            warnings.append(
                f"{label} `page_size:` only applies to `mode: list` (got {surface.mode.value})."
            )
        hinted = [c.field for c in surface.list_columns() if c.has_hints]
        if hinted:
            warnings.append(
                f"{label} field `width:` / `truncate` hints only apply to `mode: list` "
                f"(on {', '.join(hinted)})."
            )
    return errors, warnings
