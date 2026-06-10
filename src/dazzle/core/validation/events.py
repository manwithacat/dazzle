"""Event payload secret-leak validation.

Split verbatim from dazzle.core.validator per #1361.
"""

from .. import ir
from .entities import is_secret_field_name


def validate_event_payload_secrets(appspec: ir.AppSpec) -> tuple[list[str], list[str]]:
    """
    Validate that event payloads do not contain secret/sensitive fields.

    Events are typically logged, replayed, and stored long-term. Including
    passwords, API keys, tokens, or other secrets in event payloads creates
    security vulnerabilities.

    Checks:
    - HLESS stream schema fields for secret-like names
    - Event model custom fields for secret-like names
    - Entity fields used as event payloads for secret-like names

    Returns:
        Tuple of (errors, warnings)
        - errors: Fields that are almost certainly secrets (password, api_key, etc.)
        - warnings: Fields that might be secrets (token, hash, auth, etc.)
    """
    errors: list[str] = []
    warnings: list[str] = []

    # High-risk patterns that are almost always actual secrets
    high_risk_patterns = {"password", "passwd", "pwd", "api_key", "apikey", "secret", "secret_key"}

    def check_field(field_name: str, context: str) -> None:
        if not is_secret_field_name(field_name):
            return

        lower_name = field_name.lower()
        # High-risk patterns are errors
        if any(pattern in lower_name for pattern in high_risk_patterns):
            errors.append(
                f"{context} field '{field_name}' appears to contain a secret. "
                f"Secrets MUST NOT be included in event payloads. "
                f"Store secrets securely and use references instead."
            )
        else:
            # Medium-risk patterns are warnings
            warnings.append(
                f"{context} field '{field_name}' may contain sensitive data. "
                f"Ensure this field does not contain secrets, tokens, or credentials. "
                f"If it does, remove it from the event payload."
            )

    # Check HLESS streams
    for stream in appspec.streams:
        for schema in stream.schemas:
            for schema_field in schema.fields:
                check_field(schema_field.name, f"Stream '{stream.name}' schema '{schema.name}'")

    # Check event model (custom event fields)
    if appspec.event_model:
        for event in appspec.event_model.events:
            for event_field in event.custom_fields:
                check_field(event_field.name, f"Event '{event.name}'")

    return errors, warnings
