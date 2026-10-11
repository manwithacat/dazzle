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
