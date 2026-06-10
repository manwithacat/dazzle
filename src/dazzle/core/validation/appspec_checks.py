"""The validate_appspec aggregator over all validation modules.

Split verbatim from dazzle.core.validator per #1361.
"""

from .tenancy import validate_tenant_host_blocks


def validate_appspec(appspec_or_fragment: object) -> list[str]:
    """Validate a fragment or AppSpec for tenant_host hard-error rules.

    Suitable for direct use from tests and CLI commands that only need
    the error list.  Returns a flat list of error strings.
    """
    errors, _warnings = validate_tenant_host_blocks(appspec_or_fragment)
    return errors
