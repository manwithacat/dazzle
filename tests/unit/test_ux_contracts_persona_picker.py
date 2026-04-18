"""Tests for the workspace contract persona picker.

Pins the decision tree documented on `_pick_workspace_check_persona`:
  1. Explicit `access: persona(...)` on the workspace wins.
  2. Else, a persona whose `default_workspace` points at the workspace.
  3. Else, the first declared persona (admin by convention).

This was reported as a real issue when `dazzle ux verify --contracts`
on support_tickets returned three false-positive 403s because the
picker skipped step 2 and defaulted to admin on workspaces that
agent / manager / customer actually own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dazzle.cli.ux import _pick_workspace_check_persona


@dataclass
class _Persona:
    id: str
    default_workspace: str | None = None


@dataclass
class _Access:
    allow_personas: list[str] = field(default_factory=list)


@dataclass
class _Workspace:
    name: str
    access: _Access | None = None


@dataclass
class _AppSpec:
    workspaces: list[_Workspace]
    personas: list[_Persona]


def test_explicit_access_block_wins() -> None:
    """If the workspace has `access: persona(X)`, use X even when
    another persona has default_workspace pointing there."""
    spec = _AppSpec(
        workspaces=[_Workspace(name="queue", access=_Access(allow_personas=["manager"]))],
        personas=[
            _Persona(id="admin"),
            _Persona(id="manager"),
            _Persona(id="agent", default_workspace="queue"),
        ],
    )
    assert _pick_workspace_check_persona(spec, "queue") == "manager"


def test_default_workspace_reverse_lookup() -> None:
    """No access block — use the persona whose default_workspace
    points here. This closes the support_tickets false-positive
    where admin was checked against agent-owned workspaces."""
    spec = _AppSpec(
        workspaces=[_Workspace(name="queue", access=None)],
        personas=[
            _Persona(id="admin", default_workspace="_platform_admin"),
            _Persona(id="customer", default_workspace="my_tickets"),
            _Persona(id="agent", default_workspace="queue"),
            _Persona(id="manager", default_workspace="dashboard"),
        ],
    )
    assert _pick_workspace_check_persona(spec, "queue") == "agent"


def test_fallback_to_first_persona_when_nothing_matches() -> None:
    """No access block, no default_workspace match — fall back to
    the first declared persona (admin, by convention)."""
    spec = _AppSpec(
        workspaces=[_Workspace(name="orphan", access=None)],
        personas=[
            _Persona(id="admin"),
            _Persona(id="customer", default_workspace="somewhere_else"),
        ],
    )
    assert _pick_workspace_check_persona(spec, "orphan") == "admin"


def test_empty_access_allow_personas_falls_through() -> None:
    """An `access:` block with an empty allow_personas list is
    equivalent to no access block — fall through to the
    default_workspace reverse-lookup rather than picking a
    non-existent persona."""
    spec = _AppSpec(
        workspaces=[_Workspace(name="queue", access=_Access(allow_personas=[]))],
        personas=[
            _Persona(id="admin"),
            _Persona(id="agent", default_workspace="queue"),
        ],
    )
    assert _pick_workspace_check_persona(spec, "queue") == "agent"


def test_no_personas_at_all_defaults_to_admin_literal() -> None:
    """Pathological case: a project with zero personas. Return the
    literal 'admin' string so the downstream code has something to
    try to authenticate with (will fail loudly rather than crash
    on empty list access)."""
    spec = _AppSpec(workspaces=[_Workspace(name="x", access=None)], personas=[])
    assert _pick_workspace_check_persona(spec, "x") == "admin"
