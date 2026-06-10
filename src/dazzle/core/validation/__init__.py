"""Semantic validation package for DAZZLE AppSpec.

Decomposed mechanically from the former 4,100-line dazzle.core.validator
module per #1361. Each module owns one cohesive validation concern:

- ``entities`` — Entity-level semantic validation (fields, PKs, constraints, reserved names).
- ``surfaces`` — Surface and experience validation.
- ``integrations`` — Service, foreign-model, integration, webhook, and notification validation.
- ``ux`` — UX-spec, navigation, and workspace-action validation.
- ``conditions`` — Shared condition-expression helpers used across validation modules.
- ``financial`` — Money-field, account-code, transaction, and ledger validation.
- ``events`` — Event payload secret-leak validation.
- ``extended`` — Extended lint checks (dead constructs, naming, anti-patterns, suggestions).
- ``flows`` — Atomic flow, transition, approval, SLA, and process-step validation.
- ``governance`` — Audit-config, governance-policy, and sensitive-field validation.
- ``rbac`` — Scope-predicate, role-reference, and RBAC-diagnostic validation.
- ``graphs`` — Graph-declaration, lifecycle, fitness, and storage-ref validation.
- ``tenancy`` — Tenancy partition-key and tenant-host validation.
- ``appspec_checks`` — The validate_appspec aggregator over all validation modules.

``dazzle.core.validator`` remains the stable import seam and re-exports
everything here.
"""

from .appspec_checks import (
    validate_appspec,
)
from .conditions import (
    _condition_field_references,
    _validate_condition_fields,
    _walk_role_names,
)
from .entities import (
    DECIMAL_PRECISION_MAX,
    DECIMAL_PRECISION_MIN,
    SECRET_FIELD_PATTERNS,
    SQL_RESERVED_WORDS,
    STRING_MAX_LENGTH_MIN,
    STRING_MAX_LENGTH_WARN_THRESHOLD,
    _validate_constraints,
    _validate_entity_pk,
    _validate_field_decimals,
    _validate_field_duplicates,
    _validate_field_enums,
    _validate_field_modifiers,
    _validate_field_strings,
    _validate_profile_archetype,
    _validate_reserved_names,
    is_secret_field_name,
    validate_entities,
)
from .events import (
    validate_event_payload_secrets,
)
from .extended import (
    _AUDIT_METADATA_FIELD_NAMES,
    _GOD_ENTITY_FIELD_THRESHOLD,
    _GRAPH_EDGE_FIELD_NAMES,
    _INTEGRATION_KEYWORDS,
    _SOFT_DELETE_NAMES,
    _detect_dead_constructs,
    _is_framework_synthetic_name,
    _lint_fk_targets_missing_display_field,
    _lint_graph_edge_suggestions,
    _lint_graph_node_suggestions,
    _lint_integration_bindings,
    _lint_list_surface_ux,
    _lint_missing_titles,
    _lint_modeling_anti_patterns,
    _lint_naming_conventions,
    _lint_nav_group_icon_consistency,
    _lint_process_effects,
    _lint_workspace_access_declarations,
    _lint_workspace_personas,
    _lint_workspace_routing,
    _validate_persona_backed_by,
    extended_lint,
)
from .financial import (
    _validate_account_codes,
    _validate_transaction_transfers,
    validate_ledgers,
    validate_money_fields,
)
from .flows import (
    validate_approvals,
    validate_atomic_flows,
    validate_process_step_service_refs,
    validate_slas,
    validate_transition_invocations,
)
from .governance import (
    validate_audit_config,
    validate_governance_policies,
    validate_sensitive_fields,
)
from .graphs import (
    _NUMERIC_FIELD_TYPES,
    _validate_graph_edge,
    _validate_graph_node,
    validate_fitness_repr_fields,
    validate_graph_declarations,
    validate_lifecycles,
    validate_storage_refs,
)
from .integrations import (
    validate_foreign_models,
    validate_integrations,
    validate_notifications,
    validate_services,
    validate_webhooks,
)
from .rbac import (
    _VISIBILITY_BOOL_FIELD_NAMES,
    _find_user_role_enum,
    _validate_predicate_node,
    validate_admin_personas_scope_conflict,
    validate_rbac_matrix_diagnostics,
    validate_role_references_against_enum,
    validate_scope_predicates,
    validate_visibility_bool_field_scope_coverage,
)
from .surfaces import (
    validate_experiences,
    validate_surfaces,
)
from .tenancy import (
    _get_entities,
    validate_tenancy_partition_key,
    validate_tenant_host_blocks,
)
from .ux import (
    _TENANT_CONFIG_PREFIX,
    _collect_tenant_config_refs,
    validate_nav_curation,
    validate_persona_nav_refs,
    validate_ux_specs,
    validate_workspace_primary_actions,
    validate_workspace_region_actions,
)

__all__ = [
    "DECIMAL_PRECISION_MAX",
    "DECIMAL_PRECISION_MIN",
    "SECRET_FIELD_PATTERNS",
    "SQL_RESERVED_WORDS",
    "STRING_MAX_LENGTH_MIN",
    "STRING_MAX_LENGTH_WARN_THRESHOLD",
    "_AUDIT_METADATA_FIELD_NAMES",
    "_GOD_ENTITY_FIELD_THRESHOLD",
    "_GRAPH_EDGE_FIELD_NAMES",
    "_INTEGRATION_KEYWORDS",
    "_NUMERIC_FIELD_TYPES",
    "_SOFT_DELETE_NAMES",
    "_TENANT_CONFIG_PREFIX",
    "_VISIBILITY_BOOL_FIELD_NAMES",
    "_collect_tenant_config_refs",
    "_condition_field_references",
    "_detect_dead_constructs",
    "_find_user_role_enum",
    "_get_entities",
    "_is_framework_synthetic_name",
    "_lint_fk_targets_missing_display_field",
    "_lint_graph_edge_suggestions",
    "_lint_graph_node_suggestions",
    "_lint_integration_bindings",
    "_lint_list_surface_ux",
    "_lint_missing_titles",
    "_lint_modeling_anti_patterns",
    "_lint_naming_conventions",
    "_lint_nav_group_icon_consistency",
    "_lint_process_effects",
    "_lint_workspace_access_declarations",
    "_lint_workspace_personas",
    "_lint_workspace_routing",
    "_validate_account_codes",
    "_validate_condition_fields",
    "_validate_constraints",
    "_validate_entity_pk",
    "_validate_field_decimals",
    "_validate_field_duplicates",
    "_validate_field_enums",
    "_validate_field_modifiers",
    "_validate_field_strings",
    "_validate_graph_edge",
    "_validate_graph_node",
    "_validate_persona_backed_by",
    "_validate_predicate_node",
    "_validate_profile_archetype",
    "_validate_reserved_names",
    "_validate_transaction_transfers",
    "_walk_role_names",
    "extended_lint",
    "is_secret_field_name",
    "validate_admin_personas_scope_conflict",
    "validate_approvals",
    "validate_appspec",
    "validate_atomic_flows",
    "validate_audit_config",
    "validate_entities",
    "validate_event_payload_secrets",
    "validate_experiences",
    "validate_fitness_repr_fields",
    "validate_foreign_models",
    "validate_governance_policies",
    "validate_graph_declarations",
    "validate_integrations",
    "validate_ledgers",
    "validate_lifecycles",
    "validate_money_fields",
    "validate_nav_curation",
    "validate_notifications",
    "validate_persona_nav_refs",
    "validate_process_step_service_refs",
    "validate_rbac_matrix_diagnostics",
    "validate_role_references_against_enum",
    "validate_scope_predicates",
    "validate_sensitive_fields",
    "validate_services",
    "validate_slas",
    "validate_storage_refs",
    "validate_surfaces",
    "validate_tenancy_partition_key",
    "validate_tenant_host_blocks",
    "validate_transition_invocations",
    "validate_ux_specs",
    "validate_visibility_bool_field_scope_coverage",
    "validate_webhooks",
    "validate_workspace_primary_actions",
    "validate_workspace_region_actions",
]
