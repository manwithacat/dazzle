"""WorkspaceRegionContext — the per-region context bundle.

Extracted from workspace_rendering.py in #1057 cut 5 (v0.67.104).
Lives in its own module so async fetchers + scope-filter helpers
can depend on the dataclass without pulling in the rest of
workspace_rendering (which would create a circular import).

The dataclass aggregates everything a region handler needs that
isn't request-shaped (paging, query params). Built once per
region at workspace-route construction time, then passed by
reference into the handler closure.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkspaceRegionContext:
    """Bundles the non-request, non-pagination context for a workspace region handler."""

    ctx_region: Any
    ir_region: Any
    source: str
    entity_spec: Any
    attention_signals: list[Any]
    ws_access: Any
    repositories: dict[str, Any]
    require_auth: bool
    auth_middleware: Any
    # Pre-computed at startup (constant-folded from IR)
    precomputed_columns: list[dict[str, Any]] = field(default_factory=list)
    # Pre-computed ref relation names for eager-loading (from entity_auto_includes)
    auto_include: list[str] = field(default_factory=list)
    # Surface UX metadata (#362)
    surface_default_sort: list[Any] = field(default_factory=list)
    surface_empty_message: str = ""
    # Runtime parameter resolution (#572)
    param_resolver: Any = None  # ParamResolver | None
    tenant_id: str | None = None
    # Entity access spec for scope predicate enforcement (#574)
    cedar_access_spec: Any = None
    fk_graph: Any = None
    # DSL user entity name for current_user resolution (#588)
    user_entity_name: str = "User"
    # #1015 (v0.67.16) — per-entity access specs for multi-source
    # task_inbox fan-out. Maps entity name → access spec so each
    # source can apply its own scope rules at fetch time. Default
    # empty dict keeps single-source paths cost-free.
    entity_access_specs: dict[str, Any] = field(default_factory=dict)
    # #1232 — per-entity FK → target-entity maps for dotted-path
    # filter resolution in task_inbox sources (and any other path
    # that needs to call _extract_condition_filters with a non-None
    # ref_targets). Maps entity_name → {fk_field: target_entity}.
    # Default empty dict keeps callers that don't need it cost-free;
    # the workspace builder threads ServerConfig.entity_ref_targets.
    entity_ref_targets: dict[str, dict[str, str]] = field(default_factory=dict)
    # #1233 — row_action action_id → POST URL map. The renderer emits
    # this URL on the [data-dz-row-action] button as
    # ``data-dz-row-action-url`` so the client-side JS can POST without
    # re-deriving the route. Built once at WorkspaceRouteBuilder init
    # from appspec.surfaces; empty dict means no row_action surfaces
    # in this app (cost-free).
    row_action_routes: dict[str, str] = field(default_factory=dict)
    # #1303 — resolved per-row drill-to-detail URL template for row-oriented
    # displays (list, task_inbox), e.g. "/app/assessment-event/{id}". Set by
    # WorkspaceRouteBuilder when the region's source entity has a VIEW surface
    # AND the region didn't opt out via `drill: none`; empty string means no
    # row links. The list/task_inbox adapters substitute "{id}" per row.
    detail_url_template: str = ""
    # #1303 — entity_name → detail-URL template map for MULTI-source
    # task_inbox regions (where each source is a different entity, so the
    # single `detail_url_template` above isn't enough). Drill-gated the same
    # way (empty when the region set `drill: none`). The task_inbox builder
    # looks up each source's template by entity name.
    entity_detail_urls: dict[str, str] = field(default_factory=dict)
    # dual_pane_flow master-detail: list rows hx-get into the sibling detail
    # pane (``.dz-master-detail__detail``) instead of full-page body drill.
    # When True, ``detail_url_template`` points at the DETAIL region endpoint
    # with ``?id={id}`` and list rows emit pane-target HTMX attrs.
    master_detail_pane: bool = False
