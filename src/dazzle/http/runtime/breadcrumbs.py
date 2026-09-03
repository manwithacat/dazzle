"""
Breadcrumb trail derivation from URL paths.

Compatibility facade — implementation lives in pure ``dazzle.render.breadcrumbs``
so app chrome can mount the HM Breadcrumb fragment without crossing the
render ↛ http layer boundary.
"""

from __future__ import annotations

from dazzle.render.breadcrumbs import (
    Crumb,
    build_breadcrumb_trail,
    build_shell_breadcrumb,
    clerk_bulk_selection_noun,
    clerk_empty_chart_title,
    clerk_empty_collection_title,
    clerk_empty_filtered_title,
    clerk_empty_loading_title,
    clerk_entity_confirm_noun,
    clerk_entity_download_stem,
    clerk_entity_noun,
    clerk_entity_path_label,
    clerk_entity_title,
    clerk_list_empty_kind,
    clerk_pagination_rows_label,
    clerk_related_create_noun,
    clerk_related_empty_title,
    crumbs_to_breadcrumb,
    entity_path_labels_from_spec,
)

__all__ = [
    "Crumb",
    "build_breadcrumb_trail",
    "build_shell_breadcrumb",
    "clerk_bulk_selection_noun",
    "clerk_empty_chart_title",
    "clerk_empty_collection_title",
    "clerk_empty_filtered_title",
    "clerk_empty_loading_title",
    "clerk_entity_confirm_noun",
    "clerk_entity_download_stem",
    "clerk_entity_noun",
    "clerk_entity_path_label",
    "clerk_entity_title",
    "clerk_list_empty_kind",
    "clerk_pagination_rows_label",
    "clerk_related_create_noun",
    "clerk_related_empty_title",
    "crumbs_to_breadcrumb",
    "entity_path_labels_from_spec",
]
