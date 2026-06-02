"""Unified per-persona navigation builder (#1324).

Navigation is a pure function of (persona, appspec, rbac_matrix) — all static.
This module is the single source of a persona's sidebar: every page renders the
same precomputed NavModel for the current persona, so the three legacy builders
(workspace-page, entity-page, persona-union) can no longer drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class NavLink:
    label: str
    route: str
    icon: str | None = None
    entity: str | None = None  # target entity/workspace name (filtering + FR-6 lint)


@dataclass(frozen=True)
class NavGroup:
    label: str
    icon: str | None
    collapsed: bool
    links: tuple[NavLink, ...]


@dataclass(frozen=True)
class NavModel:
    groups: tuple[NavGroup, ...]
    auto_discovered: bool
