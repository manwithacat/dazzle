"""Region aggregate validation: where a region `filter:` reaches (#1773)."""

from .. import ir


def validate_region_filter_aggregate_reach(
    appspec: ir.AppSpec,
) -> tuple[list[str], list[str]]:
    """Warn when a region `filter:` cannot narrow one of its aggregates (#1773).

    The runtime composes the compiled region `filter:` into every aggregate
    over the region's own `source:` entity. An aggregate over a *different*
    entity stays filter-free — the filter names source columns the other
    table doesn't have — so `count(Note)` on a `filter: status = open`
    Invoice region counts every note in scope. Flag it when the aggregate
    has no `where` of its own, so the author narrows it explicitly.
    """
    warnings: list[str] = []
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.filter is None or not region.aggregates or not region.source:
                continue
            source_name = region.source.split(".")[0]
            label = f"Workspace '{workspace.name}' region '{region.name or region.source}'"
            for metric, ref in region.aggregates.items():
                if not isinstance(ref, ir.AggregateRef) or ref.where is not None:
                    continue
                if ref.entity and ref.entity != source_name:
                    warnings.append(
                        f"W_REGION_FILTER_NOT_ON_AGGREGATE: {label} aggregate `{metric}` "
                        f"counts {ref.entity}, so the region `filter:` (on {source_name}) "
                        f"does not narrow it. Add a `where` to the aggregate if it should."
                    )
    return [], warnings


def _pivot_measure_error(
    label: str, metric: str, ref: ir.AggregateRef, source_name: str, first_where: object
) -> str | None:
    if (ref.entity and ref.entity != source_name) or (ref.func == "count" and not ref.entity):
        return (
            f"E_PIVOT_MEASURE_CROSS_ENTITY: {label} measure `{metric}` aggregates "
            f"{ref.entity or '(none)'}, but a pivot is one GROUP BY over its source "
            f"{source_name}. Use count({source_name}) or sum/avg/min/max of a "
            f"{source_name} column."
        )
    if ref.window is not None or _references_current_bucket(ref.where):
        return (
            f"E_PIVOT_MEASURE_UNSUPPORTED: {label} measure `{metric}` uses "
            f"`window` or `current_bucket`; a pivot cell is bounded by its two "
            f"dimensions only."
        )
    if ref.where != first_where:
        return (
            f"E_PIVOT_MEASURE_WHERE_MISMATCH: {label} measure `{metric}` has a "
            f"different `where` from the first measure. Every measure in one pivot "
            f"shares a single GROUP BY, so they must share one `where` (or move the "
            f"narrowing into the region `filter:`)."
        )
    return None


def _references_current_bucket(where: ir.ConditionExpr | None) -> bool:
    if where is None:
        return False
    if where.is_compound:
        return _references_current_bucket(where.left) or _references_current_bucket(where.right)
    cmp = where.comparison
    return cmp is not None and bool(cmp.value.current_bucket)


def validate_pivot_measures(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Check every `pivot_table` measure fits one GROUP BY over the source (#1800).

    A pivot takes count / sum / avg / min / max measures (and derived metrics
    over them) — each computed by one scope-aware GROUP BY over both
    dimensions. A cross-entity aggregate, a `window`, a `current_bucket`
    sentinel or a `where` that differs between measures cannot ride that
    query; the runtime would skip the pivot, so it is an error here.
    """
    errors: list[str] = []
    for workspace in appspec.workspaces:
        for region in workspace.regions:
            if region.display != ir.DisplayMode.PIVOT_TABLE or not region.source:
                continue
            refs = [
                (m, r)
                for m, r in (region.aggregates or {}).items()
                if isinstance(r, ir.AggregateRef)
            ]
            if not refs:
                continue
            source_name = region.source.split(".")[0]
            label = f"Workspace '{workspace.name}' region '{region.name or region.source}'"
            first_where = refs[0][1].where
            for metric, ref in refs:
                error = _pivot_measure_error(label, metric, ref, source_name, first_where)
                if error is not None:
                    errors.append(error)
    return errors, []
