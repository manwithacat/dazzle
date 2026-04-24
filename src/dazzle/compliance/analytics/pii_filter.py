"""PII stripping for analytics events (v0.61.0).

The framework MUST NOT send values from fields annotated with `pii()` to
any analytics sink without the surface explicitly opting in. This module
is the single enforcement boundary — used by:

- Client-side event construction (server-rendered template includes only
  non-PII fields in the rendered `data-dz-*` attributes).
- Server-side sinks (GA4 Measurement Protocol, Plausible Events API, etc.)
  call `strip_pii()` before the HTTP POST.
- Debug / dev-mode analytics logs apply the same filter so PII never hits
  disk in plaintext form.

Opt-in is surface-scoped: a DSL author declares `analytics: include_pii: [email]`
on a surface, and the resulting `opt_in` set is passed here. Blanket app-level
opt-in is forbidden by design — too easy to ship accidentally.

Special-category fields (GDPR Art. 9/10 — health, biometric, etc.) are stripped
even under opt-in unless the additional `include_special_category=True` flag
is set. This mirrors the stricter handling required by Consent Mode v2 and
the spec's Phase 2 consent-gating plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dazzle.core.ir import FieldSpec, PIISensitivity


@dataclass(frozen=True)
class PIIFilterResult:
    """Outcome of a PII-stripping pass.

    `kept` is the redacted dict safe to emit. `dropped_fields` is the list of
    field names that were removed (for diagnostic logging — never include
    the values). `special_category_blocked` counts how many drops were due
    to GDPR Article 9/10 status even when the caller opted in.
    """

    kept: dict[str, Any]
    dropped_fields: list[str] = field(default_factory=list)
    special_category_blocked: int = 0


def strip_pii(
    data: dict[str, Any],
    fields_by_name: dict[str, FieldSpec],
    *,
    opt_in: frozenset[str] | set[str] | None = None,
    include_special_category: bool = False,
) -> PIIFilterResult:
    """Return a dict with PII field values removed.

    Args:
        data: Raw event payload keyed by field name.
        fields_by_name: FieldSpec for every known entity field so we can read
            the PII annotation. Fields not present in this map are treated as
            non-PII (the caller is responsible for passing the correct map).
        opt_in: Field names explicitly whitelisted for emission by the
            surface's `analytics: include_pii:` declaration. Defaults to
            empty — nothing is opted in.
        include_special_category: If True AND the field is in `opt_in`, the
            special-category field value survives. Off by default; set only
            from a surface with explicit gated consent.

    Returns:
        A PIIFilterResult with the safe payload and diagnostic counters.

    Any field whose FieldSpec has `pii is not None` is dropped unless the
    field name is in `opt_in`. If it is in `opt_in` but the sensitivity is
    SPECIAL_CATEGORY, it is *still* dropped unless `include_special_category`
    is True — Article 9/10 data gets a second gate by default.
    """
    opt_in_set: set[str] = set(opt_in or ())
    kept: dict[str, Any] = {}
    dropped: list[str] = []
    blocked_special: int = 0

    for key, value in data.items():
        spec = fields_by_name.get(key)
        if spec is None or spec.pii is None:
            # Not declared as PII — pass through.
            kept[key] = value
            continue

        if key not in opt_in_set:
            # Declared PII, not opted in — strip silently.
            dropped.append(key)
            continue

        # Opted in; check special-category gate.
        if spec.pii.sensitivity is PIISensitivity.SPECIAL_CATEGORY and not include_special_category:
            dropped.append(key)
            blocked_special += 1
            continue

        kept[key] = value

    return PIIFilterResult(
        kept=kept,
        dropped_fields=dropped,
        special_category_blocked=blocked_special,
    )
