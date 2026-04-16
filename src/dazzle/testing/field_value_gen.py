"""
Backward-compatibility shim — canonical module is ``dazzle.core.field_values``.

The generators have no test-framework dependencies and belong in ``core``.
This module re-exports both public functions so existing callers continue
to work without changes.
"""

from dazzle.core.field_values import generate_field_value, generate_field_value_from_str

__all__ = ["generate_field_value", "generate_field_value_from_str"]
