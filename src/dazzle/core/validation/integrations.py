"""Service, foreign-model, integration, and integration validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from urllib.parse import urlparse

from .. import ir


def validate_services(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all services for semantic correctness.

    Checks:
    - Spec URLs are valid
    - Auth profiles are complete
    - Required fields are present

    Returns:
        Tuple of (errors, warnings)
    """
    errors = []
    warnings = []

    for api in appspec.apis:
        # Check spec is provided
        if not api.spec_url and not api.spec_inline:
            errors.append(f"API '{api.name}' has no spec (url or inline)")

        # Validate URL format if provided
        if api.spec_url:
            try:
                parsed = urlparse(api.spec_url)
                if not parsed.scheme or not parsed.netloc:
                    warnings.append(f"API '{api.name}' has invalid spec URL: {api.spec_url}")
            except Exception:
                warnings.append(f"API '{api.name}' has malformed spec URL: {api.spec_url}")

        # Check auth profile
        if api.auth_profile.kind in (ir.AuthKind.OAUTH2_LEGACY, ir.AuthKind.OAUTH2_PKCE):
            # OAuth2 APIs should specify scopes
            if "scopes" not in api.auth_profile.options:
                warnings.append(f"API '{api.name}' uses OAuth2 but doesn't specify scopes")

    return errors, warnings


def validate_foreign_models(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all foreign models for semantic correctness.

    Checks:
    - Key fields are defined
    - Constraints are valid
    - Fields have appropriate types

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    for foreign_model in appspec.foreign_models:
        # Check key fields exist
        if not foreign_model.key_fields:
            errors.append(f"Foreign model '{foreign_model.name}' has no key fields")

        for key_field in foreign_model.key_fields:
            if not foreign_model.get_field(key_field):
                errors.append(
                    f"Foreign model '{foreign_model.name}' key field '{key_field}' "
                    f"is not defined in fields"
                )

        # Check for conflicting constraints
        constraint_kinds = [c.kind for c in foreign_model.constraints]
        if ir.ForeignConstraintKind.READ_ONLY in constraint_kinds:
            if ir.ForeignConstraintKind.BATCH_IMPORT in constraint_kinds:
                # This is ok - read-only can still be imported
                pass

    return errors, warnings


def validate_integrations(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all integrations for semantic correctness.

    Checks:
    - Service and foreign model references
    - Action/sync structure (simplified for v0.1)

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    for integration in appspec.integrations:
        # Check that integration uses at least one service
        if not integration.api_refs:
            warnings.append(f"Integration '{integration.name}' doesn't use any APIs")

        # Check that integration has actions, syncs, or mappings (v0.30.0+)
        if not integration.actions and not integration.syncs and not integration.mappings:
            warnings.append(f"Integration '{integration.name}' has no actions, syncs, or mappings")

    return errors, warnings
