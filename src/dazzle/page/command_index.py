"""Command-palette index — accessible destinations for a persona.

Pure function of the AppSpec + the requesting persona's roles: produces the
list of navigable destinations (workspaces + entity lists) a persona may
reach, for the `dz-command` palette's `hx-get` endpoint. Access uses the
SAME source of truth as the sidebar (`workspace_allowed_personas`), so the
palette can never surface a destination that would 403.

No I/O, no request objects — testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dazzle.core import ir
from dazzle.core.access import workspace_allowed_personas
from dazzle.core.ir.identity import spec_display_id
from dazzle.core.strings import to_api_plural
from dazzle.page.app_paths import list_path
from dazzle.render.fragment.nav_icons import infer_nav_icon

__all__ = ["CommandEntry", "build_command_index", "filter_command_index"]


@dataclass(frozen=True)
class CommandEntry:
    """One reachable destination in the command palette."""

    label: str
    url: str
    icon: str  # registry icon name
    group: str  # "Workspaces" | "Records"


def _norm_roles(roles: list[str] | None) -> set[str]:
    return {r.removeprefix("role_") for r in (roles or [])}


def build_command_index(
    appspec: ir.AppSpec,
    *,
    roles: list[str] | None,
    is_superuser: bool = False,
    app_prefix: str = "/app",
) -> list[CommandEntry]:
    """All destinations the persona identified by *roles* can reach.

    Superusers get everything. Workspace access is filtered by
    ``workspace_allowed_personas`` (None = open to all authenticated).
    Entity lists are included when the entity has at least one list surface.
    """
    return _workspace_entries(
        appspec, roles=roles, is_superuser=is_superuser, app_prefix=app_prefix
    ) + _record_entries(appspec, app_prefix=app_prefix)


def _workspace_entries(
    appspec: ir.AppSpec, *, roles: list[str] | None, is_superuser: bool, app_prefix: str
) -> list[CommandEntry]:
    normalized = _norm_roles(roles)
    personas = list(getattr(appspec, "personas", None) or [])
    entries: list[CommandEntry] = []
    for ws in getattr(appspec, "workspaces", None) or []:
        allowed = workspace_allowed_personas(ws, personas)
        if not is_superuser and allowed is not None and not (normalized & set(allowed)):
            continue
        name = str(getattr(ws, "name", "") or "")
        if not name:
            continue
        label = str(getattr(ws, "title", None) or name.replace("_", " ").title())
        entries.append(
            CommandEntry(
                label=label,
                url=f"{app_prefix}/workspaces/{name}",
                icon=infer_nav_icon(label),
                group="Workspaces",
            )
        )
    return entries


def _record_entries(appspec: ir.AppSpec, *, app_prefix: str) -> list[CommandEntry]:
    list_entities: set[str] = set()
    for surface in getattr(appspec, "surfaces", None) or []:
        mode = getattr(surface, "mode", None)
        mode_val = getattr(mode, "value", mode)
        if mode_val == "list" and getattr(surface, "entity_ref", None):
            list_entities.add(str(surface.entity_ref))
    entries: list[CommandEntry] = []
    for entity in getattr(appspec.domain, "entities", None) or []:
        if entity.name not in list_entities:
            continue
        label = str(getattr(entity, "title", None) or entity.name)
        entries.append(
            CommandEntry(
                label=label,
                url=list_path(app_prefix, to_api_plural(entity.name)),
                icon=infer_nav_icon(label),
                group="Records",
            )
        )
    return entries


def nav_model_entries(model: Any) -> list[CommandEntry]:
    """Map a (reconciled) sidebar NavModel to palette entries (#1539).

    The palette and the sidebar must share one source of truth — a
    destination the sidebar wouldn't show a persona must not surface in
    the palette. Group/link `when` visibility conditions are NOT
    evaluated here: they gate render-time visibility, not access, and
    the NavModel itself is already persona-scoped.
    """
    entries: list[CommandEntry] = []
    for group in getattr(model, "groups", ()) or ():
        for link in getattr(group, "links", ()) or ():
            entries.append(
                CommandEntry(
                    label=link.label,
                    url=link.route,
                    icon=link.icon or infer_nav_icon(link.label),
                    group=group.label,
                )
            )
    return entries


def filter_command_index(entries: list[CommandEntry], query: str) -> list[CommandEntry]:
    """Case-insensitive substring filter; empty query returns all.

    Prefix matches sort before mid-string matches; stable within a rank.
    """
    q = query.strip().lower()
    if not q:
        return entries
    ranked: list[tuple[int, int, CommandEntry]] = []
    for i, e in enumerate(entries):
        label = e.label.lower()
        pos = label.find(q)
        if pos < 0:
            continue
        ranked.append((0 if pos == 0 else 1, i, e))
    ranked.sort(key=lambda t: (t[0], t[1]))
    return [e for _, _, e in ranked]


def spec_display_persona_ids(appspec: ir.AppSpec) -> list[str]:
    """Persona ids declared by the app (helper for callers/tests)."""
    return [str(spec_display_id(p)) for p in (getattr(appspec, "personas", None) or [])]
