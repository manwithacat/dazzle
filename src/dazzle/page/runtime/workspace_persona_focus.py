"""PersonaVariant ``focus`` / ``purpose`` for workspace default layout.

EX-048 deferred ``focus`` (cycle 1470): DSL authors declare
``ux: as <persona>: focus: r1, r2`` so search/metrics lead the default
card order and fall inside the eager fold window. User-saved layouts
still win — apply only when no ``workspace.{name}.layout`` preference.

Kept as a leaf module so ``workspace_renderer`` maintainability stays
above the complexity ratchet MI rank A floor.
"""

from __future__ import annotations

from typing import Any

# Cap eager regions after focus lead so persona intent wins over stage
# STAGE_FOLD defaults without re-opening command_center / dual_pane thrash
# (nested Playwright storms when fold ≥6–8 concurrent region GETs).
_MAX_FOCUS_FOLD = 6


def collect_workspace_persona_overrides(
    workspace: Any,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Collect ``ux: as <persona>: focus/purpose`` from a WorkspaceSpec."""
    persona_focus: dict[str, list[str]] = {}
    persona_purposes: dict[str, str] = {}
    ux = getattr(workspace, "ux", None)
    if ux is None:
        return persona_focus, persona_purposes
    for variant in getattr(ux, "persona_variants", None) or []:
        persona = getattr(variant, "persona", None) or ""
        if not persona:
            continue
        focus_list = list(getattr(variant, "focus", None) or [])
        if focus_list:
            persona_focus[persona] = focus_list
        purpose_override = getattr(variant, "purpose", None) or ""
        if purpose_override:
            persona_purposes[persona] = purpose_override
    return persona_focus, persona_purposes


def first_persona_override(
    user_roles: list[str],
    persona_focus: dict[str, list[str]],
    persona_purposes: dict[str, str],
) -> tuple[list[str] | None, str | None]:
    """First role with focus and/or purpose override (table-override rule)."""
    for role in user_roles:
        key = role.removeprefix("role_")
        if key not in persona_focus and key not in persona_purposes:
            continue
        focus = list(persona_focus[key]) if key in persona_focus else None
        purpose = persona_purposes.get(key) or None
        return focus, purpose
    return None, None


def regions_with_focus_lead(
    regions: list[Any],
    focus_names: list[str],
) -> list[Any] | None:
    """Return reordered regions, or None when order is already correct."""
    by_name = {r.name: r for r in regions}
    leading: list[Any] = []
    seen: set[str] = set()
    for name in focus_names:
        region = by_name.get(name)
        if region is None or name in seen:
            continue
        leading.append(region)
        seen.add(name)
    if not leading:
        return None
    ordered = leading + [r for r in regions if r.name not in seen]
    if [r.name for r in ordered] == [r.name for r in regions]:
        return None
    return ordered


def _fold_count_for_focus(
    regions: list[Any],
    focus_names: list[str],
    current_fold: int,
) -> int | None:
    """Return expanded fold_count, or None when stage default already covers focus."""
    known = {r.name for r in regions}
    n_focus = sum(1 for name in focus_names if name in known)
    if n_focus <= 0:
        return None
    desired = min(n_focus, _MAX_FOCUS_FOLD)
    if desired <= current_fold:
        return None
    return desired


def apply_persona_focus(
    ctx: Any,
    user_roles: list[str],
) -> Any:
    """Reorder regions so the matching persona's ``focus:`` list leads.

    Author intent from ``ux: as <persona>: focus: r1, r2, …``. Unknown focus
    names are skipped. First matching role wins. Never mutates *ctx*.

    Cycle 1484 (EX-048 follow-up): also expand ``fold_count`` so every
    *known* focus region is above the fold (eager GET). Stage defaults
    often cap at 3 while authors list 4 focus regions (e.g. contact_manager
    home: directory_stats + find_contact + favourites + recent) — without
    expansion the last focus card stayed intersect-once. Cap at
    ``_MAX_FOCUS_FOLD`` to avoid re-opening multi-queue thrash.
    """
    persona_focus = getattr(ctx, "persona_focus", None) or {}
    persona_purposes = getattr(ctx, "persona_purposes", None) or {}
    if not user_roles or (not persona_focus and not persona_purposes):
        return ctx

    focus_names, purpose_override = first_persona_override(
        user_roles, persona_focus, persona_purposes
    )
    updates: dict[str, Any] = {}
    if purpose_override:
        updates["purpose"] = purpose_override
    if focus_names:
        regions = list(ctx.regions)
        reordered = regions_with_focus_lead(regions, focus_names)
        if reordered is not None:
            updates["regions"] = reordered
            regions = reordered
        current_fold = int(getattr(ctx, "fold_count", None) or 0) or 0
        expanded = _fold_count_for_focus(regions, focus_names, current_fold)
        if expanded is not None:
            updates["fold_count"] = expanded
    if not updates:
        return ctx
    return ctx.model_copy(update=updates)
