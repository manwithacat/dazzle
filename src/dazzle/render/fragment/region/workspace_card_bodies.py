"""Entity-card section body renderers (#1017) + row-action helper (#1148).

Extracted from workspace_rendering.py in #1057 cut 2 (v0.67.101).
Pure HTML-string builders for the four `entity_card` section
display modes — no I/O, no DB, no IR dispatch. Called from
`_build_entity_card_sections` in workspace_rendering after the
row data has been resolved.

Each `_render_*_body` function returns the raw HTML for the
section's `body` slot. The typed-primitive renderer pipes this
into the `body` field of `EntityCardSection` verbatim — these
helpers own escape responsibility for the raw row values they
read (via `_dazzle_html_escape`).

The `_eval_row_condition` + `_render_row_action_button` helpers
support #1148's `row_action:` primitive across the row-oriented
displays (list, cohort_strip, day_timeline). Each consumer
imports from here so the predicate + button HTML stay consistent.
"""

import datetime as _dt
import html as _html_module
import json as _json_module
from typing import Any

from dazzle.core.ir.conditions import (
    ComparisonOperator,
    ConditionExpr,
    LogicalOperator,
)


def _eval_row_condition(cond: ConditionExpr, row: dict[str, Any]) -> bool:
    """#1148: evaluate a row-level ConditionExpr against an item dict.

    Used by ``row_action.visible_when`` (and any other per-row
    predicate that operates on already-fetched row data). Supports:
    simple ``Comparison`` (field op literal) and compound
    ``AND`` / ``OR`` (recursive).

    Role checks, grant checks, via-conditions, function calls, and
    date arithmetic on rows fall back to ``True`` — those are
    server-side scope concepts, not row-data predicates. Better to
    over-show than silently hide a row-level action.
    """
    if cond.is_compound:
        if cond.left is None or cond.right is None or cond.operator is None:
            return True
        left = _eval_row_condition(cond.left, row)
        right = _eval_row_condition(cond.right, row)
        if cond.operator == LogicalOperator.AND:
            return left and right
        if cond.operator == LogicalOperator.OR:
            return left or right
        return True
    cmp = cond.comparison
    if cmp is None:
        return True
    if cmp.field is None or cmp.function is not None or cmp.value.is_date_expr:
        return True
    actual = row.get(cmp.field)
    op = cmp.operator
    if cmp.value.is_list:
        vals = cmp.value.values or []
        if op == ComparisonOperator.IN:
            return actual in vals
        if op == ComparisonOperator.NOT_IN:
            return actual not in vals
        return True
    expected = cmp.value.literal
    if op == ComparisonOperator.EQUALS or op == ComparisonOperator.IS:
        return actual == expected
    if op == ComparisonOperator.NOT_EQUALS or op == ComparisonOperator.IS_NOT:
        return actual != expected
    if actual is None or expected is None:
        return False
    try:
        if op == ComparisonOperator.GREATER_THAN:
            return bool(actual > expected)
        if op == ComparisonOperator.LESS_THAN:
            return bool(actual < expected)
        if op == ComparisonOperator.GREATER_EQUAL:
            return bool(actual >= expected)
        if op == ComparisonOperator.LESS_EQUAL:
            return bool(actual <= expected)
    except TypeError:
        return True
    return True


def _render_row_action_button(
    action_id: str,
    label: str,
    item: dict[str, Any],
    bind: dict[str, str],
    *,
    extra_class: str = "dz-list-row-action-btn",
    action_url: str = "",
) -> str:
    """#1148: build the per-row action button HTML.

    Emits a ``<button data-dz-row-action="<id>" data-dz-row-args="..."
    data-dz-row-action-url="<url>">`` carrying the bound row values as
    JSON. The client-side handler in ``dz-alpine.js`` (#1233) listens
    on ``[data-dz-row-action]``, reads the JSON payload and the resolved
    URL, and POSTs via ``htmx.ajax`` — inheriting CSRF + redirect/swap
    behaviour from the runtime's HTMX core.

    ``bind`` maps action-arg-name → row-field-name. The button's
    ``data-dz-row-args`` JSON encodes ``{arg: row[field]}`` per entry.
    Missing row fields become ``null`` — the action handler validates.

    ``action_url`` is the resolved POST endpoint for the named surface
    action (set by callers via the workspace ctx's ``row_action_routes``
    map; empty when no matching CREATE surface was found in the AppSpec).
    When empty, the client handler emits a console warning and no POST
    fires — preserves the pre-#1233 no-op shape rather than 404ing.

    ``extra_class`` lets each display family tone its button (list
    uses the table-cell class; day_timeline gets a slot-action class
    so CSS can position it inside the card).
    """
    bound: dict[str, Any] = {}
    for arg_name, field_name in bind.items():
        bound[arg_name] = item.get(field_name)
    args_json = _json_module.dumps(bound, default=str, sort_keys=True)
    url_attr = (
        f' data-dz-row-action-url="{_html_module.escape(action_url, quote=True)}"'
        if action_url
        else ""
    )
    return (
        f'<button type="button" class="{_html_module.escape(extra_class, quote=True)}" '
        f'data-dz-row-action="{_html_module.escape(action_id, quote=True)}" '
        f'data-dz-row-args="{_html_module.escape(args_json, quote=True)}"'
        f"{url_attr}>"
        f"{_html_module.escape(label)}"
        f"</button>"
    )


def _render_thread_summary_body(
    *,
    rows: list[dict[str, Any]],
    timestamp_field: str,
    sender_field: str,
    subject_field: str,
    snippet_field: str,
) -> str:
    """Render the body of an `entity_card` `thread_summary` section
    (#1017, v0.67.20).

    Compact comm-summary card showing the single most-recent thread.
    Distinct from `stamps` (chronological list) — this mode is
    designed for "what's the latest from parents?" kind of summary
    where the user wants ONE row, not a list. Most-recent picked by
    `fields[0]` (timestamp).

    Layout:
      <article class="dz-thread-summary">
        <header class="dz-thread-summary-header">
          <span class="dz-thread-summary-sender">{sender}</span>
          <time class="dz-thread-summary-time" datetime="<iso>">{visible}</time>
        </header>
        <h4 class="dz-thread-summary-subject">{subject}</h4>
        <p class="dz-thread-summary-snippet">{snippet}</p>
      </article>

    Empty / no-rows / no-timestamp returns empty string; caller
    flags omitted. Snippet is truncated to ~140 chars (compact-card
    convention) to keep the section visually balanced — the user
    drills into the full thread via the sender card's surface link.
    """
    if not rows or not timestamp_field:
        return ""

    def _to_dt(value: Any) -> _dt.datetime | None:
        if isinstance(value, _dt.datetime):
            return value if value.tzinfo else value.replace(tzinfo=_dt.UTC)
        if isinstance(value, str) and value:
            try:
                stripped = value.rstrip("Z")
                if stripped.endswith("+00:00") or "T" in stripped or " " in stripped:
                    parsed = _dt.datetime.fromisoformat(stripped)
                    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.UTC)
            except ValueError:
                return None
        return None

    # Pick the most-recent row by timestamp. Rows whose timestamp
    # doesn't parse rank below any parseable row.
    parsed: list[tuple[_dt.datetime | None, dict[str, Any]]] = [
        (_to_dt(row.get(timestamp_field)), row) for row in rows
    ]
    parsed.sort(key=lambda pair: (pair[0] is None, -(pair[0].timestamp() if pair[0] else 0)))
    chosen_ts, chosen_row = parsed[0]

    sender = str(chosen_row.get(sender_field, "") or "") if sender_field else ""
    subject = str(chosen_row.get(subject_field, "") or "") if subject_field else ""
    snippet_raw = str(chosen_row.get(snippet_field, "") or "") if snippet_field else ""
    # Truncate to ~140 chars at a word boundary; strip trailing
    # whitespace; append a one-character ellipsis when truncated.
    if len(snippet_raw) > 140:
        truncated = snippet_raw[:140].rsplit(" ", 1)[0].rstrip()
        snippet = f"{truncated}…"
    else:
        snippet = snippet_raw

    if chosen_ts is not None:
        iso = chosen_ts.isoformat()
        visible = chosen_ts.strftime("%Y-%m-%d %H:%M")
    else:
        iso = str(chosen_row.get(timestamp_field, "") or "")
        visible = iso

    sender_html = (
        f'<span class="dz-thread-summary-sender">{_dazzle_html_escape(sender)}</span>'
        if sender
        else ""
    )
    time_html = (
        f'<time class="dz-thread-summary-time" '
        f'datetime="{_dazzle_html_escape(iso)}">'
        f"{_dazzle_html_escape(visible)}"
        f"</time>"
    )
    subject_html = (
        f'<h4 class="dz-thread-summary-subject">{_dazzle_html_escape(subject)}</h4>'
        if subject
        else ""
    )
    snippet_html = (
        f'<p class="dz-thread-summary-snippet">{_dazzle_html_escape(snippet)}</p>'
        if snippet
        else ""
    )

    return (
        f'<article class="dz-thread-summary">'
        f'<header class="dz-thread-summary-header">'
        f"{sender_html}{time_html}"
        f"</header>"
        f"{subject_html}{snippet_html}"
        f"</article>"
    )


def _render_stamps_body(
    *,
    rows: list[dict[str, Any]],
    timestamp_field: str,
    label_field: str,
    detail_field: str,
) -> str:
    """Render the body of an `entity_card` `stamps` section
    (#1017, v0.67.19).

    Chronological event list — most recent first. Each row produces
    one `<li class="dz-stamp">` carrying:
      - a `<time datetime="<iso>">` with the parsed timestamp (or
        the raw value if it doesn't parse — defensive)
      - a `<span class="dz-stamp-label">` with the resolved label
      - an optional `<span class="dz-stamp-detail">` with the
        secondary field when configured

    Empty / no-timestamp-field returns empty string; caller flags
    the section omitted. The timestamp parser reuses the same
    coercion shape as `_build_day_timeline_slots` (datetime objects
    pass through; ISO strings parse; bare values fall through as
    "before any other parsable value").

    Sort is descending so the freshest event is at the top — the
    typical shape for activity-log render."""
    if not rows or not timestamp_field:
        return ""

    def _to_dt(value: Any) -> _dt.datetime | None:
        if isinstance(value, _dt.datetime):
            return value if value.tzinfo else value.replace(tzinfo=_dt.UTC)
        if isinstance(value, str) and value:
            try:
                stripped = value.rstrip("Z")
                if stripped.endswith("+00:00") or "T" in stripped or " " in stripped:
                    parsed = _dt.datetime.fromisoformat(stripped)
                    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.UTC)
            except ValueError:
                return None
        return None

    # Build (timestamp, row, raw_ts) tuples; sort descending.
    parsed: list[tuple[_dt.datetime | None, dict[str, Any], Any]] = []
    for row in rows:
        raw_ts = row.get(timestamp_field)
        parsed.append((_to_dt(raw_ts), row, raw_ts))
    # Place rows with parseable timestamps first (sorted desc); then
    # rows whose timestamp didn't parse (in their original order).
    parsed.sort(
        key=lambda triple: (triple[0] is None, -(triple[0].timestamp() if triple[0] else 0))
    )

    parts: list[str] = []
    for parsed_ts, row, raw_ts in parsed:
        # Time element: prefer ISO-8601 in the datetime= attr; visible
        # text is a humanised short form (`YYYY-MM-DD HH:MM` for
        # parseable values, raw stringified value otherwise).
        if parsed_ts is not None:
            iso = parsed_ts.isoformat()
            visible = parsed_ts.strftime("%Y-%m-%d %H:%M")
        else:
            iso = str(raw_ts or "")
            visible = iso
        time_html = (
            f'<time class="dz-stamp-time" datetime="{_dazzle_html_escape(iso)}">'
            f"{_dazzle_html_escape(visible)}"
            f"</time>"
        )

        label_value = str(row.get(label_field, "") or "") if label_field else ""
        label_html = (
            f'<span class="dz-stamp-label">{_dazzle_html_escape(label_value)}</span>'
            if label_value
            else ""
        )
        detail_value = str(row.get(detail_field, "") or "") if detail_field else ""
        detail_html = (
            f'<span class="dz-stamp-detail">{_dazzle_html_escape(detail_value)}</span>'
            if detail_value
            else ""
        )
        parts.append(f'<li class="dz-stamp">{time_html}{label_html}{detail_html}</li>')

    return f'<ol class="dz-entity-card-stamps">{"".join(parts)}</ol>'


def _render_mini_bars_body(
    *,
    rows: list[dict[str, Any]],
    value_field: str,
    label_field: str,
) -> str:
    """Render the body of an `entity_card` `mini_bars` section
    (#1017, v0.67.18).

    Compact horizontal bar row, one bar per row in the input list.
    Bars normalise against the max numeric value seen in `value_field`
    so the widest bar fills 100% and others scale relative to it.
    Non-numeric values render as a 0-width bar (defensive — adapter
    rather than crashing on a None / string value).

    Returns empty string when there are no rows or when `value_field`
    is unset; the caller flags the section omitted in that case."""
    if not rows or not value_field:
        return ""
    # Extract numeric values; track max for normalisation.
    parsed: list[tuple[float, str]] = []  # (value, label)
    max_value = 0.0
    for row in rows:
        raw = row.get(value_field)
        try:
            num = float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            num = 0.0
        if num > max_value:
            max_value = num
        label_raw = ""
        if label_field:
            label_raw = str(row.get(label_field, "") or "")
        parsed.append((num, label_raw))
    if not parsed:
        return ""
    if max_value <= 0:
        # All zero / negative — emit zero-width bars rather than divide-by-zero.
        max_value = 1.0
    bars: list[str] = []
    for value, label in parsed:
        pct = max(0.0, min(100.0, (value / max_value) * 100.0))
        # Inline width % is the only style — project CSS owns the rest
        # via the `dz-mini-bar` class.
        label_html = (
            f'<span class="dz-mini-bar-label">{_dazzle_html_escape(label)}</span>' if label else ""
        )
        # Format the value: int when whole, else 1 decimal.
        if value == int(value):
            value_str = str(int(value))
        else:
            value_str = f"{value:.1f}"
        bars.append(
            f'<li class="dz-mini-bar" data-dz-value="{_dazzle_html_escape(value_str)}">'
            f'<span class="dz-mini-bar-fill" style="width: {pct:.1f}%"></span>'
            f"{label_html}"
            f'<span class="dz-mini-bar-value">{_dazzle_html_escape(value_str)}</span>'
            f"</li>"
        )
    return f'<ul class="dz-entity-card-mini-bars">{"".join(bars)}</ul>'


def _render_quick_actions_body(actions: list[str]) -> str:
    """Render the body of an `entity_card` `quick_actions` section
    (#1017, v0.67.17).

    Each action id renders as a `<button class="dz-quick-action"
    data-dz-action="<id>">` carrying the humanised action label as
    visible text. Project JS hooks `[data-dz-action]` to open the
    matching surface as a modal flow (the surface lookup happens
    client-side via the existing surface-modal machinery).

    Empty list returns an empty string — the caller flags the
    section omitted to avoid rendering an empty button row."""
    if not actions:
        return ""
    parts: list[str] = []
    for action_id in actions:
        action_str = str(action_id)
        if not action_str:
            continue
        label = action_str.replace("_", " ").title()
        parts.append(
            f'<button type="button" class="dz-quick-action" '
            f'data-dz-action="{_dazzle_html_escape(action_str)}">'
            f"{_dazzle_html_escape(label)}"
            f"</button>"
        )
    if not parts:
        return ""
    return f'<div class="dz-entity-card-quick-actions">{"".join(parts)}</div>'


def _dazzle_html_escape(value: str) -> str:
    """Lightweight HTML attribute/text escape used by the typed-
    primitive data resolution helpers. The composed body strings
    pass through the typed renderer's `body` slot which does NOT
    re-escape pre-rendered HTML — these helpers own escape
    responsibility for fields they pull off raw source rows."""
    import html as _html

    return _html.escape(value, quote=True)
