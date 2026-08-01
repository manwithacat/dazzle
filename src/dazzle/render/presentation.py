"""Hyperpart presentation matrix — role × host → density (#1626 process).

Doctrine (antagonist ``HYPERPART_PRESENTATION_PROCESS``):

* Semantic **role** of the value (person, money, …), not English labels.
* **Host** density (list_cell, queue_meta, …) picks the Hyperpart variant.
* One **present()** seam — host-local ``str(value)`` for person is a defect.
* Closed matrix; miss → plain + residual, never invent a fourth format.

Authoring (HM pick-a-surface) selects region *modes*. This module selects
cell *presentation* for a known role on a known host.
"""

from __future__ import annotations

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

# Normative v1 matrix (person×queue_meta is the primary product gap).
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


@dataclass(frozen=True, slots=True)
class PresentResult:
    """Outcome of :func:`present` for one cell/meta segment."""

    html: str
    """Trusted HTML or escaped plain text."""

    is_html: bool
    """When True, emit path must not escape ``html``."""

    suppress_label: bool
    """When True, host must not prefix visible chrome like ``Assigned To:``."""

    density: Density
    role: Role
    host: Host
    matrix_miss: bool = False


def matrix_density(role: Role, host: Host) -> Density | None:
    """Return matrix density or None when no row (caller may residual)."""
    return PRESENTATION_MATRIX.get((role, host))


def infer_role(value: Any, col: dict[str, Any] | None = None) -> Role:
    """Best-effort role from column metadata + value (person first)."""
    col = col or {}
    col_type = str(col.get("type") or "").lower()
    if col_type == "color":
        return "color"
    if col_type in ("currency", "money"):
        return "money"
    if col_type in ("badge", "status", "enum") and col.get("type") == "badge":
        return "status"
    if col_type in ("date", "datetime", "time"):
        return "datetime"
    if looks_like_person_ref(value if isinstance(value, dict) else {"name": str(value or "")}, col):
        return "person"
    # Field-key only person heuristic when value is scalar UUID
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
    """Select matrix density and emit HTML for *value* on *host*.

    Person on ``queue_meta`` → Avatar only (no visible ``Assigned To:`` label).
    """
    col = col or {}
    density = matrix_density(role, host)
    if density is None:
        text = plain_fallback or _plain_text(value)
        return PresentResult(
            html=text,
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
        if density == "avatar_only":
            chip = render_user_chip_html(value, col, density="avatar_only")
        else:
            chip = render_user_chip_linked_html(value, col)
        # queue_meta: chip *is* the signal — suppress chrome labels
        suppress = host == "queue_meta"
        return PresentResult(
            html=chip if chip and chip != "—" else plain_fallback or _plain_text(value),
            is_html=bool(chip and chip != "—" and "dz-avatar" in chip),
            suppress_label=suppress and bool(chip and chip != "—" and "dz-avatar" in chip),
            density=density,
            role=role,
            host=host,
        )
    # Other densities: callers still use specialized paths for money/swatch/badge;
    # present() returns plain until those hosts migrate fully.
    text = plain_fallback or _plain_text(value)
    return PresentResult(
        html=text,
        is_html=False,
        suppress_label=False,
        density=density,
        role=role,
        host=host,
    )


def _plain_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, dict):
        return _ref_display_name(value) or str(value.get("id") or "")
    return str(value)
