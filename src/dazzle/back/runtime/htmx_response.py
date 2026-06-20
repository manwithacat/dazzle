"""
HTMX-aware response utilities — re-export shim.

The canonical implementation lives in ``dazzle.back.runtime.htmx``.
This module re-exports all public names so existing ``dazzle.back``
imports continue to work without modification.
"""

from dazzle.back.runtime.htmx import (
    HtmxDetails,
    htmx_error_response,
    htmx_response,
    htmx_trigger_headers,
    is_htmx_request,
    json_or_htmx_error,
)

__all__ = [
    "HtmxDetails",
    "htmx_error_response",
    "htmx_response",
    "htmx_trigger_headers",
    "is_htmx_request",
    "json_or_htmx_error",
]
