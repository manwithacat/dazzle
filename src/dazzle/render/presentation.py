"""Hyperpart presentation matrix — role × host → density (#1626 process).

Doctrine (antagonist ``HYPERPART_PRESENTATION_PROCESS``):

* Semantic **role** of the value (person, money, …), not English labels.
* **Host** density (list_cell, queue_meta, …) picks the Hyperpart variant.
* One **present()** seam — host-local ``str(value)`` for person is a defect.
* Closed matrix; miss → plain + residual, never invent a fourth format.

**Agent cognition:** :func:`cognition_snapshot` describes what is audited vs
matrix-only so opportunity scans cannot claim full green for un-scanned hosts.

**Agent creativity:** extend only via new :data:`PRESENTATION_MATRIX` rows +
:func:`present` branches + unit tests + recapture — never one-app formats.
"""

from __future__ import annotations

import html as _html_mod
from dataclasses import dataclass
from typing import Any, Literal

from dazzle.render.filters import _ref_display_name
from dazzle.render.user_chip import (
    looks_like_person_ref,
    render_user_chip_html,
    render_user_chip_linked_html,
)

Role = Literal["person", "money", "status", "color", "datetime", "plain"]
Host = Literal[
    "list_cell",
    "detail_cell",
    "queue_meta",
    "kanban_field",
    "card_meta",
    "timeline_meta",
    "metrics_tile",
]
Density = Literal[
    "avatar_only",
    "avatar_name",
    "badge",
    "swatch",
    "money",
    "plain",
    "refuse",
]

# Normative v1 matrix. Grow only with still evidence + present() branch + tests.
PRESENTATION_MATRIX: dict[tuple[Role, Host], Density] = {
    ("person", "list_cell"): "avatar_name",
    ("person", "detail_cell"): "avatar_name",
    ("person", "queue_meta"): "avatar_only",
    ("person", "kanban_field"): "avatar_name",
    ("person", "card_meta"): "avatar_name",
    ("person", "timeline_meta"): "avatar_name",
    ("person", "metrics_tile"): "refuse",
    ("money", "queue_meta"): "money",
    ("money", "list_cell"): "money",
    ("money", "detail_cell"): "money",
    ("status", "list_cell"): "badge",
    ("status", "detail_cell"): "badge",
    ("status", "queue_meta"): "badge",
    ("status", "kanban_field"): "badge",
    ("color", "list_cell"): "swatch",
    ("color", "detail_cell"): "swatch",
    ("color", "queue_meta"): "swatch",
    ("datetime", "queue_meta"): "plain",
    ("plain", "list_cell"): "plain",
    ("plain", "queue_meta"): "plain",
}

# Static opportunity scan currently walks these hosts only.
HOSTS_AUDITED_BY_SCANNER: frozenset[str] = frozenset(
    {
        "list_cell",
        "detail_cell",
        "queue_meta",
        "kanban_field",
        "timeline_meta",
        "card_meta",
        "metrics_tile",
    }
)

# Emit paths that call present() or equivalent shared person chip.
HOSTS_WIRED_TO_SEAM: frozenset[str] = frozenset(
    {
        "list_cell",  # _shared / _data_row user_chip ≡ present person
        "detail_cell",
        "queue_meta",  # present()
        "kanban_field",  # present() via kanban card fields
        "timeline_meta",  # present() via activity-feed actor + timeline fields
        "card_meta",  # present() via display: grid card fields
        "metrics_tile",  # present() refuse — no person-as-text KPI
    }
)


@dataclass(frozen=True, slots=True)
class PresentResult:
    """Outcome of :func:`present` for one cell/meta segment."""

    html: str
    is_html: bool
    suppress_label: bool
    density: Density
    role: Role
    host: Host
    matrix_miss: bool = False


def matrix_density(role: Role, host: Host) -> Density | None:
    """Return matrix density or None when no row (caller may residual)."""
    return PRESENTATION_MATRIX.get((role, host))


def cognition_snapshot() -> dict[str, Any]:
    """Machine-readable process state for agent OBSERVE / improve loops."""
    matrix_hosts = sorted({h for (_, h) in PRESENTATION_MATRIX})
    matrix_roles = sorted({r for (r, _) in PRESENTATION_MATRIX})
    not_audited = sorted(set(matrix_hosts) - set(HOSTS_AUDITED_BY_SCANNER))
    not_wired = sorted(set(matrix_hosts) - set(HOSTS_WIRED_TO_SEAM))
    return {
        "schema_version": 2,
        "doctrine": "docs/reference/hyperpart-presentation.md",
        "seam": "dazzle.render.presentation.present",
        "matrix_roles": matrix_roles,
        "matrix_hosts": matrix_hosts,
        "matrix_row_count": len(PRESENTATION_MATRIX),
        "hosts_audited_by_scanner": sorted(HOSTS_AUDITED_BY_SCANNER),
        "hosts_not_yet_audited": not_audited,
        "hosts_wired_to_seam": sorted(HOSTS_WIRED_TO_SEAM),
        "hosts_matrix_only_or_partial_wire": not_wired,
        "how_to_extend": (
            "If stills show labeled prose for a role×host with no good matrix row: "
            "(1) residual hyperpart_matrix_miss, (2) add PRESENTATION_MATRIX row, "
            "(3) implement density in present(), (4) unit test + recapture hero still. "
            "Do not invent a one-app assignee format or second avatar CSS class."
        ),
        "creativity_boundary": (
            "Select only matrix densities. Creativity is in mapping domain fields "
            "to roles and proposing matrix extensions with still evidence — not "
            "novel HTML on a single example app."
        ),
    }


def infer_role(value: Any, col: dict[str, Any] | None = None) -> Role:
    """Best-effort role from column metadata + value (person first)."""
    col = col or {}
    col_type = str(col.get("type") or "").lower()
    if col_type == "color":
        return "color"
    if col_type in ("currency", "money"):
        return "money"
    if col_type in ("badge", "status") or (
        col_type == "enum" and str(col.get("widget") or "") == "badge"
    ):
        return "status"
    if col_type in ("date", "datetime", "time"):
        return "datetime"
    probe = value if isinstance(value, dict) else {"name": str(value or "")}
    if looks_like_person_ref(probe, col):
        return "person"
    if looks_like_person_ref({"name": "x"}, col):
        return "person"
    return "plain"


def present(
    role: Role,
    host: Host,
    value: Any,
    col: dict[str, Any] | None = None,
    *,
    plain_fallback: str = "",
) -> PresentResult:
    """Select matrix density and emit HTML for *value* on *host*."""
    col = col or {}
    density = matrix_density(role, host)
    if density is None:
        text = plain_fallback or _plain_text(value)
        return PresentResult(
            html=_escape_plain(text),
            is_html=False,
            suppress_label=False,
            density="plain",
            role=role,
            host=host,
            matrix_miss=True,
        )
    if density == "refuse":
        return PresentResult(
            html="",
            is_html=False,
            suppress_label=True,
            density="refuse",
            role=role,
            host=host,
        )
    if role == "person" and density in ("avatar_only", "avatar_name"):
        return _present_person(value, col, host, density, plain_fallback)
    if density == "money":
        return _present_money(value, col, role, host, plain_fallback)
    if density == "swatch":
        return _present_swatch(value, role, host, plain_fallback)
    if density == "badge":
        return _present_badge(value, role, host, plain_fallback)
    text = plain_fallback or _plain_text(value)
    return PresentResult(
        html=_escape_plain(text),
        is_html=False,
        suppress_label=False,
        density=density,
        role=role,
        host=host,
    )


def _present_person(
    value: Any,
    col: dict[str, Any],
    host: Host,
    density: Density,
    plain_fallback: str,
) -> PresentResult:
    if density == "avatar_only":
        chip = render_user_chip_html(value, col, density="avatar_only")
    else:
        chip = render_user_chip_linked_html(value, col)
    ok = bool(chip and chip != "—" and "dz-avatar" in chip)
    suppress = host == "queue_meta" and ok
    return PresentResult(
        html=chip if ok else _escape_plain(plain_fallback or _plain_text(value)),
        is_html=ok,
        suppress_label=suppress,
        density=density,
        role="person",
        host=host,
    )


def _present_money(
    value: Any,
    col: dict[str, Any],
    role: Role,
    host: Host,
    plain_fallback: str,
) -> PresentResult:
    from dazzle.render.filters import _currency_filter

    html = _currency_filter(value)
    if html:
        return PresentResult(
            html=str(html),
            is_html=True,
            suppress_label=False,
            density="money",
            role=role,
            host=host,
        )
    fmt = str(col.get("format") or "")
    code = ""
    if "currency:" in fmt:
        code = fmt.split("currency:", 1)[1].split()[0].upper()
    try:
        num = float(value)
        text = f"{code} {num:,.2f}".strip() if code else f"{num:,.2f}"
    except (TypeError, ValueError):
        text = plain_fallback or _plain_text(value)
    return PresentResult(
        html=_escape_plain(text),
        is_html=False,
        suppress_label=False,
        density="money",
        role=role,
        host=host,
    )


def _present_swatch(value: Any, role: Role, host: Host, plain_fallback: str) -> PresentResult:
    from dazzle.render.cell_chrome import _render_color_swatch_html

    swatch = _render_color_swatch_html(value)
    if swatch and swatch != "—":
        return PresentResult(
            html=swatch,
            is_html=True,
            suppress_label=False,
            density="swatch",
            role=role,
            host=host,
        )
    return PresentResult(
        html=_escape_plain(plain_fallback or _plain_text(value)),
        is_html=False,
        suppress_label=False,
        density="swatch",
        role=role,
        host=host,
    )


def _present_badge(value: Any, role: Role, host: Host, plain_fallback: str) -> PresentResult:
    if value in (None, ""):
        return PresentResult(
            html='<span class="dz-badge-empty" aria-label="No status">—</span>',
            is_html=True,
            suppress_label=False,
            density="badge",
            role=role,
            host=host,
        )
    label = _plain_text(value)
    tone = "neutral"
    esc = _html_mod.escape(label, quote=False)
    tone_attr = _html_mod.escape(tone, quote=True)
    html = f'<span class="dz-badge dz-badge-sm" data-dz-tone="{tone_attr}">{esc}</span>'
    return PresentResult(
        html=html,
        is_html=True,
        suppress_label=False,
        density="badge",
        role=role,
        host=host,
    )


def _plain_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, dict):
        # Never fall through to str(dict) — nested UUID → UUID('…') in buyer chrome.
        name = _ref_display_name(value)
        if name and not (name.startswith("{") and "id" in name):
            return name
        rid = value.get("id")
        return str(rid) if rid is not None else ""
    from uuid import UUID

    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _escape_plain(text: str) -> str:
    return _html_mod.escape(text, quote=False) if text else ""
