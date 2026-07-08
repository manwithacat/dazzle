"""Usage-driven form-field inference (1a — ADR-0050 Phase 5b, #1517).

Consumes the field-engagement signal captured by ``dz-usage.js`` (first-focus
beacons into ``_dazzle_usage_events``, aggregated per entity by
``read_usage_counts_for_request``) and annotates the form's field dicts before
primitive dispatch:

- **Autofocus** — the most-engaged plain field gets ``autofocus``, so the form
  opens where users actually start. Plain means it will render as a native
  ``Field``/``Combobox`` input; rich client-controller widgets (TomSelect,
  …) are skipped — HTML5 ``autofocus`` on a JS-enhanced control
  races its mount.

- **Combobox upgrade** — a heavily-engaged plain ``select`` with a long option
  list is promoted to the searchable ``combobox`` widget. An author-declared
  ``widget`` is authoritative and never overridden.

Same contract as the sibling resolvers (`action_prominence_resolver`,
`column_economy_resolver`): **cold-start byte parity** — below the min-sample
floor (or with no usage at all) the field dicts are untouched and the rendered
form is byte-identical to today's; and **traceability** — an annotation that
changes the outcome logs the signal that caused it (never a silent oracle).

Layering: this module is pure (dict in, dict mutated); the http layer reads
usage with the request in scope and calls this at the dispatch-ctx seam
(``page_routes._maybe_dispatch_inner_html``). Section dicts alias the flat
field entries, so in-place annotation covers sectioned forms too.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Minimum total first-focus events on the entity's forms before usage
# annotates anything (mirrors the sibling resolvers' cold-start floor).
_DEFAULT_MIN_SAMPLES = 10

# A plain select needs at least this many options before the searchable
# combobox is an upgrade rather than friction.
_DEFAULT_COMBOBOX_MIN_OPTIONS = 8

# Widget kinds where an HTML5 `autofocus` lands on a native input the user
# can immediately type/pick in. Everything else (money, file, rich widgets,
# ref pickers, remote search) is skipped.
_AUTOFOCUS_SAFE_KINDS = {
    "text",
    "textarea",
    "email",
    "url",
    "number",
    "password",
    "tel",
    "select",
    "date",
    "datetime",
    "datetime-local",
}


def _is_plain(entry: dict[str, Any]) -> bool:
    """True when the field dict will dispatch to a native Field/Combobox."""
    if entry.get("widget") or entry.get("ref_api") or entry.get("source"):
        return False
    return str(entry.get("kind", "")).lower() in _AUTOFOCUS_SAFE_KINDS


def annotate_form_fields_by_usage(
    fields: list[dict[str, Any]],
    usage: dict[str, int],
    *,
    min_samples: int = _DEFAULT_MIN_SAMPLES,
    combobox_min_options: int = _DEFAULT_COMBOBOX_MIN_OPTIONS,
) -> None:
    """Annotate form field dicts in place from the engagement signal.

    ``usage`` maps field name → first-focus count for the form's entity.
    Below the ``min_samples`` total floor this is a no-op (cold-start byte
    parity). Above it:

    - the most-engaged plain field (ties break to declared order via the
      stable max) gains ``autofocus: True``;
    - every plain ``select`` with ``>= combobox_min_options`` options whose
      own engagement clears ``min_samples`` gains ``widget: "combobox"``.
    """
    total = sum(usage.values())
    if total < min_samples or not fields:
        return

    # Combobox upgrades FIRST: an upgraded select is a rich client widget, so
    # it must already carry `widget` when the autofocus pass filters on
    # plainness — otherwise the hottest select could take autofocus and then
    # turn into the TomSelect control autofocus is excluded from.
    for entry in fields:
        if entry.get("widget") or str(entry.get("kind", "")).lower() != "select":
            continue
        if entry.get("ref_api") or entry.get("source"):
            continue
        options = entry.get("options") or []
        count = usage.get(str(entry.get("name", "")), 0)
        if len(options) >= combobox_min_options and count >= min_samples:
            entry["widget"] = "combobox"
            logger.debug(
                "usage-driven combobox upgrade: select %r (%d options, %d engagements "
                ">= floor=%d) — declared widget would stay a plain select",
                entry.get("name"),
                len(options),
                count,
                min_samples,
            )

    # Autofocus: hottest engaged plain field, declared order winning ties.
    hottest: dict[str, Any] | None = None
    hottest_count = 0
    for entry in fields:
        count = usage.get(str(entry.get("name", "")), 0)
        if count > hottest_count and _is_plain(entry):
            hottest, hottest_count = entry, count
    if hottest is not None:
        hottest["autofocus"] = True
        logger.debug(
            "usage-driven autofocus: field %r (%d first-focus events of %d total, "
            "floor=%d) — declared order would leave focus unset",
            hottest.get("name"),
            hottest_count,
            total,
            min_samples,
        )
