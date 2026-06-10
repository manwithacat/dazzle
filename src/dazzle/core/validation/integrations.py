"""Service, foreign-model, integration, webhook, and notification validation.

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


def validate_notifications(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate all notifications for semantic correctness (v0.34.0).

    Checks:
    - Trigger entity exists
    - Trigger field exists on entity (if specified)
    - No duplicate notification names
    - Recipients reference valid fields (for field-based recipients)

    Returns:
        Tuple of (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []
    seen_names: set[str] = set()
    entity_names = {e.name for e in appspec.domain.entities}

    for n in appspec.notifications:
        # Duplicate name check
        if n.name in seen_names:
            errors.append(f"Duplicate notification name: '{n.name}'")
        seen_names.add(n.name)

        # Trigger entity must exist
        if n.trigger.entity not in entity_names:
            errors.append(f"Notification '{n.name}' references unknown entity '{n.trigger.entity}'")
        else:
            entity = appspec.get_entity(n.trigger.entity)
            if entity and n.trigger.field:
                if not entity.get_field(n.trigger.field):
                    errors.append(
                        f"Notification '{n.name}' trigger references unknown field "
                        f"'{n.trigger.field}' on entity '{n.trigger.entity}'"
                    )

            # Field-based recipients should reference a valid field
            if entity and n.recipients.kind == "field":
                if n.recipients.value and not entity.get_field(n.recipients.value):
                    warnings.append(
                        f"Notification '{n.name}' recipients reference field "
                        f"'{n.recipients.value}' which does not exist on '{n.trigger.entity}'"
                    )

    return errors, warnings


# =============================================================================
# Preview construct validation (parsed but not yet enforced at runtime)
# =============================================================================


def validate_webhooks(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """Validate webhook definitions and warn about runtime status."""
    errors: list[str] = []
    warnings: list[str] = []

    if not appspec.webhooks:
        return errors, warnings

    entity_names = {e.name for e in appspec.domain.entities}

    warnings.append(
        f"[Preview] {len(appspec.webhooks)} webhook(s) defined. "
        "Webhook delivery is not yet enforced at runtime."
    )

    for wh in appspec.webhooks:
        if wh.entity and wh.entity not in entity_names:
            errors.append(f"Webhook '{wh.name}' references unknown entity '{wh.entity}'.")
        if not wh.events:
            warnings.append(f"Webhook '{wh.name}' has no events specified.")
        if not wh.url:
            warnings.append(f"Webhook '{wh.name}' has no URL configured.")

    return errors, warnings
